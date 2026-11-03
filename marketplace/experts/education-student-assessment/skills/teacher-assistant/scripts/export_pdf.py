#!/usr/bin/env python3
"""
Word (.docx) → PDF 导出工具
将已生成的 .docx 文档转换为 PDF 格式，支持 Windows/macOS/Linux。

用法：
  python scripts/export_pdf.py --input <docx文件路径> [--output <pdf路径>]
  python scripts/export_pdf.py input.docx
"""

import sys
import subprocess
import shutil
from pathlib import Path


def docx_to_pdf_windows(docx_path: Path, pdf_path: Path) -> bool:
    """Windows 下使用 Microsoft Word COM 接口转换"""
    try:
        import win32com.client
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(docx_path.resolve()))
        doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)  # 17 = wdFormatPDF
        doc.Close()
        word.Quit()
        return True
    except ImportError:
        pass

    # 备选：使用 docx2pdf 库
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        return True
    except ImportError:
        pass

    # 备选：LibreOffice（如果已安装）
    for lo_path in [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]:
        if Path(lo_path).exists():
            result = subprocess.run(
                [lo_path, '--headless', '--convert-to', 'pdf',
                 '--outdir', str(pdf_path.parent), str(docx_path)],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                # LibreOffice 会在同目录生成同名 pdf，需重命名
                generated = pdf_path.parent / (docx_path.stem + '.pdf')
                if generated.exists() and generated != pdf_path:
                    generated.rename(pdf_path)
                return True

    return False


def docx_to_pdf_macos(docx_path: Path, pdf_path: Path) -> bool:
    """macOS 下使用 LibreOffice 或 Word 转换"""
    # LibreOffice
    for lo_path in [
        '/Applications/LibreOffice.app/Contents/MacOS/soffice',
        shutil.which('libreoffice') or '',
        shutil.which('soffice') or '',
    ]:
        if lo_path and Path(lo_path).exists():
            result = subprocess.run(
                [lo_path, '--headless', '--convert-to', 'pdf',
                 '--outdir', str(pdf_path.parent), str(docx_path)],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                generated = pdf_path.parent / (docx_path.stem + '.pdf')
                if generated.exists() and generated != pdf_path:
                    generated.rename(pdf_path)
                return True

    # docx2pdf
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        return True
    except ImportError:
        pass

    return False


def docx_to_pdf_linux(docx_path: Path, pdf_path: Path) -> bool:
    """Linux 下使用 LibreOffice 转换"""
    for cmd in ['libreoffice', 'soffice']:
        lo = shutil.which(cmd)
        if lo:
            result = subprocess.run(
                [lo, '--headless', '--convert-to', 'pdf',
                 '--outdir', str(pdf_path.parent), str(docx_path)],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                generated = pdf_path.parent / (docx_path.stem + '.pdf')
                if generated.exists() and generated != pdf_path:
                    generated.rename(pdf_path)
                return True

    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        return True
    except ImportError:
        pass

    return False


def convert_to_pdf(docx_path: str, pdf_path: str = None) -> Path:
    """
    主转换函数。自动检测操作系统并选择合适的方法。
    返回生成的 PDF 路径。
    """
    docx = Path(docx_path).resolve()
    if not docx.exists():
        print(f"[错误] 文件不存在：{docx}", file=sys.stderr)
        sys.exit(1)

    if pdf_path:
        pdf = Path(pdf_path).resolve()
    else:
        pdf = docx.with_suffix('.pdf')

    print(f"[→] 正在将 {docx.name} 转换为 PDF ...")

    import platform
    os_name = platform.system().lower()
    success = False

    if 'windows' in os_name:
        success = docx_to_pdf_windows(docx, pdf)
    elif 'darwin' in os_name:
        success = docx_to_pdf_macos(docx, pdf)
    else:
        success = docx_to_pdf_linux(docx, pdf)

    if success and pdf.exists():
        print(f"[✓] PDF 已生成：{pdf}")
        return pdf
    else:
        print("[✗] PDF 转换失败。请确保已安装以下任一工具：", file=sys.stderr)
        print("    • Microsoft Word（Windows/macOS）", file=sys.stderr)
        print("    • LibreOffice（跨平台，免费）：https://www.libreoffice.org/", file=sys.stderr)
        print("    • Python 库 docx2pdf：pip install docx2pdf", file=sys.stderr)
        sys.exit(1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Word → PDF 导出工具")
    parser.add_argument('input',  nargs='?', help='docx 文件路径（位置参数）')
    parser.add_argument('--input',  dest='input_flag',  help='docx 文件路径（--input 标志）')
    parser.add_argument('--output', dest='output_flag', help='pdf 输出路径（默认与 docx 同目录同名）')
    args = parser.parse_args()

    docx_path = args.input_flag or args.input
    if not docx_path:
        print("用法：python export_pdf.py <input.docx> [--output <output.pdf>]")
        sys.exit(1)

    convert_to_pdf(docx_path, args.output_flag)


if __name__ == '__main__':
    main()
