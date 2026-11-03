#!/usr/bin/env python3
"""
专业报表生成器
将分析结果生成 Markdown / HTML 格式报表
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime


def generate_report(
    title: str,
    sections: list[dict],
    output_path: str,
    fmt: str = "markdown",
    metadata: dict = None,
):
    """
    生成报表。
    sections 格式:
    [{"title": "概览", "content": "文本或 dict"}, ...]
    content 为 dict 时自动转表格。
    """
    if fmt == "markdown":
        _gen_markdown(title, sections, output_path, metadata)
    elif fmt == "html":
        _gen_html(title, sections, output_path, metadata)
    else:
        raise ValueError(f"不支持的格式: {fmt}")


def _gen_markdown(title: str, sections: list[dict], output_path: str, metadata: dict = None):
    lines = []
    lines.append(f"# {title}\n")
    if metadata:
        lines.append(f"> 生成时间: {metadata.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M'))}")
        if metadata.get("author"):
            lines.append(f"> 作者: {metadata['author']}")
        if metadata.get("period"):
            lines.append(f"> 数据周期: {metadata['period']}")
        lines.append("")

    for section in sections:
        lines.append(f"## {section['title']}\n")
        content = section.get("content", "")
        if isinstance(content, dict):
            lines.append(_dict_to_table(content))
        elif isinstance(content, list):
            if content and isinstance(content[0], dict):
                # list of dicts → 表格
                cols = list(content[0].keys())
                lines.append("| " + " | ".join(cols) + " |")
                lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
                for row in content:
                    vals = [str(row.get(c, "")) for c in cols]
                    lines.append("| " + " | ".join(vals) + " |")
            else:
                for item in content:
                    lines.append(f"- {item}")
        else:
            lines.append(str(content))
        if section.get("insight"):
            lines.append(f"\n> 💡 **洞察**: {section['insight']}\n")
        lines.append("")

    text = "\n".join(lines)
    Path(output_path).write_text(text, encoding="utf-8")
    print(f"✅ Markdown 报表已生成: {output_path}")


def _dict_to_table(d: dict) -> str:
    """dict 转简单表格"""
    lines = []
    if all(isinstance(v, dict) for v in d.values()):
        # 嵌套 dict → 列名表
        keys = list(d.keys())
        sub_keys = []
        for v in d.values():
            sub_keys.extend(v.keys())
        sub_keys = list(dict.fromkeys(sub_keys))
        lines.append("| " + " | ".join(["指标"] + sub_keys) + " |")
        lines.append("| " + " | ".join(["---"] * (len(sub_keys) + 1)) + " |")
        for k in keys:
            vals = [str(d[k].get(sk, "")) for sk in sub_keys]
            lines.append("| " + " | ".join([k] + vals) + " |")
    else:
        lines.append("| 指标 | 值 |")
        lines.append("| --- | --- |")
        for k, v in d.items():
            lines.append(f"| {k} | {v} |")
    return "\n".join(lines)


def _gen_html(title: str, sections: list[dict], output_path: str, metadata: dict = None):
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #333; }
    h1 { border-bottom: 2px solid #e74c3c; padding-bottom: 10px; }
    h2 { color: #2c3e50; margin-top: 2em; }
    table { width: 100%; border-collapse: collapse; margin: 1em 0; }
    th { background: #34495e; color: white; padding: 10px 12px; text-align: left; }
    td { padding: 8px 12px; border-bottom: 1px solid #ddd; }
    tr:nth-child(even) { background: #f8f9fa; }
    .insight { background: #fef9e7; border-left: 4px solid #f39c12; padding: 10px 15px; margin: 10px 0; }
    .meta { color: #7f8c8d; font-size: 0.9em; }
    .kpi { display: inline-block; background: #ecf0f1; border-radius: 8px; padding: 15px 25px; margin: 5px; text-align: center; }
    .kpi .value { font-size: 1.8em; font-weight: bold; color: #2c3e50; }
    .kpi .label { font-size: 0.9em; color: #7f8c8d; }
    """
    body = f"<h1>{title}</h1>\n"
    if metadata:
        body += f"<p class='meta'>生成时间: {metadata.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M'))}</p>\n"
        if metadata.get("period"):
            body += f"<p class='meta'>数据周期: {metadata['period']}</p>\n"

    for section in sections:
        body += f"<h2>{section['title']}</h2>\n"
        content = section.get("content", "")
        if isinstance(content, dict):
            # KPI 卡片
            if all(isinstance(v, dict) and "value" in v for v in content.values()):
                for k, v in content.items():
                    body += f"<div class='kpi'><div class='value'>{v.get('value', 'N/A')}</div><div class='label'>{k}</div></div>\n"
            else:
                body += _dict_to_html_table(content)
        elif isinstance(content, list) and content and isinstance(content[0], dict):
            body += _list_to_html_table(content)
        else:
            body += f"<p>{content}</p>\n"
        if section.get("insight"):
            body += f"<div class='insight'>💡 <strong>洞察</strong>: {section['insight']}</div>\n"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title><style>{css}</style></head>
<body>{body}</body></html>"""
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"✅ HTML 报表已生成: {output_path}")


def _dict_to_html_table(d: dict) -> str:
    rows = ""
    if all(isinstance(v, dict) for v in d.values()):
        sub_keys = list(dict.fromkeys(k for v in d.values() for k in v.keys()))
        rows += "<tr><th>指标</th>" + "".join(f"<th>{k}</th>" for k in sub_keys) + "</tr>"
        for k, v in d.items():
            rows += "<tr><td>" + k + "</td>" + "".join(f"<td>{v.get(sk, '')}</td>" for sk in sub_keys) + "</tr>"
    else:
        for k, v in d.items():
            rows += f"<tr><td>{k}</td><td>{v}</td></tr>"
    return f"<table>{rows}</table>"


def _list_to_html_table(lst: list[dict]) -> str:
    if not lst:
        return ""
    cols = list(lst[0].keys())
    header = "".join(f"<th>{c}</th>" for c in cols)
    rows = ""
    for item in lst:
        row = "".join(f"<td>{item.get(c, '')}</td>" for c in cols)
        rows += f"<tr>{row}</tr>"
    return f"<table><tr>{header}</tr>{rows}</table>"


def main():
    parser = argparse.ArgumentParser(description="专业报表生成器")
    parser.add_argument("config", help="报表配置 JSON 文件")
    parser.add_argument("-o", "--output", required=True, help="输出文件路径")
    parser.add_argument("--format", default="markdown", choices=["markdown", "html"])
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    generate_report(
        title=config.get("title", "数据分析报告"),
        sections=config.get("sections", []),
        output_path=args.output,
        fmt=args.format,
        metadata=config.get("metadata"),
    )


if __name__ == "__main__":
    main()
