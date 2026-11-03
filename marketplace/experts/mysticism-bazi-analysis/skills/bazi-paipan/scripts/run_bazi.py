#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
八字排盘技能 Wrapper
====================
供 OpenClaw / Hermes 等 Agent 框架调用的便捷入口。

支持两种调用方式：
  1. 命令行参数（与 bazi_calculator.py 相同）
  2. JSON 参数（通过 --json 传入 JSON 字符串或文件路径）

用法示例：
  # 方式1：标准命令行参数
  python run_bazi.py --time "1990-05-15 08:30" --location 成都 --gender 男

  # 方式2：JSON 字符串
  python run_bazi.py --json '{"time":"1990-05-15 08:30","location":"成都","gender":"男"}'

  # 方式3：JSON 文件
  python run_bazi.py --json ./input.json

返回：将结果 JSON 打印到 stdout（或写入 --output 指定的文件）
"""

import sys
import os
import json
import argparse

# 确保 scripts 目录在 Python 路径中
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from bazi_calculator import calculate_bazi, print_bazi


def parse_json_input(json_arg: str) -> dict:
    """解析 JSON 参数（字符串或文件路径）"""
    # 判断是文件路径还是 JSON 字符串
    if os.path.isfile(json_arg):
        with open(json_arg, encoding="utf-8") as f:
            return json.load(f)
    else:
        return json.loads(json_arg)


def main():
    parser = argparse.ArgumentParser(
        description="八字排盘技能 Wrapper v2.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python run_bazi.py --time "1990-05-15 08:30" --gender 男
  python run_bazi.py --time "1990-05-15 08:30" --location 成都 --gender 女 --name 李四 --liunian 2026
  python run_bazi.py --json '{"time":"1990-05-15 08:30","gender":"男","location":"成都"}'
        """
    )

    # 标准命令行参数
    parser.add_argument("--time",     type=str, default=None, help="出生时间，格式：YYYY-MM-DD HH:MM")
    parser.add_argument("--location", type=str, default="北京", help="出生地（城市名或经度,纬度），默认北京")
    parser.add_argument("--gender",   type=str, default="男", choices=["男", "女"], help="性别，默认男")
    parser.add_argument("--name",     type=str, default="", help="姓名（可选）")
    parser.add_argument("--liunian",  type=str, default=None, help="流年年份 YYYY，默认当前年份")
    parser.add_argument("--output",   type=str, default=None, help="输出文件路径，默认输出到 stdout")

    # JSON 模式
    parser.add_argument("--json", type=str, default=None,
                        help="JSON 参数字符串或 JSON 文件路径，覆盖其他命令行参数")

    args = parser.parse_args()

    # JSON 模式：解析并覆盖参数
    if args.json:
        try:
            params = parse_json_input(args.json)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"[错误] 无法解析 --json 参数：{e}", file=sys.stderr)
            sys.exit(1)

        birth_time = params.get("time") or params.get("birth_time")
        location   = params.get("location", "北京")
        gender     = params.get("gender", "男")
        name       = params.get("name", "")
        liunian    = params.get("liunian") or params.get("year")
        output     = params.get("output", args.output)
    else:
        birth_time = args.time
        location   = args.location
        gender     = args.gender
        name       = args.name
        liunian    = args.liunian
        output     = args.output

    # 校验必填项
    if not birth_time:
        print("[错误] 缺少必填参数：出生时间（--time 或 JSON 中的 time 字段）", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    # 执行计算
    try:
        result = calculate_bazi(birth_time, location, gender, name, liunian)
    except Exception as e:
        print(f"[错误] 八字计算失败：{e}", file=sys.stderr)
        sys.exit(1)

    # 输出结果
    print_bazi(result, output)


if __name__ == "__main__":
    main()
