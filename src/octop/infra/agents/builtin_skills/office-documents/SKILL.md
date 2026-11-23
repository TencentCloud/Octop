---
name: office-documents
description: Create, edit, inspect and render Word documents, Excel workbooks and PowerPoint presentations in this Octop workspace. 创建、检查、修改和渲染 Word、Excel、PowerPoint 文件。
metadata:
  octop:
    emoji: "📑"
    label:
      zh: "Office 文档"
      en: "Office documents"
    summary:
      zh: "制作和修改 Office 文件，渲染各页并交付工作区产物。"
      en: "Author and edit Office files, inspect rendered pages and deliver the workspace artifacts."
---

# Office documents

Work inside `{{OCTOP_WORKSPACE}}` using the active expert's file and execution tools. Find uploaded originals under `inbound/`. Use a descriptive output filename and preserve the original when editing. Use the execution environment's Python with the Octop Office dependencies. Check the exact input and the intended output before reporting success.

| Format | Create | Load and edit | Check before delivery |
| --- | --- | --- | --- |
| Word | `from docx import Document` and `doc = Document()` | Open with `Document(input_path)`. Edit the affected paragraphs, runs or table cells and call `doc.save(output_path)`. Editing individual runs preserves their formatting. | Reopen with `Document(output_path)` and check headings, tables and the requested text. |
| Excel | `from openpyxl import Workbook` and `book = Workbook()` | Use `openpyxl.load_workbook(input_path, data_only=False)`. Change the target sheets or cells, retain formulas and save to the output path. | Reopen the file, verify sheet names, target cell values and formulas. Recalculate using a spreadsheet application if computed values are part of the deliverable. |
| PowerPoint | `from pptx import Presentation` and `deck = Presentation()` | Open with `Presentation(input_path)`. Update shapes, runs or charts on the requested slides and save via `deck.save(output_path)`. | Reopen the output, check slide count, titles and target shape content. |

## Page preview

For a visual check or when the user requests page images, run the following command inside the same workspace. The helper converts the document to PDF with LibreOffice and renders every page to PNG using Poppler. In Excel it respects the workbook's print areas and page setup.

```sh
python "{{OCTOP_BUILTIN_SKILLS}}/office-documents/scripts/render.py" "output/report.docx" "output/report-pages"
```

Choose a new preview directory on each run. Its `document.pdf` and `page-*.png` files come from the saved Office file. Open the images and inspect tables, wrapping and overflows before handing over the finished file. If the execution environment lacks LibreOffice or `pdftoppm`, report the missing renderer and distinguish document validation from a visual check. The Octop chat file preview also opens Word, Excel and PowerPoint files.

Use the platform's file delivery tool when available to attach the final workspace file to the conversation. Include preview images when requested.
