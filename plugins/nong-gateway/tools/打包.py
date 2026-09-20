#!/usr/bin/env python3
"""把 plugin/ 打成可上传的 ZIP，并跑官方硬规矩校验（白名单 + 密钥扫描 + manifest 契约）。

用法:
    python3 tools/打包.py --check-only          # 只校验不出包
    python3 tools/打包.py [--out dist/]          # 校验 + 出 nong-gateway-<version>.zip
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PLUGIN_DIR = HERE / "plugin"

SECRET_PATTERNS = [
    (re.compile(r"km_b_prod_[A-Za-z0-9]{10,}"), "kimi token"),
    (re.compile(r"sk-[A-Za-z0-9]{16,}"), "openai 风格 key"),
    (re.compile(r"app_secret['\"]?\s*[:=]\s*['\"][A-Za-z0-9]{16,}"), "元宝 secret 字面量"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"), "JWT"),
]


def check() -> list[str]:
    problems: list[str] = []
    manifest = PLUGIN_DIR / "plugin.yaml"
    if not manifest.is_file():
        return ["plugin/plugin.yaml 不存在"]
    text = manifest.read_text(encoding="utf-8")
    for key in ("id", "version", "kind", "entry"):
        if not re.search(rf"^{key}:", text, re.M):
            problems.append(f"plugin.yaml 缺 {key}")
    entry = PLUGIN_DIR / "main.py"
    if "def setup(" not in entry.read_text(encoding="utf-8"):
        problems.append("entry main.py 没有 setup(ctx)")
    for f in PLUGIN_DIR.rglob("*"):
        if "__pycache__" in f.parts or ".git" in f.parts:
            problems.append(f"不该进包: {f}")
        if f.suffix == ".zip":
            problems.append(f"旧 ZIP 不该进包: {f}")
    # 密钥特征扫描
    for f in PLUGIN_DIR.rglob("*"):
        if f.is_file() and f.suffix in (".py", ".yaml", ".md", ".json"):
            body = f.read_text(encoding="utf-8", errors="ignore")
            for pat, label in SECRET_PATTERNS:
                if pat.search(body):
                    problems.append(f"{f.relative_to(PLUGIN_DIR)} 疑似含 {label}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--out", default=str(HERE / "dist"))
    args = ap.parse_args()
    problems = check()
    if problems:
        print("校验未过：")
        for p in problems:
            print("  -", p)
        return 1
    print("校验通过（manifest 契约 / 密钥特征 / 打包白名单）")
    if args.check_only:
        return 0
    import yaml
    meta = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    zpath = out / f"{meta['id']}-{meta['version']}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PLUGIN_DIR.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(PLUGIN_DIR.parent))
    print(f"已出包: {zpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
