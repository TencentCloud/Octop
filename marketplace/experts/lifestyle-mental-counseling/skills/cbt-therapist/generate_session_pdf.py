# -*- coding: utf-8 -*-
"""
CBT心理治疗 - 简洁版PDF生成模块 v3
设计原则：简洁、干净、复盘不累
"""

import os
import sys
import json
import re
from datetime import datetime
from typing import List, Dict

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether, PageBreak
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
    REPORTLAB_AVAILABLE = True

    import os as _os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _msyh_path = r'C:\Windows\Fonts\msyh.ttc'
    _simhei_path = r'C:\Windows\Fonts\simhei.ttf'
    if _os.path.exists(_msyh_path):
        pdfmetrics.registerFont(TTFont('MSYH', _msyh_path))
    if _os.path.exists(_simhei_path):
        pdfmetrics.registerFont(TTFont('SimHei', _simhei_path))
except ImportError:
    REPORTLAB_AVAILABLE = False


FONT_NAME = "MSYH"
FONT_NAME_BOLD = "MSYH"
PRIMARY = HexColor("#1A1A1A")
SECONDARY = HexColor("#666666")
ACCENT = HexColor("#0066CC")
DIVIDER = HexColor("#E0E0E0")


class SessionPDFGenerator:
    """CBT会话PDF生成器 - 简洁版"""

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.turns: List[Dict] = []
        self.session_number: int = 1
        self.session_date: str = ""
        self.session_topic: str = ""

    def load_conversation(self, turns: List[Dict], session_number: int = None):
        self.turns = turns
        if session_number:
            self.session_number = session_number
        if turns and "timestamp" in turns[0]:
            try:
                dt = datetime.fromisoformat(turns[0]["timestamp"])
                self.session_date = dt.strftime("%Y-%m-%d")
            except Exception:
                self.session_date = datetime.now().strftime("%Y-%m-%d")
        else:
            self.session_date = datetime.now().strftime("%Y-%m-%d")

    def set_session_topic(self, topic: str):
        self.session_topic = topic

    def generate_pdf(self, output_dir: str = None) -> str:
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("reportlab 未安装")
        if not self.turns:
            raise ValueError("没有对话记录")
        if output_dir is None:
            output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(output_dir, exist_ok=True)
        filename = f"CBT治疗记录_第{self.session_number}次_{self.session_date}.pdf"
        filepath = os.path.join(output_dir, filename)
        self._build_pdf(filepath)
        return filepath

    def _build_pdf(self, filepath: str):
        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            rightMargin=25*mm, leftMargin=25*mm,
            topMargin=20*mm, bottomMargin=20*mm,
        )
        styles = self._create_styles()
        story = []
        story.extend(self._build_header(styles))
        story.extend(self._build_meta(styles))
        story.extend(self._build_conversation(styles))
        story.extend(self._build_footer(styles))
        doc.build(story)

    def _create_styles(self) -> dict:
        return {
            "main_title": ParagraphStyle("MainTitle",
                fontName=FONT_NAME_BOLD, fontSize=22, textColor=PRIMARY,
                leading=28, alignment=TA_LEFT, spaceAfter=4),
            "subtitle": ParagraphStyle("Subtitle",
                fontName=FONT_NAME, fontSize=11, textColor=SECONDARY,
                leading=16, alignment=TA_LEFT, spaceAfter=12),
            "topic": ParagraphStyle("Topic",
                fontName=FONT_NAME, fontSize=12, textColor=PRIMARY,
                leading=18, spaceBefore=8, spaceAfter=16),
            "meta_label": ParagraphStyle("MetaLabel",
                fontName=FONT_NAME_BOLD, fontSize=10, textColor=SECONDARY, leading=14),
            "meta_value": ParagraphStyle("MetaValue",
                fontName=FONT_NAME, fontSize=10, textColor=PRIMARY, leading=14),
            "speaker_user": ParagraphStyle("SpeakerUser",
                fontName=FONT_NAME_BOLD, fontSize=11, textColor=ACCENT, leading=16),
            "speaker_therapist": ParagraphStyle("SpeakerTherapist",
                fontName=FONT_NAME_BOLD, fontSize=11, textColor=PRIMARY, leading=16),
            "dialogue": ParagraphStyle("Dialogue",
                fontName=FONT_NAME, fontSize=11, textColor=PRIMARY,
                leading=20, alignment=TA_LEFT),
            "footer": ParagraphStyle("Footer",
                fontName=FONT_NAME, fontSize=9, textColor=SECONDARY, alignment=TA_CENTER),
        }

    def _build_header(self, styles: dict) -> List:
        elements = []
        elements.append(Paragraph("CBT 治疗记录", styles["main_title"]))
        elements.append(Paragraph(
            f"第 {self.session_number} 次会话 · {self.session_date}", styles["subtitle"]))
        if self.session_topic:
            elements.append(Paragraph(f"主题：{self.session_topic}", styles["topic"]))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY))
        elements.append(Spacer(1, 12*mm))
        return elements

    def _build_meta(self, styles: dict) -> List:
        elements = []
        cells = [[
            Paragraph("对话轮次", styles["meta_label"]),
            Paragraph(f"{len(self.turns)} 轮", styles["meta_value"])
        ]]
        table = Table(cells, colWidths=[170*mm])
        table.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 10*mm))
        return elements

    def _split_text_into_items(self, text: str) -> List[str]:
        """
        把文本拆成独立段落。
        关键：自动识别 '1. xxx 2. xxx 3. xxx' 这种连在一行的列表，
        拆成三条各自独立的段落。
        """
        # 先按段落分隔（双换行 或 单换行）
        paragraphs = re.split(r'\n\s*\n|\n(?!\s)', text.strip())
        result = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # 识别同一行内含多个编号项目的情况
            # 匹配：数字. 或 （数字） 或 字母.
            if re.search(r'\d+\.\s+\S', para) and para.count('\n') == 0:
                # 同一行内有多个编号，用正则拆分
                # 先还原换行（把被合并的换行补回来）
                # 匹配编号开始的位置：(数字. 或 （数字） 或 数字.)
                parts = re.split(r'(?<=\S)\s+(?=\d+\.)', para)
                # 如果上面没拆开（用另一种方式）
                if len(parts) <= 1:
                    # 按编号标记拆分
                    parts = re.split(r'(?<=[。！？])\s*(?=\d+\.)', para)
                if len(parts) <= 1:
                    # 最简单粗暴：按数字编号拆分
                    parts = re.split(r'(?<=[。！？．])\s+(?=\d[．.])', para)
                if len(parts) <= 1:
                    # 用另一种：每个编号都是新段落
                    parts = re.split(r'(?<=[。！？])\s+(?=\d[．.、])', para)
                cleaned = []
                for p in parts:
                    p = p.strip()
                    if p:
                        cleaned.append(p)
                result.extend(cleaned)
            else:
                result.append(para)
        return result

    def _build_conversation(self, styles: dict) -> List:
        elements = []

        for i, turn in enumerate(self.turns):
            speaker = turn.get("speaker", "")
            text = turn.get("text", "")
            if not text or not text.strip():
                continue

            # 判断说话者
            if speaker in ["来访者", "user"]:
                speaker_label = "来访者"
                speaker_style = styles["speaker_user"]
            elif speaker in ["心理治疗师", "therapist", "🧠"]:
                speaker_label = "治疗师"
                speaker_style = styles["speaker_therapist"]
            else:
                speaker_label = speaker
                speaker_style = styles["speaker_user"]

            # 拆分文本为独立段落
            items = self._split_text_into_items(text)

            # 第一个段落：说话者 + 第一条内容（左右分栏）
            first_item = items[0]
            first_data = [[
                Paragraph(speaker_label, speaker_style),
                Paragraph(first_item, styles["dialogue"]),
            ]]
            first_table = Table(first_data, colWidths=[40*mm, 118*mm])
            first_table.setStyle(TableStyle([
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("LEFTPADDING", (1, 0), (1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            elements.append(first_table)

            # 后续段落：左空 + 内容（右分栏对齐）
            for item in items[1:]:
                sub_data = [[
                    Paragraph("", styles["speaker_user"]),
                    Paragraph(item, styles["dialogue"]),
                ]]
                sub_table = Table(sub_data, colWidths=[40*mm, 118*mm])
                sub_table.setStyle(TableStyle([
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("LEFTPADDING", (1, 0), (1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]))
                elements.append(sub_table)

            # 分隔线
            if i < len(self.turns) - 1:
                elements.append(Spacer(1, 2*mm))
                elements.append(HRFlowable(width="100%", thickness=0.5, color=DIVIDER))
                elements.append(Spacer(1, 6*mm))

        return elements

    def _build_footer(self, styles: dict) -> List:
        elements = []
        elements.append(Spacer(1, 15*mm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=DIVIDER))
        elements.append(Spacer(1, 6*mm))
        footer_text = f"CBT治疗记录 · {datetime.now().strftime('%Y-%m-%d')} · 仅供个人复盘使用"
        elements.append(Paragraph(footer_text, styles["footer"]))
        return elements


# ============================================================
# 历史提取器（兼容旧接口）
# ============================================================
def extract_session_from_history(user_id: str, session_number: int = None, latest: bool = True):
    storage_dir = os.path.join(os.path.expanduser("~"), ".qclaw", "workspace", "cbt-sessions")
    history_file = os.path.join(storage_dir, f"history_{user_id}.json")
    if not os.path.exists(history_file):
        return [], session_number or 1
    with open(history_file, 'r', encoding='utf-8') as f:
        history = json.load(f)
    if not history:
        return [], session_number or 1
    sessions = {}
    for record in history:
        sn = record.get("session_number") or 1
        if sn not in sessions:
            sessions[sn] = []
        sessions[sn].append(record)
    if session_number:
        target = sessions.get(session_number, [])
    elif latest:
        target_sn = max(sessions.keys()) if sessions else 1
        target = sessions.get(target_sn, [])
        session_number = target_sn
    else:
        target = history
        session_number = session_number or 1
    turns = []
    for r in target:
        if r.get("user"):
            turns.append({"speaker": "user", "text": r["user"], "timestamp": r.get("timestamp")})
        if r.get("therapist"):
            turns.append({"speaker": "therapist", "text": r["therapist"], "timestamp": r.get("timestamp")})
    turns.sort(key=lambda x: x.get("timestamp", ""))
    return turns, session_number


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default="default")
    parser.add_argument("--session", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--topic", default="")
    args = parser.parse_args()
    turns, session_num = extract_session_from_history(args.user_id, args.session)
    if not turns:
        print("未找到对话记录")
        sys.exit(1)
    generator = SessionPDFGenerator(user_id=args.user_id)
    generator.load_conversation(turns, session_num)
    if args.topic:
        generator.set_session_topic(args.topic)
    pdf_path = generator.generate_pdf(args.output)
    print(f"PDF已生成：{pdf_path}")


if __name__ == "__main__":
    main()
