# -*- coding: utf-8 -*-
"""Resume text extractor for PDF and Word files.

Supported inputs:
    .pdf   -> pdfplumber first, pypdf fallback (with table extraction)
    .docx  -> python-docx, paragraphs and tables in document order
    .doc   -> convert to .docx via MS Word COM automation (Windows), then extract;
              exit code 4 with a hint if Word/pywin32 is unavailable

Usage:
    python extract_resume.py <input.pdf|input.docx|input.doc> [--json] [--out output.txt]

Output:
    - Default: plain text to stdout; PDF pages marked "=== Page N ===",
      Word content marked "=== Content ===" (tables flattened to "a | b | c" lines)
    - --json: JSON with {"file", "page_count"/"block_count", "total_chars", "method", ...}
    - --out: also write the plain text to a file (UTF-8)

Exit codes: 0 ok, 1 file not found, 2 unsupported/unreadable, 3 no text layer (PDF),
            4 .doc cannot be converted (no Word COM available).
"""
import argparse
import json
import sys
import os

def extract_pdf(path):
    pages, method = [], None
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                try:
                    for table in page.extract_tables():
                        for row in table:
                            cells = [c.strip() for c in row if c and c.strip()]
                            if cells:
                                text += "\n" + " | ".join(cells)
                except Exception:
                    pass
                pages.append({"page": i, "text": text.strip()})
        method = "pdfplumber"
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(path)
        for i, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append({"page": i, "text": text.strip()})
        method = "pypdf"
    return pages, method, "page"

def extract_docx(path):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(path)
    lines = []
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag
        if tag.endswith("}p"):
            t = Paragraph(child, doc).text.strip()
            if t:
                lines.append(t)
        elif tag.endswith("}tbl"):
            tbl = Table(child, doc)
            for row in tbl.rows:
                cells = []
                for c in row.cells:
                    v = c.text.strip().replace("\n", " ")
                    if v:
                        cells.append(v)
                if cells:
                    lines.append(" | ".join(cells))
    return [{"page": 1, "text": "\n".join(lines)}], "python-docx", "block"

def extract_doc(path):
    """Convert legacy .doc to .docx via MS Word COM, then extract.

    Word (esp. 2007/12.0) may raise spurious RPC errors on Close/Quit after a
    successful SaveAs. Therefore cleanup errors are swallowed and success is
    judged solely by whether the converted .docx was produced.
    """
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        raise RuntimeError("pywin32 not installed")
    import pythoncom
    pythoncom.CoInitialize()
    tmp_docx = os.path.splitext(os.path.abspath(path))[0] + "_converted.docx"
    if os.path.isfile(tmp_docx):
        try:
            os.remove(tmp_docx)
        except OSError:
            tmp_docx = os.path.splitext(os.path.abspath(path))[0] + "_c2.docx"
    word = None
    doc = None
    err = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(os.path.abspath(path), ReadOnly=True)
        # SaveAs (not SaveAs2: missing in Word <= 2007); FileFormat 12 = wdFormatXMLDocument (.docx)
        doc.SaveAs(tmp_docx, FileFormat=12)
    except Exception as e:
        err = e
    finally:
        for cleanup in (
            lambda: doc.Close(False),
            lambda: word.Quit(),
        ):
            try:
                if cleanup is not None:
                    cleanup()
            except Exception:
                pass
    if not err and not os.path.isfile(tmp_docx):
        err = RuntimeError("converted .docx was not produced")
    if err:
        raise RuntimeError(str(err))
    result = extract_docx(tmp_docx)
    try:
        os.remove(tmp_docx)
    except OSError:
        pass
    return result[0], result[1] + "+COM", result[2]

def main():
    ap = argparse.ArgumentParser(description="Extract text from a PDF/Word resume")
    ap.add_argument("file", help="path to the .pdf/.docx/.doc file")
    ap.add_argument("--json", action="store_true", help="output JSON metadata")
    ap.add_argument("--out", help="write extracted plain text to this file")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(json.dumps({"error": "file not found: %s" % args.file}, ensure_ascii=False))
        sys.exit(1)

    ext = os.path.splitext(args.file)[1].lower()
    if ext == ".pdf":
        pages, method, unit = extract_pdf(args.file)
    elif ext == ".docx":
        pages, method, unit = extract_docx(args.file)
    elif ext == ".doc":
        try:
            pages, method, unit = extract_doc(args.file)
        except Exception as e:
            print(json.dumps({
                "error": "cannot convert legacy .doc: %s" % e,
                "hint": "Ask the user to re-save as .docx or .pdf, or install pywin32 into the managed venv.",
            }, ensure_ascii=False))
            sys.exit(4)
    else:
        print(json.dumps({"error": "unsupported file type: %s (use .pdf/.docx/.doc)" % ext}, ensure_ascii=False))
        sys.exit(2)

    full_text = "\n\n".join(
        "=== %s %d ===\n%s" % ("Page" if unit == "page" else "Content", p["page"], p["text"])
        for p in pages)
    total = sum(len(p["text"]) for p in pages)

    if total < 30 and ext == ".pdf":
        print(json.dumps({
            "file": os.path.abspath(args.file),
            "page_count": len(pages),
            "total_chars": total,
            "method": method,
            "has_text_layer": False,
            "hint": "No text layer detected. Treat the PDF as scanned: convert pages to images and read them visually.",
        }, ensure_ascii=False))
        sys.exit(3)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(full_text)

    if args.json:
        count_key = "page_count" if unit == "page" else "block_count"
        meta = {
            "file": os.path.abspath(args.file),
            count_key: len(pages),
            "total_chars": total,
            "method": method,
        }
        if ext == ".pdf":
            meta["has_text_layer"] = True
        print(json.dumps(meta, ensure_ascii=False))
    else:
        sys.stdout.buffer.write(full_text.encode("utf-8"))

if __name__ == "__main__":
    main()
