"""简单主题 —— 换肤逻辑全在 ``ui/index.js``。

Dashboard 只在聊天页 import 已启用插件的 UI，所以直接打开 ``/admin/users``
这类页面时主题不会被加载。为此这里额外给 SPA 外壳打一个小补丁：在
``index.html`` 的 ``</head>`` 前塞一段内联引导脚本，由它确认插件处于启用
状态后再把 ``ui/index.js`` 取回来注入。不依赖任何服务端模板改动。

补丁是幂等的，失败也只是退回"仅聊天页生效"，不会影响控制台启动。
"""

from __future__ import annotations

import contextlib
import json
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from octop_harness.plugins import PluginContext

VERSION = "1.0.2"

_TEXT = (
    "简单主题已安装：对话、输入框、侧栏和设置页使用一致的简洁排版，"
    "浅色/深色跟随控制台外观。要临时关掉，到「插件」面板禁用 简单主题后刷新页面。"
)

_BOOT_MARKER = "octop-simple-theme-boot"
_PATCH_FLAG = "_octop_simple_theme_shell_patch"

# 内联引导脚本：先确认插件仍是启用状态，再取回主题脚本执行。
# 必须是经典脚本（要走动态 import 而不是 <script type=module>，才能带鉴权头）。
# token 读取顺序与宿主 ``dashboard/src/api/request.ts::getAuthToken`` 一致：
# 勾选「记住我」在 localStorage，未勾选在 sessionStorage，前者优先。
_BOOT_JS = """
(function () {
  if (window.__octopSimpleThemeBooted) return;
  window.__octopSimpleThemeBooted = true;
  var token = "";
  try { token = localStorage.getItem("auth_token") || ""; } catch (e) {}
  if (!token) {
    try { token = sessionStorage.getItem("auth_token") || ""; } catch (e) {}
  }
  if (!token) return;
  var auth = { Authorization: "Bearer " + token };
  fetch("/api/plugins", { headers: auth })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (list) {
      var hit = null;
      for (var i = 0; i < (list || []).length; i++) {
        if (list[i] && list[i].id === "simple-theme") hit = list[i];
      }
      if (!hit || hit.enabled === false) return;
      var entry = (hit.ui && hit.ui.entry) || "ui/index.js";
      var path = String(entry).replace(/^\\/+/, "").replace(/^ui\\//, "");
      return fetch("/api/plugins/simple-theme/ui/" + path + "?v=__VERSION__", { headers: auth })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (code) {
          if (!code) return;
          var url = URL.createObjectURL(new Blob([code], { type: "text/javascript" }));
          return import(url).then(function (mod) {
            try {
              if (mod && typeof mod.setup === "function") mod.setup({ registerRenderer: function () {} });
            } catch (e) {}
          });
        });
    })
    .catch(function () {});
})();
""".replace("__VERSION__", VERSION)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "theme_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


async def simple_theme_info() -> str:
    """查看 简单主题的状态，以及如何开关它。"""
    data = {
        "version": VERSION,
        "theme": "simple",
        "mode": "auto",
        "checked_at": datetime.now(tz=UTC).isoformat(),
    }
    return _payload(data, _TEXT)


def _rewrite_shell(html: str) -> str:
    if _BOOT_MARKER in html:
        return html
    tag = f'<script id="{_BOOT_MARKER}">{_BOOT_JS}</script>\n'
    for anchor in ("</head>", "</HEAD>"):
        if anchor in html:
            return html.replace(anchor, tag + anchor, 1)
    return tag + html


def _patch_shell() -> None:
    """让 SPA 外壳在首屏就带上主题引导脚本（幂等）。"""
    try:
        from fastapi.responses import FileResponse, HTMLResponse

        from octop.api import app as app_module

        if getattr(app_module, _PATCH_FLAG, False):
            return
        # Hot reload does not restart the host process. If the previous fallback wrapper
        # is still installed, peel its closure back to the original function first.
        legacy_patch_flag = "_octop_" + "gpt_theme_shell_patch"
        previous = getattr(app_module, legacy_patch_flag, False)
        if previous:
            wrapped = app_module._dashboard_fallback
            for cell in getattr(wrapped, "__closure__", ()) or ():
                with contextlib.suppress(Exception):
                    candidate = cell.cell_contents
                    if (
                        isinstance(candidate, types.FunctionType)
                        and candidate.__name__ == "_dashboard_fallback"
                    ):
                        app_module._dashboard_fallback = candidate
                        break
            with contextlib.suppress(Exception):
                delattr(app_module, legacy_patch_flag)
        original = app_module._dashboard_fallback

        def fallback_with_theme(index_file: Path, full_path: str) -> Any:
            response = original(index_file, full_path)
            if not isinstance(response, FileResponse):
                return response
            try:
                text = Path(response.path).read_text(encoding="utf-8")
            except OSError:
                return response
            if "<html" not in text[:400].lower():
                return response
            patched = HTMLResponse(_rewrite_shell(text), status_code=200)
            patched.headers["Cache-Control"] = "no-cache"
            return patched

        app_module._dashboard_fallback = fallback_with_theme
        setattr(app_module, _PATCH_FLAG, True)
    except Exception as exc:  # noqa: BLE001 - 主题不该拦住插件加载
        print(f"[simple-theme] SPA 外壳补丁未安装: {exc}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "simple_theme_info",
        simple_theme_info,
        description="查看 简单主题插件是否生效，以及如何关闭它（返回一张状态卡片）。",
    )
    _patch_shell()
