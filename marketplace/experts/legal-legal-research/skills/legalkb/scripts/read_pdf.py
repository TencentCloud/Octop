"""读取 PDF 文件文本内容"""
import sys
import pdfplumber
from pathlib import Path


def read_pdf(file_path: str, page_range: str = None) -> str:
    """读取 PDF 内容

    Args:
        file_path: PDF 文件路径
        page_range: 页码范围，如 "1-10"，None 表示全部

    Returns:
        PDF 纯文本内容
    """
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] 文件不存在: {file_path}")
        sys.exit(1)

    pages = None
    if page_range:
        try:
            start, end = page_range.split("-")
            pages = range(int(start.strip()) - 1, int(end.strip()))
        except Exception:
            print("[WARN] 页码范围格式错误，将读取全部页面")

    texts = []
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages) if pages is None else len(pages)
        target_pages = list(pages) if pages else range(len(pdf.pages))

        for i, page_num in enumerate(target_pages):
            if page_num >= len(pdf.pages):
                break
            page = pdf.pages[page_num]
            text = page.extract_text()
            if text:
                texts.append(f"--- 第 {page_num + 1} 页 ---\n{text}")

    result = "\n\n".join(texts)
    print(result)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python read_pdf.py <文件路径> [页码范围，如 1-10]")
        sys.exit(1)
    file_path = sys.argv[1]
    page_range = sys.argv[2] if len(sys.argv) > 2 else None
    read_pdf(file_path, page_range)
