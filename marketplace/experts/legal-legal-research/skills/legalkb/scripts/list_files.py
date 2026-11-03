"""列出目录下所有支持的法律文件"""
import sys
import os
from pathlib import Path


def list_files(directory: str) -> None:
    """列出所有 PDF 和 Word 文件"""
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"[ERROR] 目录不存在: {directory}")
        sys.exit(1)

    supported = (".pdf", ".docx", ".doc")
    files = []
    for root, _, filenames in os.walk(dir_path):
        for fname in filenames:
            if Path(fname).suffix.lower() in supported:
                fpath = Path(root) / fname
                rel = fpath.relative_to(dir_path)
                files.append(str(fpath))

    if not files:
        print(f"[INFO] 目录中未找到 PDF 或 Word 文件: {directory}")
    else:
        print(f"[共 {len(files)} 个文件]\n")
        for f in sorted(files):
            print(f)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python list_files.py <目录路径>")
        sys.exit(1)
    list_files(sys.argv[1])
