# -*- coding: utf-8 -*-
"""Export parsed resume JSON (pdf-resume-parser schema) to an Excel workbook.

Input: one or more JSON files, each containing a single resume object or an
array of objects following the skill's references/schema.md structure.
Output: single-sheet .xlsx "候选人汇总" with user-defined columns:
    姓名 | 年龄 | 求职意向 | 期望城市 | 期望薪资 | 毕业院校 | 学历 | 教育经历 |
    工作经历1-时间段/公司/岗位/工作内容, 工作经历2-..., 工作经历3-... |
    技能证书 | 语言证书 | 备注 | 来源文件

Work segments: at most MAX_WORK_SEGMENTS (3) most recent segments; the resume
array is expected to be in descending order (schema rule).

Usage:
    python export_to_excel.py parsed.json -o resumes.xlsx
    python export_to_excel.py *.json -o resumes.xlsx
    python export_to_excel.py dir_of_json -o resumes.xlsx   # all *.json in dir

Exit codes: 0 ok, 1 no input/error, 2 openpyxl missing.
"""
import argparse
import glob
import json
import os
import sys

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl is not installed. Install it into the managed venv: pip install openpyxl")
    sys.exit(2)

MAX_WORK_SEGMENTS = 3  # 用户指定：最多解析最近 3 段工作经历

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(vertical="top", wrap_text=True)


def load_records(paths):
    records = []
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "*.json"))))
        else:
            files.append(p)
    if not files:
        raise ValueError("no JSON input files found")
    for f in files:
        with open(f, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                records.append(item)
    if not records:
        raise ValueError("no resume objects found in input")
    return records


def s(v):
    return "" if v is None else str(v)


def join_list(v):
    if isinstance(v, list):
        return "\n".join(str(x) for x in v if x)
    return s(v)


def fmt_edu(rec):
    lines = []
    for e in rec.get("教育背景", []) or []:
        parts = [s(e.get(k)) for k in ("时间段", "学校", "专业", "学历")]
        lines.append(" | ".join(p for p in parts if p))
    return "\n".join(lines)


def work_cols(rec):
    """Flatten work history into fixed-size column values (3 segments)."""
    segs = (rec.get("工作经历", []) or [])[:MAX_WORK_SEGMENTS]
    vals = []
    for i in range(MAX_WORK_SEGMENTS):
        if i < len(segs):
            w = segs[i]
            vals += [s(w.get("时间段")), s(w.get("公司")), s(w.get("岗位")), s(w.get("工作内容"))]
        else:
            vals += ["", "", "", ""]
    return vals


def headers_and_row(rec):
    edu = rec.get("教育背景", []) or []
    top = edu[0] if edu else {}
    headers = (
        ["姓名", "年龄", "求职意向", "期望城市", "期望薪资", "毕业院校", "学历", "教育经历"]
        + [f"工作经历{i}-" + f for i in range(1, MAX_WORK_SEGMENTS + 1)
           for f in ("时间段", "公司", "岗位", "工作内容")]
        + ["技能证书", "语言证书", "备注", "来源文件"]
    )
    row = (
        [s(rec.get("姓名")), s(rec.get("年龄")),
         s(rec.get("求职意向")), s(rec.get("期望城市")), s(rec.get("期望薪资")),
         s(top.get("学校")), s(top.get("学历")), fmt_edu(rec)]
        + work_cols(rec)
        + [join_list(rec.get("技能证书")), join_list(rec.get("语言证书")),
           s(rec.get("备注")), s(rec.get("来源文件"))]
    )
    return headers, row


def write_sheet(ws, headers, rows):
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = WRAP
    for row in rows:
        ws.append(row)
    for c in range(1, len(headers) + 1):
        width = len(headers[c - 1]) * 1.8 + 4
        for row in rows[:50]:
            v = str(row[c - 1]) if c - 1 < len(row) else ""
            longest = max((len(line) for line in v.split("\n")), default=0)
            width = max(width, min(longest * 1.8 + 2, 50))
        ws.column_dimensions[get_column_letter(c)].width = width
    for r in range(2, len(rows) + 2):
        for c in range(1, len(headers) + 1):
            ws.cell(row=r, column=c).alignment = WRAP
    ws.freeze_panes = "A2"


def main():
    ap = argparse.ArgumentParser(description="Export parsed resume JSON to Excel")
    ap.add_argument("inputs", nargs="+", help="JSON files or a directory of *.json")
    ap.add_argument("-o", "--output", required=True, help="output .xlsx path")
    args = ap.parse_args()

    try:
        records = load_records(args.inputs)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    headers = headers_and_row({})[0]
    rows = [headers_and_row(r)[1] for r in records]

    wb = Workbook()
    ws = wb.active
    ws.title = "候选人汇总"
    write_sheet(ws, headers, rows)

    out = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    wb.save(out)
    print(json.dumps({
        "output": out,
        "candidates": len(records),
        "columns": headers,
        "max_work_segments": MAX_WORK_SEGMENTS,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
