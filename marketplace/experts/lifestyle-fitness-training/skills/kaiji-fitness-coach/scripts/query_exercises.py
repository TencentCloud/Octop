#!/usr/bin/env python3
"""
Free Exercise DB 查询脚本

功能：
- 按肌群、器械、难度等条件筛选动作
- 查询单个动作详情
- 输出 JSON 或表格格式

跨平台兼容：Windows / Linux / macOS
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# 数据库路径
DB_NAME = "free-exercise-db"

def get_skill_dir() -> Path:
    """获取技能目录路径"""
    return Path(__file__).parent.parent.resolve()

def get_db_path() -> Path:
    """获取数据库路径"""
    return get_skill_dir() / DB_NAME

def get_exercises_path() -> Path:
    """获取 exercises 目录路径"""
    return get_db_path() / "exercises"

def get_dist_path() -> Path:
    """获取合并文件路径"""
    return get_db_path() / "dist" / "exercises.json"

def check_db_exists() -> bool:
    """检查数据库是否存在"""
    return get_exercises_path().exists() or get_dist_path().exists()

def load_all_exercises() -> List[Dict[str, Any]]:
    """加载所有动作数据"""
    exercises = []
    
    # 优先使用合并文件
    dist_path = get_dist_path()
    if dist_path.exists():
        with open(dist_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 回退到逐个读取
    exercises_path = get_exercises_path()
    if not exercises_path.exists():
        return []
    
    for exercise_dir in exercises_path.iterdir():
        if exercise_dir.is_dir():
            exercise_json = exercise_dir / "exercise.json"
            if exercise_json.exists():
                try:
                    with open(exercise_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # 添加图片路径
                        images_dir = exercise_dir / "images"
                        if images_dir.exists():
                            data["imagePaths"] = [
                                str(images_dir / img) 
                                for img in images_dir.glob("*.jpg")
                            ]
                        exercises.append(data)
                except (json.JSONDecodeError, IOError):
                    continue
    
    return exercises

def filter_exercises(
    exercises: List[Dict[str, Any]],
    muscle: Optional[str] = None,
    equipment: Optional[str] = None,
    level: Optional[str] = None,
    force: Optional[str] = None,
    mechanic: Optional[str] = None,
    category: Optional[str] = None,
    name: Optional[str] = None,
    exercise_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """按条件筛选动作"""
    filtered = exercises
    
    # 按 ID 精确匹配
    if exercise_id:
        filtered = [e for e in filtered if e.get("id", "").lower() == exercise_id.lower()]
        return filtered
    
    # 按名称模糊匹配
    if name:
        name_lower = name.lower()
        filtered = [e for e in filtered if name_lower in e.get("name", "").lower()]
    
    # 按肌群筛选
    if muscle:
        muscle_lower = muscle.lower()
        filtered = [
            e for e in filtered 
            if muscle_lower in [m.lower() for m in e.get("primaryMuscles", [])]
            or muscle_lower in [m.lower() for m in e.get("secondaryMuscles", [])]
        ]
    
    # 按器械筛选
    if equipment:
        equipment_lower = equipment.lower()
        filtered = [
            e for e in filtered 
            if e.get("equipment", "").lower() == equipment_lower
        ]
    
    # 按难度筛选
    if level:
        level_lower = level.lower()
        filtered = [
            e for e in filtered 
            if e.get("level", "").lower() == level_lower
        ]
    
    # 按发力类型筛选
    if force:
        force_lower = force.lower()
        filtered = [
            e for e in filtered 
            if e.get("force", "").lower() == force_lower
        ]
    
    # 按动作类型筛选
    if mechanic:
        mechanic_lower = mechanic.lower()
        filtered = [
            e for e in filtered 
            if e.get("mechanic", "").lower() == mechanic_lower
        ]
    
    # 按训练类别筛选
    if category:
        category_lower = category.lower()
        filtered = [
            e for e in filtered 
            if e.get("category", "").lower() == category_lower
        ]
    
    return filtered

def format_exercise_brief(exercise: Dict[str, Any]) -> str:
    """格式化动作简要信息"""
    name = exercise.get("name", "Unknown")
    level = exercise.get("level", "-")
    equipment = exercise.get("equipment", "-")
    primary = ", ".join(exercise.get("primaryMuscles", []))
    secondary = ", ".join(exercise.get("secondaryMuscles", []))
    
    return f"{name} | {level} | {equipment} | {primary}" + (
        f" (+{secondary})" if secondary else ""
    )

def format_exercise_detail(exercise: Dict[str, Any]) -> str:
    """格式化动作详细信息"""
    lines = []
    
    # 标题
    name = exercise.get("name", "Unknown")
    exercise_id = exercise.get("id", "")
    lines.append(f"# {name}")
    lines.append(f"**ID**: {exercise_id}")
    lines.append("")
    
    # 基本信息
    lines.append("## 基本信息")
    lines.append(f"- **难度**: {exercise.get('level', '-')}")
    lines.append(f"- **器械**: {exercise.get('equipment', '-')}")
    lines.append(f"- **发力类型**: {exercise.get('force', '-')}")
    lines.append(f"- **动作类型**: {exercise.get('mechanic', '-')}")
    lines.append(f"- **训练类别**: {exercise.get('category', '-')}")
    
    primary = exercise.get("primaryMuscles", [])
    secondary = exercise.get("secondaryMuscles", [])
    lines.append(f"- **主要肌群**: {', '.join(primary) if primary else '-'}")
    lines.append(f"- **次要肌群**: {', '.join(secondary) if secondary else '-'}")
    lines.append("")
    
    # 动作说明
    instructions = exercise.get("instructions", [])
    if instructions:
        lines.append("## 动作说明")
        for i, step in enumerate(instructions, 1):
            lines.append(f"{i}. {step}")
        lines.append("")
    
    # 图片路径
    image_paths = exercise.get("imagePaths", [])
    if image_paths:
        lines.append("## 示范图片")
        for path in image_paths:
            lines.append(f"- {path}")
        lines.append("")
    
    return "\n".join(lines)

def output_table(exercises: List[Dict[str, Any]]):
    """输出表格格式"""
    if not exercises:
        print("没有找到匹配的动作")
        return
    
    print(f"找到 {len(exercises)} 个动作：\n")
    
    # 表头
    print("| # | 名称 | 难度 | 器械 | 主要肌群 |")
    print("|---|------|------|------|----------|")
    
    # 表格内容
    for i, exercise in enumerate(exercises, 1):
        name = exercise.get("name", "-")
        level = exercise.get("level", "-")
        equipment = exercise.get("equipment", "-")
        primary = ", ".join(exercise.get("primaryMuscles", [])) or "-"
        
        print(f"| {i} | {name} | {level} | {equipment} | {primary} |")

def output_json(exercises: List[Dict[str, Any]]):
    """输出 JSON 格式"""
    print(json.dumps(exercises, ensure_ascii=False, indent=2))

def output_ids(exercises: List[Dict[str, Any]]):
    """仅输出 ID 列表"""
    for exercise in exercises:
        print(exercise.get("id", ""))

def output_detail(exercise: Dict[str, Any]):
    """输出详细信息"""
    print(format_exercise_detail(exercise))

def main():
    parser = argparse.ArgumentParser(
        description="Free Exercise DB 查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
查询参数:
  --muscle      目标肌群 (chest, lats, quadriceps, biceps, etc.)
  --equipment   器械类型 (dumbbell, barbell, "body only", machine, etc.)
  --level       难度等级 (beginner, intermediate, expert)
  --force       发力类型 (push, pull, static)
  --mechanic    动作类型 (compound, isolation)
  --category    训练类别 (strength, cardio, stretching, etc.)
  --name        动作名称模糊匹配
  --id          动作 ID 精确匹配

输出格式:
  --format      输出格式 (table, json, ids, detail)
  --detailed    详细信息模式（与 --id 配合使用）

示例:
  # 查询胸部哑铃动作
  python query_exercises.py --muscle chest --equipment dumbbell
  
  # 查询推类动作
  python query_exercises.py --force push --equipment dumbbell
  
  # 查询单个动作详情
  python query_exercises.py --id "Incline_Dumbbell_Press" --detailed
  
  # 输出 JSON 格式
  python query_exercises.py --muscle chest --format json
  
  # 仅输出 ID 列表
  python query_exercises.py --equipment dumbbell --format ids
  
  # 检查数据库
  python query_exercises.py --check-db
        """
    )
    
    # 查询参数
    parser.add_argument("--muscle", help="目标肌群")
    parser.add_argument("--equipment", help="器械类型")
    parser.add_argument("--level", help="难度等级")
    parser.add_argument("--force", help="发力类型")
    parser.add_argument("--mechanic", help="动作类型")
    parser.add_argument("--category", help="训练类别")
    parser.add_argument("--name", help="动作名称（模糊匹配）")
    parser.add_argument("--id", dest="exercise_id", help="动作 ID（精确匹配）")
    
    # 输出参数
    parser.add_argument("--format", choices=["table", "json", "ids", "detail"], 
                        default="table", help="输出格式")
    parser.add_argument("--detailed", action="store_true", help="详细信息模式")
    
    # 工具参数
    parser.add_argument("--check-db", action="store_true", help="检查数据库是否存在")
    parser.add_argument("--list-muscles", action="store_true", help="列出所有肌群")
    parser.add_argument("--list-equipment", action="store_true", help="列出所有器械")
    
    args = parser.parse_args()
    
    # 检查数据库
    if args.check_db:
        exists = check_db_exists()
        print(f"数据库存在: {exists}")
        if exists:
            print(f"路径: {get_db_path()}")
        sys.exit(0 if exists else 1)
    
    # 列出枚举值
    if args.list_muscles or args.list_equipment:
        exercises = load_all_exercises()
        
        if args.list_muscles:
            muscles = set()
            for e in exercises:
                muscles.update(e.get("primaryMuscles", []))
                muscles.update(e.get("secondaryMuscles", []))
            print("可用肌群:")
            for m in sorted(muscles):
                print(f"  - {m}")
        
        if args.list_equipment:
            equipment = set()
            for e in exercises:
                eq = e.get("equipment")
                if eq:
                    equipment.add(eq)
            print("可用器械:")
            for eq in sorted(equipment):
                print(f"  - {eq}")
        
        sys.exit(0)
    
    # 检查数据库
    if not check_db_exists():
        print("错误：数据库不存在")
        print("请先运行: python scripts/setup_db.py")
        sys.exit(1)
    
    # 加载并筛选
    exercises = load_all_exercises()
    
    filtered = filter_exercises(
        exercises,
        muscle=args.muscle,
        equipment=args.equipment,
        level=args.level,
        force=args.force,
        mechanic=args.mechanic,
        category=args.category,
        name=args.name,
        exercise_id=args.exercise_id
    )
    
    # 输出
    if not filtered:
        print("没有找到匹配的动作")
        sys.exit(0)
    
    # 详细模式
    if args.detailed and len(filtered) == 1:
        output_detail(filtered[0])
        sys.exit(0)
    
    # 格式输出
    if args.format == "table":
        output_table(filtered)
    elif args.format == "json":
        output_json(filtered)
    elif args.format == "ids":
        output_ids(filtered)
    elif args.format == "detail":
        for exercise in filtered:
            output_detail(exercise)
            print("---")

if __name__ == "__main__":
    main()
