"""TDEE helper for GymBuddy.skill — Mifflin–St Jeor BMR × activity factor."""

from __future__ import annotations

import argparse
from typing import Literal


def calculate_tdee(
    weight: float,
    height: float,
    age: int,
    gender: Literal["male", "female"],
    activity_level: float,
) -> float:
    """
    计算每日总能量消耗 (TDEE)。
    weight: kg, height: cm, age: 岁
    activity_level: 约 1.2（久坐）到 1.9（高强度运动员）
    """
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    return round(bmr * activity_level, 1)


def _main() -> None:
    p = argparse.ArgumentParser(description="估算 TDEE（Mifflin–St Jeor × 活动系数）")
    p.add_argument("--weight", type=float, required=True, help="体重 kg")
    p.add_argument("--height", type=float, required=True, help="身高 cm")
    p.add_argument("--age", type=int, required=True, help="年龄")
    p.add_argument("--gender", choices=("male", "female"), required=True)
    p.add_argument(
        "--activity",
        type=float,
        required=True,
        help="活动系数，例如 1.2 久坐、1.375 轻度、1.55 中度、1.725 重",
    )
    args = p.parse_args()
    tdee = calculate_tdee(args.weight, args.height, args.age, args.gender, args.activity)
    print(f"TDEE (kcal/day, estimate): {tdee}")


if __name__ == "__main__":
    _main()
