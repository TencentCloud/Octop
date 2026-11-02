"""读取 Word (.docx) 文件文本内容"""
import sys
from pathlib import Path
from docx import Document


def read_docx(file_path: str) -> str:
    """读取 DocX 文件内容

    Args:
        file_path: .docx 文件路径

    Returns:
        纯文本内容，保留段落结构
    """
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] 文件不存在: {file_path}")
        sys.exit(1)

    if path.suffix.lower() not in (".docx", ".doc"):
        print(f"[WARN] 不是 .docx 文件: {file_path}")

    doc = Document(path)
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)

    result = "\n".join(paragraphs)
    print(result)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python read_docx.py <文件路径>")
        sys.exit(1)
    read_docx(sys.argv[1])
