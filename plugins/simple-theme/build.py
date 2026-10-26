#!/usr/bin/env python3
"""把 ui/theme.css 内联进 ui/index.template.js，产出 ui/index.js。

用法：
    python build.py

为什么要内联：插件的 UI 静态资源挂在鉴权接口 /api/plugins/<id>/ui/<file> 下，
外链 <link rel=stylesheet> 带不上 Authorization 头，只能内联；内联顺带还避开了
Service Worker 对插件 JS 的缓存。

字体是个例外——它是二进制，必须走 fetch + FontFace，见 index.template.js。
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE / "ui"
CSS = UI / "theme.css"
ICONS = UI / "model-icons.js"
TEMPLATE = UI / "index.template.js"
OUT = UI / "index.js"
PLUGIN_MANIFEST = HERE / "plugin.yaml"
UI_PLUGIN_MANIFEST = UI / "plugin.yaml"
PLACEHOLDER = "__THEME_CSS__"
ICON_PLACEHOLDER = "/* __MODEL_ICONS__"


def main() -> int:
    css = CSS.read_text(encoding="utf-8")
    if "`" in css:
        raise SystemExit("theme.css 里不能出现反引号（会截断模板字符串）")
    if "\\" in css:
        # 反斜杠在模板字符串里也会被转义，逐处检查太脆，直接替换更安全
        css = css.replace("\\", "\\\\")
    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"{TEMPLATE.name} 缺少占位符 {PLACEHOLDER}")
    icons = ICONS.read_text(encoding="utf-8").strip()
    marker = next((ln for ln in template.splitlines() if ln.startswith(ICON_PLACEHOLDER)), None)
    if marker is None:
        raise SystemExit(f"{TEMPLATE.name} 缺少图标占位行 {ICON_PLACEHOLDER} ... */")
    out = template.replace(marker, icons)
    OUT.write_text(out.replace(PLACEHOLDER, css), encoding="utf-8")
    UI_PLUGIN_MANIFEST.write_text(PLUGIN_MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        f"built {OUT.relative_to(HERE)}  ({len(css)} bytes css, "
        f"{len(icons)} bytes icons, {OUT.stat().st_size} bytes total)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
