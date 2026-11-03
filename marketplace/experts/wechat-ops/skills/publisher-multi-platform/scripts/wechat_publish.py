#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx>=0.27.0",
# ]
# ///
"""
WeChat Publisher Personal — Publish Markdown to WeChat Official Account

A self-contained CLI that wraps wenyan-cli for rendering and uses
WeChat Official Account API for publishing articles to draft box.
Supports multi-platform publishing (WeChat + XHS) via companion script.

Usage:
    python3 wechat_publish.py <command> [options]

Commands:
    publish         Publish Markdown file(s) to WeChat draft box
    render          Render Markdown to HTML (preview only)
    themes          List available wenyan themes
    check           Check environment configuration
    server-status   Check wenyan server connection
    setup-server    Interactive guide for deploying wenyan server
    multi-publish   Publish to WeChat + XHS simultaneously (一文多发)

Environment:
    WECHAT_APP_ID       WeChat Official Account AppID (required)
    WECHAT_APP_SECRET   WeChat Official Account AppSecret (required)
    WENYAN_SERVER       Wenyan server URL for server mode (optional)
    WENYAN_API_KEY      Wenyan server API key (optional)
    WENYAN_THEME        Default theme (optional, default: github)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WECHAT_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_UPLOAD_IMG_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
WECHAT_ADD_DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
WECHAT_UPLOAD_THUMB_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"

TOKEN_CACHE_FILE = os.path.expanduser("~/.wechat-publisher-token.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def check_wenyan_installed() -> bool:
    """Check if wenyan-cli is installed globally."""
    return shutil.which("wenyan") is not None


def run_wenyan(args: list[str], capture=True) -> subprocess.CompletedProcess:
    """Run wenyan-cli with given arguments."""
    cmd = ["wenyan", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=120,
        )
        return result
    except FileNotFoundError:
        print(
            "Error: wenyan-cli not found. Install with: npm install -g @wenyan-md/cli",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: wenyan-cli timed out after 120 seconds.", file=sys.stderr)
        sys.exit(1)


def get_env(name: str, required: bool = False) -> str | None:
    """Get environment variable with optional requirement check."""
    val = os.environ.get(name)
    if required and not val:
        print(
            f"Error: Environment variable {name} is required but not set.",
            file=sys.stderr,
        )
        print(f"Set it with: export {name}='your_value'", file=sys.stderr)
        sys.exit(1)
    return val


def load_token_cache() -> dict:
    """Read the token cache file; raise when it is unreadable or malformed."""
    with open(TOKEN_CACHE_FILE) as f:
        cache = json.load(f)
    if not isinstance(cache, dict):
        raise ValueError("token cache is not a JSON object")
    return cache


def get_wechat_access_token() -> str:
    """Get WeChat API access token (with caching)."""
    app_id = get_env("WECHAT_APP_ID", required=True)
    app_secret = get_env("WECHAT_APP_SECRET", required=True)

    # Check cache. An access token is scoped to one official account, so a
    # record written for a different WECHAT_APP_ID must never be reused: the
    # next publish would land in the previous account and still report success.
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            cache = load_token_cache()
        except (OSError, ValueError):
            cache = {}
        # 5min buffer; records without an app_id predate this check, so refetch.
        if (
            cache.get("app_id") == app_id
            and cache.get("access_token")
            and cache.get("expires_at", 0) > time.time() + 300
        ):
            return cache["access_token"]

    # Fetch new token
    resp = httpx.get(
        WECHAT_TOKEN_URL,
        params={
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        },
        timeout=30,
    )

    data = resp.json()
    if "access_token" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown error")
        print(f"Error getting access token: [{errcode}] {errmsg}", file=sys.stderr)
        if errcode == 40164:
            print(
                "💡 Hint: Your IP is not in the whitelist. Add your IP to WeChat API whitelist.",
                file=sys.stderr,
            )
            print("   Get your IP with: curl ifconfig.me", file=sys.stderr)
        sys.exit(1)

    # Cache token, tagged with the account it was issued for.
    token_data = {
        "app_id": app_id,
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 7200),
    }
    with open(TOKEN_CACHE_FILE, "w") as f:
        json.dump(token_data, f)
    os.chmod(TOKEN_CACHE_FILE, 0o600)

    return data["access_token"]


def parse_frontmatter(md_path: str) -> dict:
    """Parse YAML frontmatter from a Markdown file."""
    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}

    fm = {}
    for line in match.group(1).strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def upload_thumb_image(access_token: str, image_path: str) -> str:
    """Upload a thumb/cover image to WeChat permanent material, return media_id."""
    if image_path.startswith(("http://", "https://")):
        # Download image first
        resp = httpx.get(image_path, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            print(
                f"Error downloading cover image: HTTP {resp.status_code}",
                file=sys.stderr,
            )
            sys.exit(1)
        # Determine extension
        content_type = resp.headers.get("content-type", "image/jpeg")
        ext = ".jpg" if "jpeg" in content_type else ".png" if "png" in content_type else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(resp.content)
        image_path = tmp.name

    if not os.path.isfile(image_path):
        print(f"Error: Cover image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    with open(image_path, "rb") as f:
        resp = httpx.post(
            WECHAT_UPLOAD_THUMB_URL,
            params={"access_token": access_token, "type": "thumb"},
            files={"media": (os.path.basename(image_path), f)},
            timeout=60,
        )

    data = resp.json()
    if "media_id" not in data:
        print(f"Error uploading thumb: {data}", file=sys.stderr)
        sys.exit(1)

    return data["media_id"]


def render_markdown(
    md_path: str,
    theme: str | None = None,
    server: str | None = None,
    api_key: str | None = None,
) -> str:
    """Render Markdown file to HTML using wenyan-cli."""
    args = ["render", "-f", md_path]
    if theme:
        args.extend(["--theme", theme])
    if server:
        args.extend(["--server", server])
    if api_key:
        args.extend(["--api-key", api_key])

    result = run_wenyan(args)
    if result.returncode != 0:
        print(f"Error rendering: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    return result.stdout


def publish_to_draft(
    access_token: str,
    title: str,
    html_content: str,
    thumb_media_id: str,
    author: str = "",
    digest: str = "",
    source_url: str = "",
) -> dict:
    """Publish an article to WeChat draft box."""
    article = {
        "title": title,
        "author": author,
        "digest": digest,
        "content": html_content,
        "thumb_media_id": thumb_media_id,
        "content_source_url": source_url,
        "show_cover_pic": 1,
        "need_open_comment": 0,
    }

    resp = httpx.post(
        WECHAT_ADD_DRAFT_URL,
        params={"access_token": access_token},
        json={"articles": [article]},
        timeout=60,
    )

    data = resp.json()
    if "media_id" not in data:
        errcode = data.get("errcode", "unknown")
        errmsg = data.get("errmsg", "unknown")
        print(f"Error publishing draft: [{errcode}] {errmsg}", file=sys.stderr)
        sys.exit(1)

    return data


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_publish(args):
    """Publish Markdown file(s) to WeChat draft box."""
    if not check_wenyan_installed():
        print(
            "Error: wenyan-cli not installed. Run: npm install -g @wenyan-md/cli",
            file=sys.stderr,
        )
        sys.exit(1)

    server = args.server or get_env("WENYAN_SERVER")
    api_key = args.api_key or get_env("WENYAN_API_KEY")
    theme = args.theme or get_env("WENYAN_THEME") or "github"
    access_token = get_wechat_access_token()

    for md_file in args.files:
        if not os.path.isfile(md_file):
            print(f"⚠️  File not found: {md_file}, skipping.", file=sys.stderr)
            continue

        print(f"\n📄 Processing: {md_file}")

        # Parse frontmatter
        fm = parse_frontmatter(md_file)
        title = fm.get("title")
        if not title:
            title = Path(md_file).stem
            print(f"  ⚠️  No title in frontmatter, using filename: {title}")

        author = fm.get("author", "")
        source_url = fm.get("source_url", "")
        cover = fm.get("cover", "")

        # Render Markdown → HTML using wenyan-cli
        print(f"  🎨 Rendering with theme '{theme}'...")
        wenyan_args = ["publish", "-f", md_file]
        if theme:
            wenyan_args.extend(["--theme", theme])
        if server:
            wenyan_args.extend(["--server", server])
        if api_key:
            wenyan_args.extend(["--api-key", api_key])

        result = run_wenyan(wenyan_args)
        if result.returncode != 0:
            stderr_text = result.stderr.strip() if result.stderr else ""
            # wenyan publish handles publishing itself — check the output
            if "success" in (result.stdout or "").lower() or "草稿" in (result.stdout or ""):
                print(f"  ✅ Published via wenyan-cli: {title}")
                if result.stdout:
                    print(f"  {result.stdout.strip()}")
                continue
            print(f"  ❌ wenyan publish failed: {stderr_text}", file=sys.stderr)

            # Fallback: render + manual upload
            print("  🔄 Falling back to manual publish...")
            html_content = render_markdown(md_file, theme, server, api_key)

            # Upload cover image
            thumb_media_id = ""
            if cover:
                # Resolve relative path
                if not cover.startswith(("http://", "https://", "/")):
                    cover = str(Path(md_file).parent / cover)
                print(f"  🖼️  Uploading cover: {cover}")
                thumb_media_id = upload_thumb_image(access_token, cover)
            else:
                print("  ⚠️  No cover image, using default placeholder.")
                # Create a simple placeholder
                thumb_media_id = _upload_placeholder_thumb(access_token)

            # Publish to draft
            print("  📤 Publishing to draft box...")
            result_data = publish_to_draft(
                access_token,
                title,
                html_content,
                thumb_media_id,
                author,
                "",
                source_url,
            )
            print(f"  ✅ Published! media_id={result_data.get('media_id')}")
            continue

        # wenyan publish succeeded
        print(f"  ✅ Published: {title}")
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                print(f"  {line}")


def _upload_placeholder_thumb(access_token: str) -> str:
    """Create and upload a simple placeholder thumb image."""
    try:
        from PIL import Image

        img = Image.new("RGB", (900, 383), color=(64, 128, 255))
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp.name, "JPEG")
        return upload_thumb_image(access_token, tmp.name)
    except ImportError:
        # Without PIL, create a minimal valid JPEG
        # Use a 1x1 pixel JPEG
        minimal_jpeg = bytes(
            [
                0xFF,
                0xD8,
                0xFF,
                0xE0,
                0x00,
                0x10,
                0x4A,
                0x46,
                0x49,
                0x46,
                0x00,
                0x01,
                0x01,
                0x00,
                0x00,
                0x01,
                0x00,
                0x01,
                0x00,
                0x00,
                0xFF,
                0xDB,
                0x00,
                0x43,
                0x00,
                0x08,
                0x06,
                0x06,
                0x07,
                0x06,
                0x05,
                0x08,
                0x07,
                0x07,
                0x07,
                0x09,
                0x09,
                0x08,
                0x0A,
                0x0C,
                0x14,
                0x0D,
                0x0C,
                0x0B,
                0x0B,
                0x0C,
                0x19,
                0x12,
                0x13,
                0x0F,
                0x14,
                0x1D,
                0x1A,
                0x1F,
                0x1E,
                0x1D,
                0x1A,
                0x1C,
                0x1C,
                0x20,
                0x24,
                0x2E,
                0x27,
                0x20,
                0x22,
                0x2C,
                0x23,
                0x1C,
                0x1C,
                0x28,
                0x37,
                0x29,
                0x2C,
                0x30,
                0x31,
                0x34,
                0x34,
                0x34,
                0x1F,
                0x27,
                0x39,
                0x3D,
                0x38,
                0x32,
                0x3C,
                0x2E,
                0x33,
                0x34,
                0x32,
                0xFF,
                0xC0,
                0x00,
                0x0B,
                0x08,
                0x00,
                0x01,
                0x00,
                0x01,
                0x01,
                0x01,
                0x11,
                0x00,
                0xFF,
                0xC4,
                0x00,
                0x1F,
                0x00,
                0x00,
                0x01,
                0x05,
                0x01,
                0x01,
                0x01,
                0x01,
                0x01,
                0x01,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x01,
                0x02,
                0x03,
                0x04,
                0x05,
                0x06,
                0x07,
                0x08,
                0x09,
                0x0A,
                0x0B,
                0xFF,
                0xC4,
                0x00,
                0xB5,
                0x10,
                0x00,
                0x02,
                0x01,
                0x03,
                0x03,
                0x02,
                0x04,
                0x03,
                0x05,
                0x05,
                0x04,
                0x04,
                0x00,
                0x00,
                0x01,
                0x7D,
                0x01,
                0x02,
                0x03,
                0x00,
                0x04,
                0x11,
                0x05,
                0x12,
                0x21,
                0x31,
                0x41,
                0x06,
                0x13,
                0x51,
                0x61,
                0x07,
                0x22,
                0x71,
                0x14,
                0x32,
                0x81,
                0x91,
                0xA1,
                0x08,
                0x23,
                0x42,
                0xB1,
                0xC1,
                0x15,
                0x52,
                0xD1,
                0xF0,
                0x24,
                0x33,
                0x62,
                0x72,
                0x82,
                0x09,
                0x0A,
                0x16,
                0x17,
                0x18,
                0x19,
                0x1A,
                0x25,
                0x26,
                0x27,
                0x28,
                0x29,
                0x2A,
                0x34,
                0x35,
                0x36,
                0x37,
                0x38,
                0x39,
                0x3A,
                0x43,
                0x44,
                0x45,
                0x46,
                0x47,
                0x48,
                0x49,
                0x4A,
                0x53,
                0x54,
                0x55,
                0x56,
                0x57,
                0x58,
                0x59,
                0x5A,
                0x63,
                0x64,
                0x65,
                0x66,
                0x67,
                0x68,
                0x69,
                0x6A,
                0x73,
                0x74,
                0x75,
                0x76,
                0x77,
                0x78,
                0x79,
                0x7A,
                0x83,
                0x84,
                0x85,
                0x86,
                0x87,
                0x88,
                0x89,
                0x8A,
                0x92,
                0x93,
                0x94,
                0x95,
                0x96,
                0x97,
                0x98,
                0x99,
                0x9A,
                0xA2,
                0xA3,
                0xA4,
                0xA5,
                0xA6,
                0xA7,
                0xA8,
                0xA9,
                0xAA,
                0xB2,
                0xB3,
                0xB4,
                0xB5,
                0xB6,
                0xB7,
                0xB8,
                0xB9,
                0xBA,
                0xC2,
                0xC3,
                0xC4,
                0xC5,
                0xC6,
                0xC7,
                0xC8,
                0xC9,
                0xCA,
                0xD2,
                0xD3,
                0xD4,
                0xD5,
                0xD6,
                0xD7,
                0xD8,
                0xD9,
                0xDA,
                0xE1,
                0xE2,
                0xE3,
                0xE4,
                0xE5,
                0xE6,
                0xE7,
                0xE8,
                0xE9,
                0xEA,
                0xF1,
                0xF2,
                0xF3,
                0xF4,
                0xF5,
                0xF6,
                0xF7,
                0xF8,
                0xF9,
                0xFA,
                0xFF,
                0xDA,
                0x00,
                0x08,
                0x01,
                0x01,
                0x00,
                0x00,
                0x3F,
                0x00,
                0x7B,
                0x94,
                0x11,
                0x00,
                0x00,
                0x00,
                0x00,
                0xFF,
                0xD9,
            ]
        )
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(minimal_jpeg)
        return upload_thumb_image(access_token, tmp.name)


def cmd_render(args):
    """Render Markdown to HTML preview."""
    if not check_wenyan_installed():
        print(
            "Error: wenyan-cli not installed. Run: npm install -g @wenyan-md/cli",
            file=sys.stderr,
        )
        sys.exit(1)

    md_file = args.file
    if not os.path.isfile(md_file):
        print(f"Error: File not found: {md_file}", file=sys.stderr)
        sys.exit(1)

    server = args.server or get_env("WENYAN_SERVER")
    api_key = args.api_key or get_env("WENYAN_API_KEY")
    theme = args.theme or get_env("WENYAN_THEME") or "github"

    html = render_markdown(md_file, theme, server, api_key)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ Rendered to: {args.output}")
    else:
        print(html)


def cmd_themes(args):
    """List available wenyan themes."""
    if not check_wenyan_installed():
        print(
            "Error: wenyan-cli not installed. Run: npm install -g @wenyan-md/cli",
            file=sys.stderr,
        )
        sys.exit(1)

    result = run_wenyan(["theme", "list"])
    if result.returncode != 0:
        # Fallback: list known built-in themes
        print("📎 Built-in themes (wenyan-cli):\n")
        themes = [
            ("github", "GitHub 风格，清爽简洁"),
            ("elegant", "优雅风格，适合文学类"),
            ("dark", "暗色主题"),
            ("condensed", "紧凑排版"),
            ("default", "默认主题"),
        ]
        for tid, desc in themes:
            print(f"  • {tid:<15} {desc}")
        print("\n💡 Use: --theme <name> to apply a theme")
        return

    print("📎 Available themes:\n")
    print(result.stdout)


def cmd_check(args):
    """Check environment configuration."""
    print("🔍 Environment Check\n")

    # 1. wenyan-cli
    installed = check_wenyan_installed()
    status = "✅" if installed else "❌"
    print(f"  {status} wenyan-cli: {'installed' if installed else 'NOT installed'}")
    if installed:
        ver = run_wenyan(["--version"])
        if ver.returncode == 0:
            print(f"      Version: {ver.stdout.strip()}")

    # 2. Node.js
    node = shutil.which("node")
    status = "✅" if node else "❌"
    print(f"  {status} Node.js: {'found' if node else 'NOT found'}")

    # 3. WECHAT_APP_ID
    app_id = get_env("WECHAT_APP_ID")
    status = "✅" if app_id else "❌"
    masked = f"{app_id[:4]}...{app_id[-4:]}" if app_id and len(app_id) > 8 else app_id
    print(f"  {status} WECHAT_APP_ID: {masked or 'NOT SET'}")

    # 4. WECHAT_APP_SECRET
    app_secret = get_env("WECHAT_APP_SECRET")
    status = "✅" if app_secret else "❌"
    print(f"  {status} WECHAT_APP_SECRET: {'***set***' if app_secret else 'NOT SET'}")

    # 5. Server mode
    server = get_env("WENYAN_SERVER")
    if server:
        print(f"  ℹ️  WENYAN_SERVER: {server}")
        api_key = get_env("WENYAN_API_KEY")
        print(f"  ℹ️  WENYAN_API_KEY: {'***set***' if api_key else 'NOT SET'}")
    else:
        print("  ℹ️  Server mode: not configured (using local mode)")

    # 6. Token cache
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            cache = load_token_cache()
            expires = cache.get("expires_at", 0)
            if cache.get("app_id") != app_id:
                print("  ⚠️  Token cache: not valid for this WECHAT_APP_ID (will be re-fetched)")
            elif expires > time.time():
                remaining = int((expires - time.time()) / 60)
                print(f"  ✅ Token cache: valid ({remaining} min remaining)")
            else:
                print("  ⚠️  Token cache: expired")
        except (OSError, ValueError):
            print("  ⚠️  Token cache: corrupted")
    else:
        print("  ℹ️  Token cache: not found (will fetch on first use)")

    # 7. IP hint
    print("\n💡 Your public IP: run 'curl ifconfig.me' to check")
    print("   Make sure it's in your WeChat API IP whitelist")
    if not server:
        print("   Or use server mode to avoid local IP whitelist issues")


def cmd_server_status(args):
    """Check wenyan server connection."""
    server = args.server or get_env("WENYAN_SERVER")
    if not server:
        print("ℹ️  No server configured. Using local mode.")
        print("   Set WENYAN_SERVER to use server mode.")
        return

    print(f"🔌 Checking server: {server}")
    try:
        resp = httpx.get(f"{server}/health", timeout=10)
        if resp.status_code == 200:
            print("  ✅ Server is online")
        else:
            print(f"  ⚠️  Server responded with HTTP {resp.status_code}")
    except httpx.ConnectError:
        print("  ❌ Cannot connect to server")
    except httpx.TimeoutException:
        print("  ❌ Connection timed out")


def cmd_setup_server(args):
    """Interactive guide for deploying wenyan server."""
    host = args.host
    print(f"""
╔══════════════════════════════════════════════════════╗
║   Wenyan Server 部署指南 — 个人 IP 白名单代理         ║
╚══════════════════════════════════════════════════════╝

目的：在你的云服务器上部署 wenyan server，解决本地 IP 不固定的问题。
服务器只需要有固定公网 IP 即可。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: 在服务器上安装 Node.js 和 wenyan-cli

    ssh root@{host}
    # 安装 Node.js (如果没有)
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs

    # 安装 wenyan-cli
    npm install -g @wenyan-md/cli
    wenyan --help

Step 2: 配置环境变量

    export WECHAT_APP_ID="your_app_id"
    export WECHAT_APP_SECRET="your_app_secret"

Step 3: 启动 wenyan server

    # 前台运行（测试）
    wenyan serve --port 7788

    # 后台运行（生产）
    nohup wenyan serve --port 7788 >> /var/log/wenyan-server.log 2>&1 &

Step 4: 将服务器 IP 加入微信白名单

    # 获取服务器公网 IP
    curl ifconfig.me

    # 登录微信开发者平台 → API IP白名单 → 添加上面的 IP

Step 5: 配置本地环境

    # 在本地 ~/.bashrc 或 ~/.zshrc 中添加：
    export WENYAN_SERVER="http://{host}:7788"
    export WENYAN_API_KEY="your_api_key"  # 如果设置了 API key

Step 6: 验证

    python3 {os.path.abspath(__file__)} server-status --server http://{host}:7788

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

完成后，你就可以在本地使用任意网络发布文章了：

    python3 {os.path.abspath(__file__)} publish article.md

wenyan-cli 会自动通过 server 转发请求到微信 API。
""")


def cmd_multi_publish(args):
    """Publish to WeChat + XHS simultaneously (一文多发)."""
    xhs_script = Path(__file__).parent / "xhs_publish.py"
    if not xhs_script.exists():
        print(f"Error: xhs_publish.py not found at {xhs_script}", file=sys.stderr)
        sys.exit(1)

    results = {"wechat": False, "xhs": False}

    for md_file in args.files:
        if not os.path.isfile(md_file):
            print(f"⚠️  File not found: {md_file}, skipping.", file=sys.stderr)
            continue

        fm = parse_frontmatter(md_file)
        title = fm.get("title", Path(md_file).stem)

        print(f"\n{'=' * 60}")
        print(f"📄 一文多发: {title}")
        print(f"{'=' * 60}")

        # Step 1: Publish to WeChat
        print("\n📱 [1/2] 发布到内容运营平台...")
        print(f"{'-' * 40}")
        try:
            # Reuse existing publish logic
            wechat_args = argparse.Namespace(
                files=[md_file],
                theme=args.theme,
                server=args.server,
                api_key=args.api_key,
            )
            cmd_publish(wechat_args)
            results["wechat"] = True
        except SystemExit:
            print("  ⚠️  微信发布失败，继续社交内容平台发布...")

        # Step 2: Publish to XHS
        print("\n📕 [2/2] 发布到社交内容平台...")
        print(f"{'-' * 40}")
        try:
            xhs_cmd = [
                sys.executable,
                str(xhs_script),
                "publish",
                md_file,
            ]
            if args.xhs_draft:
                xhs_cmd.append("--draft")
            if args.xhs_headless:
                xhs_cmd.append("--headless")

            result = subprocess.run(xhs_cmd, timeout=180)
            if result.returncode == 0:
                results["xhs"] = True
        except subprocess.TimeoutExpired:
            print("  ⚠️  社交内容平台发布超时 (180s)。", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  社交内容平台发布出错: {e}", file=sys.stderr)

        # Summary
        print(f"\n{'=' * 60}")
        print(f"📊 发布结果汇总: {title}")
        print(f"  内容运营平台: {'✅ 成功' if results['wechat'] else '❌ 失败'}")
        print(f"  社交内容平台:     {'✅ 成功' if results['xhs'] else '❌ 失败'}")
        print(f"{'=' * 60}")

        if results["wechat"]:
            print("\n💡 下一步:")
            print(f"  1. 登录公众号后台，在草稿箱找到《{title}》并发布")
            print("  2. 发布后去搜狗微信搜索验证: https://weixin.sogou.com/")
        print()


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wechat_publish",
        description="WeChat Publisher Personal — Publish Markdown to WeChat Official Account",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # publish
    p = sub.add_parser("publish", help="Publish Markdown to WeChat draft box")
    p.add_argument("files", nargs="+", help="Markdown file(s) to publish")
    p.add_argument("--theme", "-t", help="Rendering theme (default: github)")
    p.add_argument("--server", help="Wenyan server URL (env: WENYAN_SERVER)")
    p.add_argument("--api-key", help="Wenyan server API key (env: WENYAN_API_KEY)")
    p.set_defaults(func=cmd_publish)

    # render
    p = sub.add_parser("render", help="Render Markdown to HTML (preview)")
    p.add_argument("file", help="Markdown file to render")
    p.add_argument("--theme", "-t", help="Rendering theme (default: github)")
    p.add_argument("--output", "-o", help="Output HTML file path")
    p.add_argument("--server", help="Wenyan server URL")
    p.add_argument("--api-key", help="Wenyan server API key")
    p.set_defaults(func=cmd_render)

    # themes
    p = sub.add_parser("themes", help="List available themes")
    p.set_defaults(func=cmd_themes)

    # check
    p = sub.add_parser("check", help="Check environment configuration")
    p.set_defaults(func=cmd_check)

    # server-status
    p = sub.add_parser("server-status", help="Check wenyan server connection")
    p.add_argument("--server", help="Wenyan server URL")
    p.set_defaults(func=cmd_server_status)

    # setup-server
    p = sub.add_parser("setup-server", help="Guide for deploying wenyan server")
    p.add_argument("--host", required=True, help="Your server IP or hostname")
    p.set_defaults(func=cmd_setup_server)

    # multi-publish
    p = sub.add_parser("multi-publish", help="Publish to WeChat + XHS simultaneously (一文多发)")
    p.add_argument("files", nargs="+", help="Markdown file(s) to publish")
    p.add_argument("--theme", "-t", help="Rendering theme for WeChat (default: github)")
    p.add_argument("--server", help="Wenyan server URL (env: WENYAN_SERVER)")
    p.add_argument("--api-key", help="Wenyan server API key (env: WENYAN_API_KEY)")
    p.add_argument(
        "--xhs-draft",
        action="store_true",
        help="XHS: fill content but don't auto-publish",
    )
    p.add_argument("--xhs-headless", action="store_true", help="XHS: run browser in headless mode")
    p.set_defaults(func=cmd_multi_publish)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
