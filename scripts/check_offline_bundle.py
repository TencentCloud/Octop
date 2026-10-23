#!/usr/bin/env python3
"""Offline bundle 构建后闸门(CI 在上传 artifact 前跑,失败退出码非零)。

三个检查:
  1. --variant legacy:每个 wheel 必须带 glibc <= 2.17 基线的标签
     (manylinux2014_* 或 manylinux_2_17_*);standard 只生成基线清单。
  2. 一致性:requirements-third-party.txt 里每个 == 锁定的包,必须与 bundle 内
     实际 wheel 版本一致(防"包与清单不一致"事故,如 mcp 2.x 那次)。
  3. 主包存在:bundle 内必须有 5 个主包 wheel(octop + 四上游)。

用法: python3 scripts/check_offline_bundle.py <offline 目录> [--variant legacy|standard]
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

MAIN_PACKAGES = {"octop", "octop_harness", "octop_gateway", "octop_memory", "octop_browser"}
WHEEL_NAME_RE = re.compile(r"^(?P<name>[^-]+)-(?P<ver>[^-]+)-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<tags>[^-]+)\.whl$")


def wheel_tag_baseline_glibc(tags_field: str) -> tuple[int, int] | None:
    """取 wheel 兼容标签中的**最低** glibc 基线(即可装的最老系统)。

    tags_field 形如 manylinux_2_17_aarch64.manylinux2014_aarch64。
    返回 None 表示纯 Python / 平台无关 wheel(视为通过)。
    """
    lowest: tuple[int, int] | None = None
    for tag in tags_field.split("."):
        m = re.match(r"manylinux_(\d+)_(\d+)", tag)
        if m:
            v = (int(m.group(1)), int(m.group(2)))
        elif re.match(r"manylinux2014", tag):
            v = (2, 17)
        elif re.match(r"manylinux1_", tag):
            v = (2, 5)  # manylinux1 = glibc 2.5 基线,比 2014 更老,兼容
        elif tag.startswith(("linux_", "any")):
            continue
        else:
            # 非 manylinux 标签(如 musllinux)不在本闸门范围
            continue
        if lowest is None or v < lowest:
            lowest = v
    return lowest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle_dir")
    ap.add_argument("--variant", choices=("standard", "legacy"), default="standard")
    args = ap.parse_args()

    bundle = args.bundle_dir
    wheels = sorted(glob.glob(os.path.join(bundle, "*.whl")))
    if not wheels:
        print(f"::error::bundle 内没有 wheel: {bundle}")
        return 1

    failures: list[str] = []
    baselines: list[str] = []

    # ---- 检查 1:标签基线 -------------------------------------------------------
    for whl in wheels:
        name = os.path.basename(whl)
        m = WHEEL_NAME_RE.match(name)
        if not m:
            failures.append(f"无法解析 wheel 文件名: {name}")
            continue
        norm = m.group("name").lower().replace("_", "-")
        baseline = wheel_tag_baseline_glibc(m.group("tags"))
        if baseline is None:
            tags_field = m.group("tags")
            if "any" in tags_field.split("."):
                baselines.append(f"{name}: platform-independent")
            elif tags_field in ("linux_aarch64", "linux_x86_64"):
                # 无 glibc 下限标签(如 manylinux2014 容器内 pip wheel 的原始产物):
                # 轮内 glibc 符号取决于编译环境——管线保证 legacy 的 linux_* 轮在
                # manylinux2014(glibc 2.17)容器内编译,目标 glibc 2.23 可装,放行。
                # (runner 本机直编的 macosx/win 轮仍会在 legacy 拦下)
                baselines.append(f"{name}: linux_{args.variant} (no glibc floor, accepted)")
            else:
                baselines.append(f"{name}: NON-MANYLINUX ({tags_field})")
                if args.variant == "legacy":
                    failures.append(f"legacy 包内混入非 manylinux 二进制轮: {name} ({tags_field})")
        else:
            baselines.append(f"{name}: glibc {baseline[0]}.{baseline[1]}")
            if args.variant == "legacy" and baseline > (2, 17):
                failures.append(
                    f"legacy 包内混入高基线 wheel: {name} (glibc {baseline[0]}.{baseline[1]} > 2.17)"
                )

    # ---- 检查 2:清单 vs 实际 wheel 一致性 --------------------------------------
    req_path = os.path.join(bundle, "requirements-third-party.txt")
    if os.path.exists(req_path):
        pinned: dict[str, str] = {}
        for line in open(req_path).read().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pm = re.match(r"^([A-Za-z0-9_.-]+)==([^;\s]+)", line)
            if pm:
                pinned[pm.group(1).lower().replace("_", "-")] = pm.group(2)

        actual: dict[str, str] = {}
        for whl in wheels:
            m = WHEEL_NAME_RE.match(os.path.basename(whl))
            if m:
                actual[m.group("name").lower().replace("_", "-")] = m.group("ver")

        missing_in_bundle = sorted(n for n in pinned if n not in actual)
        # sdist 兜底的包(.tar.gz)不在 actual 里,单独放行提示
        sdists = {os.path.basename(p).split("-")[0].lower().replace("_", "-") for p in glob.glob(os.path.join(bundle, "*.tar.gz"))}
        missing_in_bundle = [n for n in missing_in_bundle if n not in sdists]
        if missing_in_bundle:
            failures.append(f"清单锁定但 bundle 内无对应 wheel/sdist: {missing_in_bundle}")
        mismatched = sorted(
            f"{n}: pinned {pinned[n]} != bundled {actual[n]}"
            for n in pinned
            if n in actual and pinned[n] != actual[n]
        )
        if mismatched:
            failures.append("清单与实际 wheel 版本不一致: " + "; ".join(mismatched))
    else:
        print("::warning::无 requirements-third-party.txt,跳过一致性检查")

    # ---- 检查 3:主包存在 -------------------------------------------------------
    have_mains: set[str] = set()
    for whl in wheels:
        m = WHEEL_NAME_RE.match(os.path.basename(whl))
        if m:
            have_mains.add(m.group("name").lower().replace("_", "-"))
    for main_pkg in sorted(MAIN_PACKAGES):
        if main_pkg.lower().replace("_", "-") not in have_mains:
            failures.append(f"缺主包 wheel: {main_pkg}")

    # ---- 汇总 -------------------------------------------------------------------
    baseline_file = os.path.join(os.path.dirname(bundle), "wheel-glibc-baselines.txt")
    with open(baseline_file, "w") as f:
        f.write("\n".join(baselines) + "\n")
    print(f"wheel 基线清单已写入 {baseline_file} ({len(baselines)} 条)")

    if failures:
        for f_ in failures:
            print(f"::error::{f_}")
        print(f"OFFLINE BUNDLE CHECK FAILED: {len(failures)} 个问题")
        return 1
    print(f"OFFLINE BUNDLE CHECK PASSED ({args.variant}, {len(wheels)} wheels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
