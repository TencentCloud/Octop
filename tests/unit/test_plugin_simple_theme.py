"""``plugins/simple-theme`` must stay installable, buildable and attributed."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
from octop_harness.plugins import PluginManifest, PluginRegistry, load_plugin_dir

_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "simple-theme"
_TEMPLATE = _PLUGIN_DIR / "ui" / "index.template.js"
_BUNDLE = _PLUGIN_DIR / "ui" / "index.js"
# Dashboard keeps the JWT in localStorage ("remember me") or sessionStorage
# (session-only login); ``getAuthToken()`` reads local first, then session.
_HELPER_RE = re.compile(r"function simpleAuthToken\(\) \{.*?\n\}\n", re.S)


def _load_main() -> object:
    spec = importlib.util.spec_from_file_location("_simple_theme_main", _PLUGIN_DIR / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_declares_theme_plugin_and_ui() -> None:
    manifest = PluginManifest.load(_PLUGIN_DIR / "plugin.yaml")
    assert manifest.id == "simple-theme"
    assert manifest.version == "1.0.2"
    assert manifest.kind == "tool"
    assert manifest.name == "简单主题"
    assert (_PLUGIN_DIR / "ui" / "index.js").is_file()
    assert (_PLUGIN_DIR / "ui" / "manifest.json").is_file()


def test_plugin_loads_and_registers_status_tool() -> None:
    PluginRegistry.reset()
    try:
        loaded = load_plugin_dir(_PLUGIN_DIR, install_deps=False)
        assert loaded.manifest.id == "simple-theme"
        assert [tool.name for tool in loaded.tools] == ["simple_theme_info"]
    finally:
        PluginRegistry.reset()


def test_status_tool_returns_theme_card_payload() -> None:
    module = _load_main()
    payload = json.loads(asyncio.run(module.simple_theme_info()))  # type: ignore[attr-defined]
    assert payload["octop_ui"] == {"renderer": "theme_card", "version": 1}
    assert payload["data"]["version"] == "1.0.2"
    assert payload["text"]


def test_shell_rewrite_is_idempotent_and_lands_before_head_close() -> None:
    module = _load_main()
    html = "<html><head><title>Octop</title></head><body></body></html>"
    once = module._rewrite_shell(html)  # type: ignore[attr-defined]
    assert once.count("octop-simple-theme-boot") == 1
    assert once.index("octop-simple-theme-boot") < once.index("</head>")
    assert module._rewrite_shell(once) == once  # type: ignore[attr-defined]


def test_built_bundle_contains_current_css() -> None:
    """``build.py`` inlines ``theme.css`` (backslash-escaped) into ``index.js``."""
    css = (_PLUGIN_DIR / "ui" / "theme.css").read_text(encoding="utf-8").strip()
    bundle = (_PLUGIN_DIR / "ui" / "index.js").read_text(encoding="utf-8")
    assert "const CSS = `" in bundle
    assert css.replace("\\", "\\\\") in bundle


def test_third_party_licenses_are_shipped() -> None:
    licenses = _PLUGIN_DIR / "LICENSES"
    ofl = (licenses / "Inter-OFL-1.1.txt").read_text(encoding="utf-8")
    mit = (licenses / "LobeHub-icons-MIT.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in ofl
    assert "The Inter Project Authors" in ofl
    assert "MIT License" in mit
    assert "LobeHub" in mit
    readme = (_PLUGIN_DIR / "README.md").read_text(encoding="utf-8")
    assert "LICENSES/README.md" in readme


# ---------------------------------------------------------------------------
# Auth-token compatibility: session-only logins store the JWT in sessionStorage
# (``dashboard/src/api/request.ts::setAuthToken(token, remember=False)``), the
# "remember me" default keeps it in localStorage. Every theme read must follow
# the host's ``getAuthToken()`` order: local first, session second.
# ---------------------------------------------------------------------------


def _helper_source(path: Path) -> str:
    match = _HELPER_RE.search(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path} 缺少共享的 simpleAuthToken() helper"
    return match.group(0)


def test_auth_token_reads_are_centralised_in_one_helper() -> None:
    """No caller may read ``auth_token`` on its own (that is what dropped the
    session-only login), and the shipped bundle must match the template."""
    template_helper = _helper_source(_TEMPLATE)
    assert _helper_source(_BUNDLE) == template_helper, "ui/index.js 未按模板重建"

    assert template_helper.index('localStorage.getItem("auth_token")') < template_helper.index(
        'sessionStorage.getItem("auth_token")'
    ), "读取顺序必须与宿主 getAuthToken() 一致：local 优先，其次 session"

    for path in (_TEMPLATE, _BUNDLE):
        text = path.read_text(encoding="utf-8")
        assert text.count("auth_token") == 2, f"{path} 仍有绕开 helper 的 token 读取"
        assert len(_HELPER_RE.findall(text)) == 1
        for call_site in ("verifyEnabled", "simpleAuthHeaders", "loadFont"):
            start = text.index(f"function {call_site}(")
            end = text.find("\nfunction ", start + 1)
            body = text[start : end if end != -1 else len(text)]
            assert "simpleAuthToken()" in body, f"{path}: {call_site} 未走共享 helper"
            assert "localStorage.getItem" not in body, f"{path}: {call_site} 直接读 localStorage"


def test_boot_script_reads_session_storage_fallback() -> None:
    """The inline SPA-shell bootstrap runs before the bundle and needs the same
    fallback, otherwise session-only users get no theme outside the chat page."""
    boot_js = _load_main()._BOOT_JS  # type: ignore[attr-defined]
    local_at = boot_js.index('localStorage.getItem("auth_token")')
    session_at = boot_js.index('sessionStorage.getItem("auth_token")')
    assert local_at < session_at
    assert "if (!token)" in boot_js[local_at:session_at], "session 读取必须只在 local 为空时兜底"
    # 存储被禁用时读取会抛错，兜底分支自己也要有 try/catch
    assert "try {" in boot_js[session_at - 40 : session_at], "session 兜底必须包在 try 里"
    assert boot_js.index("if (!token) return;") > session_at


_BROWSER_PROBE = """
({ helper, local, session }) => {
  const store = (state) => ({
    getItem(key) {
      if (state === "throw") throw new DOMException("denied", "SecurityError");
      return state && Object.prototype.hasOwnProperty.call(state, key) ? state[key] : null;
    },
  });
  Object.defineProperty(window, "localStorage", { configurable: true, get: () => store(local) });
  Object.defineProperty(window, "sessionStorage", { configurable: true, get: () => store(session) });
  new Function(helper + "; window.__probe = simpleAuthToken;")();
  return window.__probe();
}
"""


@pytest.mark.slow
def test_auth_token_fallback_runs_in_a_real_browser() -> None:
    """Execute the *shipped* helper (extracted from ``ui/index.js``) in Chromium
    against stub storages — mirrors the host's storage layout, no network."""
    sync_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed")

    helper = _helper_source(_BUNDLE)
    cases: list[tuple[Any, Any, str, str]] = [
        ({"auth_token": "local-tok"}, None, "local-tok", "记住我 → localStorage"),
        (None, {"auth_token": "sess-tok"}, "sess-tok", "未记住 → sessionStorage"),
        ({"auth_token": "local-tok"}, {"auth_token": "sess-tok"}, "local-tok", "local 优先"),
        (None, None, "", "未登录"),
        ("throw", {"auth_token": "sess-tok"}, "sess-tok", "localStorage 抛错时兜底"),
        ("throw", "throw", "", "两种存储都不可用时静默降级"),
    ]

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - 沙箱/CI 没装浏览器时跳过
            pytest.skip(f"chromium 不可用: {exc}")
        try:
            page = browser.new_page()
            page.set_content("<html><body></body></html>")
            for local, session, expected, why in cases:
                got = page.evaluate(
                    _BROWSER_PROBE, {"helper": helper, "local": local, "session": session}
                )
                assert got == expected, f"{why}: 期望 {expected!r}，实际 {got!r}"
        finally:
            browser.close()
