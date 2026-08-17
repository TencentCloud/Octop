#!/usr/bin/env python3
"""plugin_version_lite.py — 插件版本探测精简版（行为同 plugin_version.py，去注释/调试/明细）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

_CB_VER_REL = Path(".codebuddy-plugin", "plugin.json")
_CB_MARKETS = ("local-dev", "wechataimarketplace",
               "codebuddy-plugins-official", "codebuddy-builtin")
_CB_BUILTIN_MARKETPLACE = "codebuddy-builtin"  # Linux 内置插件所在 marketplace
# qclaw 版本号优先看 package.json，再回退 openclaw.plugin.json / plugin.json
_OC_MANIFESTS = ("package.json", "openclaw.plugin.json", "plugin.json")
DEFAULT_PLUGIN = "weixinpay"
NOT_SUPPORTED = "0"
X402_THRESHOLD = "1.5.106"  # 版本 >= 此值认为支持 x402 协议

# qclaw 目录名映射：openclaw 规范名优先，回退兼容旧名。WorkBuddy 不受影响（始终 weixinpay）。
_OC_PLUGIN_ALIASES = {"weixinpay": ("openclaw-weixinpay", "weixinpay")}


def _oc_candidates(name: str) -> list[str]:
    return list(_OC_PLUGIN_ALIASES.get(name, (name,)))


def _sep() -> str:
    return ";" if sys.platform == "win32" else ":"


def _platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def _home() -> Path:
    return Path(os.environ.get("HOME") or os.path.expanduser("~"))


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError, json.JSONDecodeError,
            PermissionError, OSError):
        return None


def _ver_from(path: Path, rel: Path = _CB_VER_REL) -> Optional[str]:
    data = _read_json(path / rel)
    v = data.get("version") if data else None
    return str(v) if v else None


def detect_agent() -> str:
    # ① 身份环境变量（最可靠）。Qclaw 大小写存在版本差异，两种写法都认（env 名大小写敏感）
    if os.environ.get("Qclaw_USER_ID") or os.environ.get("QCLAW_USER_ID"):
        return "qclaw"
    if os.environ.get("CODEBUDDY_SESSION_ID"):
        return "workbuddy"
    # ② 平台专属环境变量线索（不看配置目录存在性：删应用后配置残留会误判，导致跨 Agent）
    if os.environ.get("OPENCLAW_CONFIG_PATH"):
        return "qclaw"
    if (os.environ.get("WORKBUDDY_CONFIG_DIR")
            or os.environ.get("CODEBUDDY_CONFIG_DIR")
            or os.environ.get("CODEBUDDY_BUILTIN_SKILLS_DIR")
            or os.environ.get("CODEBUDDY_PLUGIN_DIRS")):
        return "workbuddy"
    return "unknown"


def _resolve_config_dir() -> str:
    cfg = os.environ.get("WORKBUDDY_CONFIG_DIR") or os.environ.get("CODEBUDDY_CONFIG_DIR")
    if not cfg:
        wb = _home() / ".workbuddy"
        cfg = str(wb if wb.exists() else _home() / ".codebuddy")
    return cfg


def _cb_builtin_plugins_roots_by_platform() -> list[Path]:
    # 仅桌面端(win/mac)有 builtin-plugins 应用资源目录；Linux 无（走 codebuddy-builtin marketplace）
    name = _platform()
    if name == "macos":
        return [Path("/Applications/WorkBuddy.app/Contents/Resources/"
                     "app.asar.unpacked/resources/builtin-plugins")]
    if name == "windows":
        roots = []
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "Programs" / "WorkBuddy" / "resources"
                         / "app.asar.unpacked" / "resources" / "builtin-plugins")
        roots.append(Path(r"C:\Program Files\WorkBuddy\resources"
                          r"\app.asar.unpacked\resources\builtin-plugins"))
        return roots
    return []


def _builtin_roots() -> list[Path]:
    # 桌面端与 Linux 内置插件命名不同，按平台区分
    if _platform() == "linux":
        return [Path(_resolve_config_dir()) / "plugins" / "marketplaces"
                / _CB_BUILTIN_MARKETPLACE / "plugins"]
    roots: list[Path] = []
    skills = os.environ.get("CODEBUDDY_BUILTIN_SKILLS_DIR")
    if skills:
        sp = Path(skills)
        roots.append(sp.with_name("builtin-plugins") if sp.name
                     else sp.parent / "builtin-plugins")
    roots.extend(_cb_builtin_plugins_roots_by_platform())
    seen: set[str] = set()
    return [r for r in roots if not (str(r) in seen or seen.add(str(r)))]


def _oc_ver(root: Path) -> Optional[str]:
    for manifest in _OC_MANIFESTS:
        data = _read_json(root / manifest)
        v = data.get("version") if data else None
        if v:
            return str(v)
    return None


def detect_workbuddy(name: str = DEFAULT_PLUGIN) -> str:
    # ① 内置 builtin-plugins 优先（SKILLS_DIR -> CONFIG_DIR -> 平台推测）
    for broot in _builtin_roots():
        v = _ver_from(broot / name)
        if v:
            return v
    # ② CODEBUDDY_PLUGIN_DIRS
    raw = os.environ.get("CODEBUDDY_PLUGIN_DIRS", "")
    for chunk in raw.split(_sep()) if raw else []:
        d = chunk.strip()
        if d and Path(d).name == name:
            v = _ver_from(Path(d))
            if v:
                return v
    # ③④⑤ 配置目录 + marketplace / flat
    cfg = (os.environ.get("WORKBUDDY_CONFIG_DIR")
           or os.environ.get("CODEBUDDY_CONFIG_DIR"))
    if not cfg:
        wb = _home() / ".workbuddy"
        cfg = str(wb if wb.exists() else _home() / ".codebuddy")
    base = Path(cfg)
    for m in _CB_MARKETS:
        v = _ver_from(base / "plugins" / "marketplaces" / m / "plugins" / name)
        if v:
            return v
    v = _ver_from(base / "plugins" / name)
    if v:
        return v
    return NOT_SUPPORTED


def detect_qclaw(name: str = DEFAULT_PLUGIN) -> str:
    cfg = os.environ.get("OPENCLAW_CONFIG_PATH")
    config_file = Path(cfg) if cfg else _home() / ".qclaw" / "openclaw.json"
    config = _read_json(config_file)
    if not config:
        return NOT_SUPPORTED
    plugins = config.get("plugins", {}) or {}
    names = _oc_candidates(name)  # openclaw-weixinpay 优先，weixinpay 回退
    installs = plugins.get("installs", {}) or {}
    # ① installs.<候选>.installPath
    for nm in names:
        install = (installs.get(nm) or {}).get("installPath")
        if install:
            v = _oc_ver(Path(install))
            if v:
                return v
    # ② plugins.load.paths（内置/已加载插件）
    load = (plugins.get("load", {}) or {}).get("paths", [])
    load = [load] if isinstance(load, str) else [str(p) for p in (load or []) if p]
    for lp in load:
        base = Path(lp)
        cands = [base / nm for nm in names] + ([base] if base.name in names else [])
        for c in cands:
            v = _oc_ver(c)
            if v:
                return v
    return NOT_SUPPORTED


def _parse_ver(v: str) -> list:
    out = []
    for seg in str(v).split("."):
        num = ""
        for ch in seg:
            if ch.isdigit():
                num += ch
            else:
                break
        out.append(int(num) if num else 0)
    return out


def _ver_ge(a: str, b: str) -> bool:
    pa, pb = _parse_ver(a), _parse_ver(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return pa >= pb


def weixinpay_installed(version: str) -> bool:
    """版本 > 0（非 "0"）认为 weixinpay 插件存在。"""
    return version != NOT_SUPPORTED


def weixinpay_support_x402(version: str) -> bool:
    """版本 >= X402_THRESHOLD（默认 1.5.106）认为 weixinpay 支持 x402 协议。"""
    return weixinpay_installed(version) and _ver_ge(version, X402_THRESHOLD)


def get_plugin_version(name: str = DEFAULT_PLUGIN, system: str = "auto") -> str:
    system = system.lower()
    if system == "workbuddy":
        return detect_workbuddy(name)
    if system == "qclaw":
        return detect_qclaw(name)
    # auto：严格按 Agent 身份单查，绝不跨平台
    # （WorkBuddy 不查 qclaw 路径，Qclaw 不查 workbuddy 路径）
    agent = detect_agent()
    if agent == "qclaw":
        return detect_qclaw(name)
    # workbuddy 或无法判定时，保守只查 workbuddy（不跨到 qclaw）
    return detect_workbuddy(name)


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    name, system, as_json = DEFAULT_PLUGIN, "auto", False
    mode = "installed"  # 默认：返回是否支持微信插件
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--version":
            mode = "version"
        elif a == "--installed":
            mode = "installed"
        elif a == "--x402":
            mode = "x402"
        elif a == "--system":
            i += 1
            system = argv[i].lower() if i < len(argv) else system
        elif a.startswith("--system="):
            system = a.split("=", 1)[1].lower()
        elif not a.startswith("-"):
            name = a
        i += 1
    v = get_plugin_version(name, system)
    inst, x402 = weixinpay_installed(v), weixinpay_support_x402(v)
    if as_json:
        print(json.dumps({"plugin": name, "system": system,
                          "platform": _platform(), "version": v,
                          "weixinpay_installed": inst,
                          "weixinpay_support_x402": x402,
                          "weixinpay_x402_threshold": X402_THRESHOLD},
                         ensure_ascii=False))
    elif mode == "version":
        print(v)
    elif mode == "x402":
        print("true" if x402 else "false")
    else:
        print("true" if inst else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
