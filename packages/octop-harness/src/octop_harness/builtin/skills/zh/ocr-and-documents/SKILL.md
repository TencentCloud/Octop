---
name: ocr-and-documents
description: "从 PDF/扫描件中提取文本（pymupdf、marker-pdf）。"
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

# PDF 和文档提取

## Harness-agent tools

本技能从 Octop 移植。使用以下 harness/deepagents 工具：

| 概念 | 工具 |
|---------|------|
| Shell | `execute` |
| 读/写/编辑文件 | `read_file`, `write_file`, `edit_file` |
| 查找文件/搜索内容 | `glob`, `grep` |
| 获取 URL | `web_fetch` |
| 浏览器自动化 | `browser_use` |
| 子代理工作 | `task` |
| 记忆 | `memory_store`, `memory_recall`, `memory_search` |

内置技能文件位于 `/_builtin_skills/<name>/`。用户安装的技能位于 `/skills/<name>/`。

对于 DOCX：使用 `python-docx`（解析实际文档结构，远优于 OCR）。
对于 PPTX：参见 `powerpoint` 技能（使用带完整幻灯片/注释支持的 `python-pptx`）。
本技能涵盖 **PDF 和扫描文档**。

## 步骤 1：远程 URL 可用？

如果文档有 URL，**先尝试 `web_fetch`** 用于 HTML 页面和基于文本的内容：

```
web_fetch(url="https://arxiv.org/abs/2402.03300")
```

`web_fetch` 将 HTML 转换为 markdown。对于二进制 PDF，它返回纯文本或可能失败——回退到下面的本地提取。

仅当文件是本地文件、`web_fetch` 失败或返回不可用输出，或者你需要批量处理/OCR 时才使用本地提取。

## 步骤 2：选择本地提取器

| 功能 | pymupdf (~25MB) | marker-pdf (~3-5GB) |
|---|---|---|
| **基于文本的 PDF** | ✅ | ✅ |
| **扫描的 PDF（OCR）** | ❌ | ✅（90+ 种语言） |
| **表格** | ✅（基础） | ✅（高精度） |
| **公式 / LaTeX** | ❌ | ✅ |
| **代码块** | ❌ | ✅ |
| **表单** | ❌ | ✅ |
| **页眉/页脚移除** | ❌ | ✅ |
| **阅读顺序检测** | ❌ | ✅ |
| **图像提取** | ✅（嵌入） | ✅（带上下文） |
| **图像 → 文本（OCR）** | ❌ | ✅ |
| **EPUB** | ✅ | ✅ |
| **Markdown 输出** | ✅（通过 pymupdf4llm） | ✅（原生，更高质量） |
| **安装大小** | ~25MB | ~3-5GB（PyTorch + 模型） |
| **速度** | 即时 | ~1-14 秒/页（CPU），~0.2 秒/页（GPU） |

**决策**：除非你需要 OCR、公式、表单或复杂布局分析，否则使用 pymupdf。

如果用户的系统缺少 ~5GB 可用空间，但需要 marker 功能：

> "此文档需要 OCR/高级提取（marker-pdf），这需要 ~5GB 用于 PyTorch 和模型。你的系统有 [X]GB 可用空间。选项：释放空间、提供 URL 以便我可以使用 web_fetch，或者我可以尝试 pymupdf，它适用于基于文本的 PDF，但不适用于扫描文档或公式。"

---

## pymupdf（轻量级）

```bash
pip install pymupdf pymupdf4llm
```

**通过助手脚本**（在 `init_workspace` 后的工作区根目录）：

```bash
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --markdown
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --tables
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --images out/
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --metadata
python _builtin_skills/ocr-and-documents/scripts/extract_pymupdf.py document.pdf --pages 0-4
```

**内联**：

```python
import pymupdf

doc = pymupdf.open("document.pdf")
for page in doc:
    print(page.get_text())
```

---

## marker-pdf（高质量 OCR）

```bash
# 先检查磁盘空间
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py --check

pip install marker-pdf
```

**通过助手脚本**：

```bash
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf --json
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf --output_dir out/
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py scanned.pdf
python _builtin_skills/ocr-and-documents/scripts/extract_marker.py document.pdf --use_llm
```

**CLI**（随 marker-pdf 安装）：

```bash
marker_single document.pdf --output_dir ./output
marker /path/to/folder --workers 4    # 批量
```

---

## Arxiv 论文

```
# 摘要（HTML → markdown 通过 web_fetch）
web_fetch(url="https://arxiv.org/abs/2402.03300")

# 完整论文 PDF——下载然后本地提取（见上面的 pymupdf / marker）
execute(command="curl -L -o paper.pdf https://arxiv.org/pdf/2402.03300")
```

对于论文搜索，使用已配置的搜索工具（`tavily_search`、`searchfree_search` 等），或对已知 URL 使用 `web_fetch`。

## 拆分、合并和搜索

pymupdf 原生处理这些——使用 `execute` 或内联 Python：

```python
# 拆分：提取前 5 页到新 PDF
import pymupdf

doc = pymupdf.open("report.pdf")
new = pymupdf.open()
for i in range(5):
    new.insert_pdf(doc, from_page=i, to_page=i)
new.save("pages_1-5.pdf")

# 合并多个 PDF
result = pymupdf.open()
for path in ["a.pdf", "b.pdf", "c.pdf"]:
    result.insert_pdf(pymupdf.open(path))
result.save("merged.pdf")

# 跨所有页面搜索文本
doc = pymupdf.open("report.pdf")
for i, page in enumerate(doc):
    results = page.search_for("venue")
    if results:
        print(f"Page {i + 1}: {len(results)} match(es)")
        print(page.get_text("text"))
```

无需额外依赖——pymupdf 在一个包中涵盖拆分、合并、搜索和文本提取。

---

## 注意事项

- `web_fetch` 始终是 URL 的首选
- pymupdf 是安全的默认选择——即时、无模型、随处可用
- marker-pdf 用于 OCR、扫描文档、公式、复杂布局——仅在需要时安装
- 两个助手脚本都接受 `--help` 以获取完整用法
- marker-pdf 在首次使用时将 ~2.5GB 模型下载到 `~/.cache/huggingface/`
- 对于 Word 文档：`pip install python-docx`（优于 OCR——解析实际结构）
- 对于 PowerPoint：`pip install python-pptx`（参见 `powerpoint` 技能）
