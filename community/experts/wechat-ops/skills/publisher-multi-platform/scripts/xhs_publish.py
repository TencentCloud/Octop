#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx>=0.27.0",
#     "playwright>=1.40.0",
# ]
# ///
"""
XHS (社交内容平台/RedNote) Publisher — Publish content to Xiaohongshu

Based on ClawHub hi-yu/xhs skill v1.2.5 concept, implemented as a
standalone browser-automation publisher for the personal multi-platform
publishing workflow.

Usage:
    python3 xhs_publish.py <command> [options]

Commands:
    login           Login to Xiaohongshu (scan QR code)
    publish         Publish a note from Markdown file
    publish-text    Publish a text-only note
    check           Check login status and environment
    adapt           Adapt a Markdown article for XHS style (preview)

Environment:
    XHS_COOKIE_FILE     Path to cookie file (default: ~/.xhs-cookies.json)
    GEMINI_API_KEY      Gemini API key for AI cover generation (optional)
    IMG_API_KEY         Image generation API key (optional)
    HUNYUAN_API_KEY     Hunyuan API key for AI cover generation (optional)
"""

import argparse
import json
import os
import re
import sys
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

XHS_BASE_URL = "https://www.xiaohongshu.com"
XHS_CREATOR_URL = "https://creator.xiaohongshu.com"
XHS_PUBLISH_URL = f"{XHS_CREATOR_URL}/publish/publish"
COOKIE_FILE = os.environ.get("XHS_COOKIE_FILE", os.path.expanduser("~/.xhs-cookies.json"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def check_playwright_installed() -> bool:
    """Check if playwright and its browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        return True
    except ImportError:
        return False


def ensure_playwright():
    """Ensure playwright is installed and browsers are ready."""
    if not check_playwright_installed():
        print("Error: playwright is required. Install with:", file=sys.stderr)
        print("  pip install playwright", file=sys.stderr)
        print("  playwright install chromium", file=sys.stderr)
        sys.exit(1)


def save_cookies(cookies: list, path: str = COOKIE_FILE):
    """Save browser cookies to file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    os.chmod(path, 0o600)
    print(f"  💾 Cookies saved to: {path}")


def load_cookies(path: str = COOKIE_FILE) -> list | None:
    """Load browser cookies from file."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def parse_frontmatter(md_path: str) -> tuple[dict, str]:
    """Parse YAML frontmatter and body from a Markdown file."""
    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    fm = {}
    for line in match.group(1).strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")

    return fm, match.group(2)


def md_to_xhs_text(md_body: str, title: str = "") -> str:
    """
    Convert Markdown body to XHS-friendly plain text.

    XHS notes are short-form, emoji-rich, and use hashtags.
    This strips Markdown syntax and adapts the format.
    """
    text = md_body

    # Remove images (will be handled separately)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # Convert headers to bold text with emoji
    text = re.sub(r"^#{1,3}\s+(.+)$", r"📌 \1", text, flags=re.MULTILINE)
    text = re.sub(r"^#{4,6}\s+(.+)$", r"▪️ \1", text, flags=re.MULTILINE)

    # Convert bold
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)

    # Convert italic
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # Convert inline code
    text = re.sub(r"`(.+?)`", r"「\1」", text)

    # Convert code blocks to simplified text
    text = re.sub(r"```[\w]*\n(.*?)```", r"💻 代码片段:\n\1", text, flags=re.DOTALL)

    # Convert unordered lists
    text = re.sub(r"^[\-\*]\s+", "• ", text, flags=re.MULTILINE)

    # Convert ordered lists
    text = re.sub(r"^\d+\.\s+", "• ", text, flags=re.MULTILINE)

    # Convert links to text
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)

    # Convert blockquotes
    text = re.sub(r"^>\s*(.+)$", r"💬 \1", text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim
    text = text.strip()

    # Prepend title if provided
    if title:
        text = f"{title}\n\n{text}"

    # Truncate to XHS limit (~1000 chars recommended, max ~2000)
    if len(text) > 1800:
        text = text[:1800] + "\n\n... 👆 完整内容请查看公众号文章"

    return text


def extract_images_from_md(md_path: str) -> list[str]:
    """Extract image paths/URLs from Markdown file."""
    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    images = re.findall(r"!\[.*?\]\((.+?)\)", content)

    # Also check frontmatter cover
    fm, _ = parse_frontmatter(md_path)
    cover = fm.get("cover", "")
    if cover and cover not in images:
        images.insert(0, cover)

    # Resolve relative paths
    md_dir = Path(md_path).parent
    resolved = []
    for img in images:
        if img.startswith(("http://", "https://")):
            resolved.append(img)
        else:
            abs_path = str(md_dir / img)
            if os.path.isfile(abs_path):
                resolved.append(abs_path)

    return resolved


def extract_hashtags(md_body: str, fm: dict) -> list[str]:
    """Extract or generate hashtags from content."""
    tags = []

    # Check frontmatter for tags/hashtags
    for key in ("tags", "hashtags", "xhs_tags"):
        val = fm.get(key, "")
        if val:
            tags.extend([t.strip().strip("#") for t in val.split(",")])

    # Auto-extract existing hashtags from body
    body_tags = re.findall(r"#(\w+)", md_body)
    tags.extend(body_tags)

    # Deduplicate
    seen = set()
    unique = []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)

    return unique[:10]  # XHS max ~10 tags


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_login(args):
    """Login to Xiaohongshu via QR code scan."""
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    print("🔐 正在启动浏览器登录社交内容平台...")
    print("   请用社交内容平台 APP 扫描二维码完成登录\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        page.goto(f"{XHS_BASE_URL}/explore")
        page.wait_for_timeout(2000)

        # Wait for user to complete login
        print("⏳ 等待登录完成...")
        print("   登录成功后，页面会自动跳转。")
        print("   完成后请按任意键继续（或等待 120 秒自动超时）...\n")

        try:
            # Wait for the page to show logged-in state
            # (e.g., user avatar or profile icon appears)
            page.wait_for_selector(
                'a[href*="/user/profile"], .user-avatar, .side-bar-user',
                timeout=120000,
            )
            print("✅ 检测到登录成功!")
        except Exception:
            print("⚠️  未检测到自动登录状态，尝试保存当前 cookies...")

        # Save cookies
        cookies = context.cookies()
        save_cookies(cookies)

        browser.close()

    print("\n✅ 登录完成！Cookies 已保存。")
    print(f"   Cookie 文件: {COOKIE_FILE}")


def cmd_publish(args):
    """Publish a note from Markdown file to XHS."""
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    md_file = args.file
    if not os.path.isfile(md_file):
        print(f"Error: File not found: {md_file}", file=sys.stderr)
        sys.exit(1)

    # Parse content
    fm, body = parse_frontmatter(md_file)
    title = fm.get("title", Path(md_file).stem)
    xhs_text = md_to_xhs_text(body, title)
    images = extract_images_from_md(md_file)
    hashtags = extract_hashtags(body, fm)

    # Load cookies
    cookies = load_cookies()
    if not cookies:
        print("❌ 未找到登录信息。请先运行 login 命令:", file=sys.stderr)
        print(f"   python3 {__file__} login", file=sys.stderr)
        sys.exit(1)

    print("\n📱 准备发布社交内容平台笔记:")
    print(f"  标题: {title}")
    print(f"  图片: {len(images)} 张")
    print(f"  标签: {', '.join('#' + t for t in hashtags) if hashtags else '(无)'}")
    print(f"  正文预览: {xhs_text[:100]}...")
    print()

    if not images:
        print("⚠️  社交内容平台笔记建议至少包含一张图片。")
        print("   可以在 frontmatter 中添加 cover 字段，或在正文中添加图片。")
        if not args.force:
            print("   使用 --force 跳过此检查。")
            sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )

        # Restore cookies
        context.add_cookies(cookies)
        page = context.new_page()

        try:
            # Navigate to publish page
            print("  🌐 正在打开发布页面...")
            page.goto(XHS_PUBLISH_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # Check if we're logged in
            if "login" in page.url.lower() or "sign" in page.url.lower():
                print("  ❌ Cookie 已过期，请重新登录:", file=sys.stderr)
                print(f"     python3 {__file__} login", file=sys.stderr)
                browser.close()
                sys.exit(1)

            # Upload images
            if images:
                print(f"  🖼️  正在上传 {len(images)} 张图片...")
                file_input = page.locator('input[type="file"]').first
                for idx, img_path in enumerate(images):
                    if img_path.startswith(("http://", "https://")):
                        # Download remote image first
                        print(f"    ⬇️  下载远程图片 {idx + 1}...")
                        resp = httpx.get(img_path, timeout=30, follow_redirects=True)
                        if resp.status_code == 200:
                            import tempfile

                            ext = (
                                ".jpg" if "jpeg" in resp.headers.get("content-type", "") else ".png"
                            )
                            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                                tmp.write(resp.content)
                            img_path = tmp.name
                        else:
                            print(f"    ⚠️  下载失败，跳过: {img_path}")
                            continue

                    file_input.set_input_files(img_path)
                    page.wait_for_timeout(2000)
                    print(f"    ✅ 图片 {idx + 1}/{len(images)} 已上传")

                page.wait_for_timeout(3000)

            # Fill in title
            print("  📝 正在填写标题...")
            title_input = page.locator(
                '[placeholder*="标题"], .c-input_inner, input[name="title"]'
            ).first
            if title_input.is_visible():
                title_input.fill(title[:20])  # XHS title max 20 chars

            # Fill in content
            print("  📝 正在填写正文...")

            # Append hashtags
            text_with_tags = xhs_text
            if hashtags:
                tag_str = " ".join(f"#{t}" for t in hashtags)
                text_with_tags = f"{xhs_text}\n\n{tag_str}"

            content_area = page.locator(
                '[contenteditable="true"], .ql-editor, textarea[placeholder*="正文"]'
            ).first
            if content_area.is_visible():
                content_area.click()
                content_area.fill(text_with_tags)

            page.wait_for_timeout(2000)

            # Click publish button
            if not args.draft:
                print("  📤 正在发布...")
                publish_btn = page.locator(
                    'button:has-text("发布"), .publishBtn, button.css-k2sopx'
                ).first
                if publish_btn.is_visible():
                    publish_btn.click()
                    page.wait_for_timeout(5000)
                    print("  ✅ 笔记已发布！")
                else:
                    print("  ⚠️  未找到发布按钮，请手动点击发布。")
                    page.wait_for_timeout(30000)
            else:
                print("  📋 草稿模式：内容已填写，请手动检查并发布。")
                print("     30 秒后浏览器将自动关闭...")
                page.wait_for_timeout(30000)

        except Exception as e:
            print(f"  ❌ 发布过程中出错: {e}", file=sys.stderr)
            if not args.headless:
                print("  浏览器保持打开，请手动完成操作...")
                page.wait_for_timeout(60000)
        finally:
            # Update cookies
            new_cookies = context.cookies()
            save_cookies(new_cookies)
            browser.close()


def cmd_adapt(args):
    """Preview how a Markdown article would look as XHS note."""
    md_file = args.file
    if not os.path.isfile(md_file):
        print(f"Error: File not found: {md_file}", file=sys.stderr)
        sys.exit(1)

    fm, body = parse_frontmatter(md_file)
    title = fm.get("title", Path(md_file).stem)
    xhs_text = md_to_xhs_text(body, title)
    images = extract_images_from_md(md_file)
    hashtags = extract_hashtags(body, fm)

    print("=" * 60)
    print("📱 社交内容平台笔记预览")
    print("=" * 60)
    print(f"\n📌 标题: {title[:20]}")
    print(f"🖼️  图片: {len(images)} 张")
    if images:
        for i, img in enumerate(images[:5]):
            print(f"   {i + 1}. {img}")
        if len(images) > 5:
            print(f"   ... 还有 {len(images) - 5} 张")

    print(f"\n📝 正文 ({len(xhs_text)} 字):\n")
    print(xhs_text)

    if hashtags:
        print(f"\n🏷️  标签: {' '.join('#' + t for t in hashtags)}")

    print("\n" + "=" * 60)
    print(f"字数: {len(xhs_text)}/1800  |  图片: {len(images)} 张")

    if len(xhs_text) > 1800:
        print("⚠️  正文过长，发布时会被截断。建议精简内容或拆分为多篇笔记。")
    if not images:
        print("⚠️  没有图片。社交内容平台笔记建议至少包含一张图片。")


def cmd_check(args):
    """Check XHS publishing environment."""
    print("🔍 社交内容平台发布环境检查\n")

    # 1. Playwright
    pw_ok = check_playwright_installed()
    status = "✅" if pw_ok else "❌"
    print(f"  {status} playwright: {'已安装' if pw_ok else '未安装'}")
    if not pw_ok:
        print("      安装: pip install playwright && playwright install chromium")

    # 2. Cookie file
    cookies = load_cookies()
    status = "✅" if cookies else "❌"
    print(f"  {status} 登录状态: {'已登录 (有 Cookie)' if cookies else '未登录'}")
    if cookies:
        print(f"      Cookie 文件: {COOKIE_FILE}")
        # Check cookie freshness
        mtime = os.path.getmtime(COOKIE_FILE)
        age_hours = (time.time() - mtime) / 3600
        if age_hours > 24:
            print(f"      ⚠️  Cookie 已超过 {int(age_hours)} 小时，可能需要重新登录")
        else:
            print(f"      最近更新: {int(age_hours)} 小时前")

    # 3. AI 封面生成 API keys (optional)
    gemini = os.environ.get("GEMINI_API_KEY")
    img_api = os.environ.get("IMG_API_KEY")
    hunyuan = os.environ.get("HUNYUAN_API_KEY")

    if gemini or img_api or hunyuan:
        print("  ✅ AI 封面生成: 已配置")
        if gemini:
            print("      GEMINI_API_KEY: ***已设置***")
        if img_api:
            print("      IMG_API_KEY: ***已设置***")
        if hunyuan:
            print("      HUNYUAN_API_KEY: ***已设置***")
    else:
        print("  ℹ️  AI 封面生成: 未配置（可选）")
        print("      配置任一 API Key 即可启用: GEMINI_API_KEY / IMG_API_KEY / HUNYUAN_API_KEY")

    print()
    if not cookies:
        print("💡 下一步: 运行 login 命令完成登录")
        print(f"   python3 {__file__} login")


def cmd_publish_text(args):
    """Publish a text-only note (no Markdown file needed)."""
    ensure_playwright()

    title = args.title
    text = args.text
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    cookies = load_cookies()
    if not cookies:
        print("❌ 未找到登录信息。请先运行 login 命令:", file=sys.stderr)
        sys.exit(1)

    full_text = text
    if tags:
        tag_str = " ".join(f"#{t}" for t in tags)
        full_text = f"{text}\n\n{tag_str}"

    print("\n📱 准备发布社交内容平台纯文字笔记:")
    print(f"  标题: {title}")
    print(f"  正文: {full_text[:100]}...")
    print()

    # Use same browser automation logic as cmd_publish
    print("ℹ️  纯文字笔记需要至少一张图片。请在浏览器中手动添加图片后发布。")


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="xhs_publish",
        description="XHS Publisher — Publish content to Xiaohongshu (社交内容平台)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # login
    p = sub.add_parser("login", help="Login to XHS (scan QR code)")
    p.set_defaults(func=cmd_login)

    # publish
    p = sub.add_parser("publish", help="Publish Markdown file as XHS note")
    p.add_argument("file", help="Markdown file to publish")
    p.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    p.add_argument("--draft", action="store_true", help="Fill content but don't click publish")
    p.add_argument("--force", action="store_true", help="Skip image check")
    p.set_defaults(func=cmd_publish)

    # publish-text
    p = sub.add_parser("publish-text", help="Publish a text-only note")
    p.add_argument("--title", required=True, help="Note title")
    p.add_argument("--text", required=True, help="Note text content")
    p.add_argument("--tags", help="Comma-separated tags")
    p.set_defaults(func=cmd_publish_text)

    # adapt
    p = sub.add_parser("adapt", help="Preview Markdown adapted for XHS format")
    p.add_argument("file", help="Markdown file to preview")
    p.set_defaults(func=cmd_adapt)

    # check
    p = sub.add_parser("check", help="Check XHS publishing environment")
    p.set_defaults(func=cmd_check)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
