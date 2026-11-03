#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resume_to_text.py — 简历 PDF / 图片 → 干净文本

用途：把候选人简历（PDF 或图片）转成干净的 Markdown 文本，供简历分析使用。
     内建「平台水印过滤」，专门处理 BOSS 直聘 / 招聘平台导出的斜向旋转水印，
     避免水印字符混入正文，污染事实底稿。

用法：
    python resume_to_text.py <简历文件路径> [-o 输出文件.md]

依赖（任选其一安装）：
    PDF 文本层提取   → pdfplumber（推荐，纯 Python）
    OCR / 复杂转换   → markitdown（可选，转换扫描版或图片）

    pip install pdfplumber
    # 可选：pip install 'markitdown[all]'

原理：
    招聘平台导出的 PDF 常带斜向水印（如 jdxNW7fnqeOWb-... / 80e49dcd37365e...）。
    直接用 extract_text() 会把水印字符混进正文行内（"负责空调4等y家电"）。
    本脚本按「坐标重建」方式提取：先探明水印字符集，再按 y 坐标分组重建行，
    过滤掉孤立的水印碎片，输出干净的逐行文本。

作者：resume-screening skill 内嵌脚本
版本：v1.0.0
"""

import argparse
import re
import sys
from pathlib import Path

# 正文中不应出现的「孤立单字符」频率阈值说明：
# 正常中英文混排里，单字符（如数字、字母）通常紧贴词，不会大量孤立成词。
# 水印碎片则常以「单字符 / 成对 1-2 字符」的形式散布。下面用字符集白名单过滤。

# 水印长串的最小长度：平台水印 ID 通常 20-50 位的随机字母数字（含连字符）。
# 阈值取 15，避开手机号(11)、日期(含 .)、邮箱(含 @ .)等正常长 token。
LONG_TOKEN_MIN_LEN = 15

# 行重建时 y 坐标的分组精度（pt）。取值 3：同一行内上下浮动 3pt 内的词归一组。
Y_BIN = 3


def detect_watermark(words):
    """从 pdfplumber 的 extract_words() 结果里探明水印字符集。

    水印特征：由随机字母数字 + 连字符组成的长串（长度 >= LONG_TOKEN_MIN_LEN），
    这些长串通常就是平台文件 ID / 水印串，其字符会以单字符/短碎片形式散落在正文行内。

    返回 (charset, long_tokens)：
      charset     需要过滤的「水印单字符」集合
      long_tokens 识别出的水印长串列表（整串过滤）
    """
    charset = set()
    long_tokens = []
    for w in words:
        t = (w.get("text") or "").strip()
        # 允许连字符（水印 ID 常含 "-"，如 80e49dcd...Wf-bWOeq...）
        if len(t) >= LONG_TOKEN_MIN_LEN and re.fullmatch(r"[A-Za-z0-9\-]+", t):
            long_tokens.append(t)
            charset.update(set(t))
    return charset, long_tokens


def clean_inner_watermark(text, charset):
    """剔除混在中文词内的孤立水印字符（如 '空调4等y家电' → '空调等家电'）。

    规则：字符在水印字符集内，且左右邻接都是非 ASCII 字符（中文/全角标点/空格）
    的孤立字符 → 判为斜向水印混入，剔除。
    左右任一边是 ASCII 字符（字母/数字/符号如 + - @ .）→ 视为英文/数字表达式
    一部分，保留（避免误删「1+X」的 1、「C++」等专有名词）。
    """
    if not charset or not text:
        return text
    chars = list(text)
    n = len(chars)
    out = []
    for i, c in enumerate(chars):
        if c in charset:
            left = chars[i - 1] if i > 0 else ""
            right = chars[i + 1] if i < n - 1 else ""
            left_ascii = bool(left) and ord(left) < 128
            right_ascii = bool(right) and ord(right) < 128
            if not left_ascii and not right_ascii:
                continue  # 被中文/全角包围的孤立水印字符，剔除
        out.append(c)
    return "".join(out)


def rebuild_lines(words, charset, long_tokens):
    """按坐标重建每一行，过滤水印碎片。

    过滤规则：
      1. 水印长串本身
      2. 短碎片（长度 <= 3）且不含中文、且字符全在水印字符集内
      3. 中文词内的孤立水印字符（clean_inner_watermark）

    返回 list[str]：干净的正文行。
    """
    rows = {}
    for w in words:
        t = (w.get("text") or "").strip()
        if not t:
            continue
        # 1. 整串过滤：水印长串本身
        if t in long_tokens:
            continue
        # 2. 碎片过滤：短 token、无中文、字符全在字符集 → 水印碎片
        if (
            charset
            and len(t) <= 3
            and not re.search(r"[\u4e00-\u9fff]", t)
            and all(c in charset for c in t)
        ):
            continue
        # 3. 词内清洗：含中文的词，剔除孤立水印字符
        if charset and re.search(r"[\u4e00-\u9fff]", t):
            t = clean_inner_watermark(t, charset)
        if not t.strip():
            continue

        key = round((w.get("top") or 0) / Y_BIN) * Y_BIN
        rows.setdefault(key, []).append((w.get("x0") or 0, t))

    lines = []
    for k in sorted(rows):
        line = " ".join(t for _, t in sorted(rows[k], key=lambda x: x[0]))
        line = line.strip()
        if line:
            lines.append(line)
    return lines


def extract_pdf_text(pdf_path):
    """提取 PDF 文本。优先坐标重建 + 水印过滤；失败则退回 extract_text。

    打开失败（损坏文件/非 PDF 伪装）时友好报错，不抛 traceback。
    """
    import pdfplumber

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_text = []
            total_chars = 0
            for page in pdf.pages:
                words = page.extract_words()
                if words:
                    charset, long_tokens = detect_watermark(words)
                    lines = rebuild_lines(words, charset, long_tokens)
                    page_text = "\n".join(lines)
                else:
                    page_text = page.extract_text() or ""
                total_chars += len(page_text)
                if page_text.strip():
                    pages_text.append(page_text.strip())

            text = "\n\n".join(pages_text)
    except Exception as e:  # noqa: BLE001 — 损坏/非 PDF/加密文件统一兜底
        print(f"❌ 无法解析 PDF：{e}", file=sys.stderr)
        print("  请确认文件是有效的 PDF（未损坏、非其他格式伪装）。", file=sys.stderr)
        print("  扫描版（无文字层）可加 --ocr 走 OCR。", file=sys.stderr)
        return ""

    if not text.strip():
        print("⚠️  未提取到文本层：这可能是扫描版 PDF（无文字层）。", file=sys.stderr)
        print("    请改用图片 OCR（见下方建议），或让对方发清晰文字版/截图。", file=sys.stderr)
    return text


def extract_with_markitdown(path):
    """可选：用 markitdown 转换（支持扫描版 OCR / 图片）。"""
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(str(path))
    return result.text_content or ""


def main():
    if len(sys.argv) < 2:
        print("用法：python resume_to_text.py <简历文件路径> [-o 输出文件.md] [--ocr]", file=sys.stderr)
        print("示例：python resume_to_text.py 简历.pdf -o /tmp/resume.md", file=sys.stderr)
        print("      扫描版/图片加 --ocr（需 pip install 'markitdown[all]'）", file=sys.stderr)
        sys.exit(1)

    ap = argparse.ArgumentParser(description="简历 PDF/图片 → 干净文本")
    ap.add_argument("input", help="简历文件路径（.pdf / .png / .jpg 等）")
    ap.add_argument("-o", "--output", help="输出文件路径（默认打印到 stdout）")
    ap.add_argument("--ocr", action="store_true", help="用 markitdown 走 OCR（扫描版/图片）")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"❌ 文件不存在：{src}", file=sys.stderr)
        sys.exit(1)

    if args.ocr:
        try:
            text = extract_with_markitdown(src)
        except Exception as e:  # noqa: BLE001
            print(f"❌ OCR 转换失败：{e}", file=sys.stderr)
            print("  建议：pip install 'markitdown[all]'，或让对方发文字版。", file=sys.stderr)
            sys.exit(1)
    elif src.suffix.lower() == ".pdf":
        text = extract_pdf_text(src)
    else:
        # 图片：优先 OCR，若未装 markitdown 则提示
        try:
            text = extract_with_markitdown(src)
        except Exception as e:  # noqa: BLE001
            print(f"❌ 图片转换需要 markitdown：{e}", file=sys.stderr)
            print("  建议：pip install 'markitdown[all]'", file=sys.stderr)
            sys.exit(1)

    # 清理常见噪音行（转换工具日志）
    text = re.sub(r"(?m)^.*(pydub|RuntimeWarning|warn\().*$\n?", "", text)
    text = text.strip()

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"✅ 已写入 {args.output}（{len(text)} 字符）", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
