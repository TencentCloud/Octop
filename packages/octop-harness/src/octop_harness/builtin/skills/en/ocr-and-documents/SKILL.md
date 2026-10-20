---
name: ocr-and-documents
description: "Extract text from PDFs/scans (pymupdf, marker-pdf)."
version: 2.3.0
author: Octop
license: MIT
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "文档提取"
      en: "OCR & Documents"
    summary:
      zh: "从 PDF 和扫描件中提取文本。"
      en: "Extract text from PDFs and scanned documents."
  harness:
    emoji: "📃"
    tags: [PDF, Documents, Research, Arxiv, Text-Extraction, OCR]
    related_skills: [powerpoint]
---

# PDF & Document Extraction

## Harness-agent tools

This skill was ported from Octop. Use these harness/deepagents tools:

| Concept | Tool |
|---------|------|
| Shell | `execute` |
| Read / write / edit files | `read_file`, `write_file`, `edit_file` |
| Find files / search content | `glob`, `grep` |
| Fetch URLs | `web_fetch` |
| Browser automation | `browser_use` |
| Subagent work | `task` |
| Memory | `memory_store`, `memory_recall`, `memory_search` |

Builtin skill files live under `/_builtin_skills/<name>/`. User-installed skills live under `/skills/<name>/`.

For DOCX: use `python-docx` (parses actual document structure, far better than OCR).
For PPTX: see the `powerpoint` skill (uses `python-pptx` with full slide/notes support).
This skill covers **PDFs and scanned documents**.

## Step 1: Remote URL Available?

If the document has a URL, **try `web_fetch` first** for HTML pages and text-based content:

```
web_fetch(url="https://arxiv.org/abs/2402.03300")
```

`web_fetch` converts HTML to markdown. For binary PDFs it returns plain text or may fail — fall back to local extraction below.

Only use local extraction when: the file is local, `web_fetch` fails or returns unusable output, or you need batch processing / OCR.

## Step 2: Choose Local Extractor

| Feature | pymupdf (~25MB) | marker-pdf (~3-5GB) |
|---------|-----------------|---------------------|
| **Text-based PDF** | ✅ | ✅ |
| **Scanned PDF (OCR)** | ❌ | ✅ (90+ languages) |
| **Tables** | ✅ (basic) | ✅ (high accuracy) |
| **Equations / LaTeX** | ❌ | ✅ |
| **Code blocks** | ❌ | ✅ |
| **Forms** | ❌ | ✅ |
| **Headers/footers removal** | ❌ | ✅ |
| **Reading order detection** | ❌ | ✅ |
| **Images extraction** | ✅ (embedded) | ✅ (with context) |
| **Images → text (OCR)** | ❌ | ✅ |
| **EPUB** | ✅ | ✅ |
| **Markdown output** | ✅ (via pymupdf4llm) | ✅ (native, higher quality) |
| **Install size** | ~25MB | ~3-5GB (PyTorch + models) |
| **Speed** | Instant | ~1-14s/page (CPU), ~0.2s/page (GPU) |

**Decision**: Use pymupdf unless you need OCR, equations, forms, or complex layout analysis.

If the user needs marker capabilities but the system lacks ~5GB free disk:
> "This document needs OCR/advanced extraction (marker-pdf), which requires ~5GB for PyTorch and models. Your system has [X]GB free. Options: free up space, provide a URL so I can use web_fetch, or I can try pymupdf which works for text-based PDFs but not scanned documents or equations."

---

## pymupdf (lightweight)

```bash
pip install pymupdf pymupdf4llm
```

**Via helper script** (from workspace root after `init_workspace`):

```bash
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --markdown
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --tables
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --images out/
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --metadata
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --pages 0-4
```

**Inline**:
```bash
python3 -c "
import pymupdf
doc = pymupdf.open('document.pdf')
for page in doc:
    print(page.get_text())
"
```

---

## marker-pdf (high-quality OCR)

```bash
# Check disk space first
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py --check

pip install marker-pdf
```

**Via helper script**:
```bash
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf --json
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf --output_dir out/
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py scanned.pdf
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf --use_llm
```

**CLI** (installed with marker-pdf):
```bash
marker_single document.pdf --output_dir ./output
marker /path/to/folder --workers 4    # Batch
```

---

## Arxiv Papers

```
# Abstract (HTML → markdown via web_fetch)
web_fetch(url="https://arxiv.org/abs/2402.03300")

# Full paper PDF — download then extract locally (see pymupdf / marker above)
execute(command="curl -L -o paper.pdf https://arxiv.org/pdf/2402.03300")
```

For paper search, use configured search tools (`tavily_search`, `searchfree_search`, etc.) or `web_fetch` on a known URL.

## Split, Merge & Search

pymupdf handles these natively — use `execute` or inline Python:

```python
# Split: extract pages 1-5 to a new PDF
import pymupdf

doc = pymupdf.open("report.pdf")
new = pymupdf.open()
for i in range(5):
    new.insert_pdf(doc, from_page=i, to_page=i)
new.save("pages_1-5.pdf")
```

```python
# Merge multiple PDFs
import pymupdf

result = pymupdf.open()
for path in ["a.pdf", "b.pdf", "c.pdf"]:
    result.insert_pdf(pymupdf.open(path))
result.save("merged.pdf")
```

```python
# Search for text across all pages
import pymupdf

doc = pymupdf.open("report.pdf")
for i, page in enumerate(doc):
    results = page.search_for("revenue")
    if results:
        print(f"Page {i + 1}: {len(results)} match(es)")
        print(page.get_text("text"))
```

No extra dependencies needed — pymupdf covers split, merge, search, and text extraction in one package.

---

## Notes

- `web_fetch` is always first choice for URLs
- pymupdf is the safe default — instant, no models, works everywhere
- marker-pdf is for OCR, scanned docs, equations, complex layouts — install only when needed
- Both helper scripts accept `--help` for full usage
- marker-pdf downloads ~2.5GB of models to `~/.cache/huggingface/` on first use
- For Word docs: `pip install python-docx` (better than OCR — parses actual structure)
- For PowerPoint: see the `powerpoint` skill (uses python-pptx)
