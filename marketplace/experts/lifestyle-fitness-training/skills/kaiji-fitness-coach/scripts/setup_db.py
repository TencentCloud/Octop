#!/usr/bin/env python3
"""
Free Exercise DB 数据库设置脚本

功能：
- 检查数据库是否存在
- 从 Gitee 克隆/下载数据库
- 更新数据库到最新版本
- 验证数据库完整性

跨平台兼容：Windows / Linux / macOS
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from urllib.request import urlopen, urlretrieve
from urllib.error import URLError

# 数据库信息
DB_REPO_URL = "https://gitee.com/kaiji1126/free-exercise-db.git"
DB_ARCHIVE_URL = "https://gitee.com/kaiji1126/free-exercise-db/repository/archive/main.zip"
DB_NAME = "free-exercise-db"

def get_skill_dir():
    """获取技能目录路径"""
    # 脚本在 scripts/ 目录下，技能目录是上一级
    return Path(__file__).parent.parent.resolve()

def get_db_path():
    """获取数据库路径"""
    return get_skill_dir() / DB_NAME

def check_db_exists():
    """检查数据库是否存在"""
    db_path = get_db_path()
    exercises_path = db_path / "exercises"
    dist_path = db_path / "dist" / "exercises.json"
    
    return exercises_path.exists() or dist_path.exists()

def check_git_available():
    """检查 git 是否可用"""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def clone_with_git():
    """使用 git 克隆数据库"""
    db_path = get_db_path()
    
    print(f"正在从 Gitee 克隆数据库...")
    print(f"仓库: {DB_REPO_URL}")
    
    try:
        result = subprocess.run(
            ["git", "clone", DB_REPO_URL, str(db_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            print("✓ 数据库克隆成功！")
            return True
        else:
            print(f"✗ 克隆失败: {result.stderr}")
            return False
            
    except subprocess.SubprocessError as e:
        print(f"✗ 克隆出错: {e}")
        return False

def download_with_urllib():
    """使用 urllib 下载数据库压缩包"""
    import zipfile
    import tempfile
    
    db_path = get_db_path()
    temp_dir = Path(tempfile.mkdtemp())
    
    print(f"正在从 Gitee 下载数据库...")
    print(f"地址: {DB_ARCHIVE_URL}")
    
    try:
        zip_path = temp_dir / "db.zip"
        urlretrieve(DB_ARCHIVE_URL, zip_path)
        print("✓ 下载完成")
        
        # 解压
        print("正在解压...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # 找到解压后的目录（通常带有 -main 后缀）
        extracted_dirs = [d for d in temp_dir.iterdir() if d.is_dir()]
        if not extracted_dirs:
            print("✗ 解压失败：未找到目录")
            return False
        
        source_dir = extracted_dirs[0]
        
        # 移动到目标位置
        if db_path.exists():
            shutil.rmtree(db_path)
        
        shutil.move(str(source_dir), str(db_path))
        print("✓ 解压完成")
        
        # 清理临时文件
        shutil.rmtree(temp_dir)
        
        return True
        
    except (URLError, zipfile.BadZipFile, OSError) as e:
        print(f"✗ 下载/解压失败: {e}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        return False

def setup_database(force=False):
    """设置数据库"""
    db_path = get_db_path()
    
    # 检查是否已存在
    if check_db_exists() and not force:
        print(f"✓ 数据库已存在: {db_path}")
        print("  使用 --force 重新下载")
        return True
    
    # 如果强制更新，先删除旧数据库
    if force and db_path.exists():
        print("删除旧数据库...")
        shutil.rmtree(db_path)
    
    # 优先使用 git
    if check_git_available():
        print("检测到 git，使用 git 克隆...")
        if clone_with_git():
            return True
        print("git 克隆失败，尝试直接下载...")
    
    # 回退到直接下载
    return download_with_urllib()

def update_database():
    """更新数据库到最新版本"""
    db_path = get_db_path()
    
    if not db_path.exists():
        print("数据库不存在，正在下载...")
        return setup_database()
    
    # 检查是否是 git 仓库
    git_dir = db_path / ".git"
    if git_dir.exists():
        print("正在更新数据库（git pull）...")
        try:
            result = subprocess.run(
                ["git", "-C", str(db_path), "pull"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✓ 数据库更新成功！")
                return True
            else:
                print(f"✗ 更新失败: {result.stderr}")
                return False
                
        except subprocess.SubprocessError as e:
            print(f"✗ 更新出错: {e}")
            return False
    else:
        print("数据库不是 git 仓库，重新下载...")
        return setup_database(force=True)

def verify_database():
    """验证数据库完整性"""
    db_path = get_db_path()
    exercises_path = db_path / "exercises"
    dist_path = db_path / "dist" / "exercises.json"
    
    print(f"验证数据库: {db_path}")
    
    # 检查目录存在
    if not db_path.exists():
        print("✗ 数据库目录不存在")
        return False
    
    # 检查 exercises 目录
    if exercises_path.exists():
        exercise_count = len(list(exercises_path.glob("*")))
        print(f"✓ 找到 {exercise_count} 个动作目录")
        
        # 抽查几个动作文件
        sample_dirs = list(exercises_path.glob("*"))[:3]
        for d in sample_dirs:
            exercise_json = d / "exercise.json"
            if exercise_json.exists():
                try:
                    with open(exercise_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    print(f"  ✓ {data.get('name', d.name)}")
                except (json.JSONDecodeError, IOError) as e:
                    print(f"  ✗ {d.name}: {e}")
                    return False
        return True
    
    # 检查 dist/exercises.json
    if dist_path.exists():
        try:
            with open(dist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                print(f"✓ 找到合并文件，包含 {len(data)} 个动作")
                return True
            else:
                print("✗ 合并文件格式错误")
                return False
        except (json.JSONDecodeError, IOError) as e:
            print(f"✗ 读取合并文件失败: {e}")
            return False
    
    print("✗ 数据库不完整：缺少 exercises 目录和 dist/exercises.json")
    return False

def get_db_info():
    """获取数据库信息"""
    db_path = get_db_path()
    
    if not db_path.exists():
        print("数据库不存在")
        return
    
    print(f"数据库路径: {db_path}")
    
    # 统计动作数量
    exercises_path = db_path / "exercises"
    if exercises_path.exists():
        count = len(list(exercises_path.glob("*")))
        print(f"动作数量: {count}")
    
    # 检查 git 信息
    git_dir = db_path / ".git"
    if git_dir.exists():
        print("数据源: git 仓库")
        try:
            result = subprocess.run(
                ["git", "-C", str(db_path), "log", "-1", "--format=%h %s"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"最新提交: {result.stdout.strip()}")
        except subprocess.SubprocessError:
            pass
    else:
        print("数据源: 压缩包下载")

def main():
    parser = argparse.ArgumentParser(
        description="Free Exercise DB 数据库设置工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python setup_db.py              # 设置数据库（如果不存在）
  python setup_db.py --force      # 强制重新下载
  python setup_db.py --update     # 更新到最新版本
  python setup_db.py --verify     # 验证数据库完整性
  python setup_db.py --info       # 显示数据库信息
  python setup_db.py --check      # 检查数据库是否存在
        """
    )
    
    parser.add_argument("--force", action="store_true", help="强制重新下载")
    parser.add_argument("--update", action="store_true", help="更新到最新版本")
    parser.add_argument("--verify", action="store_true", help="验证数据库完整性")
    parser.add_argument("--info", action="store_true", help="显示数据库信息")
    parser.add_argument("--check", action="store_true", help="检查数据库是否存在")
    
    args = parser.parse_args()
    
    # 检查模式
    if args.check:
        exists = check_db_exists()
        print(f"数据库存在: {exists}")
        if exists:
            print(f"路径: {get_db_path()}")
        sys.exit(0 if exists else 1)
    
    # 信息模式
    if args.info:
        get_db_info()
        sys.exit(0)
    
    # 验证模式
    if args.verify:
        success = verify_database()
        sys.exit(0 if success else 1)
    
    # 更新模式
    if args.update:
        success = update_database()
        sys.exit(0 if success else 1)
    
    # 设置模式（默认）
    success = setup_database(force=args.force)
    if success:
        verify_database()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
