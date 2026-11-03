#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a local folder scaffold for one student."
    )
    parser.add_argument("--student-name", required=True)
    parser.add_argument("--grade", required=True)
    parser.add_argument("--status", default="leads")
    parser.add_argument("--start-date", default=date.today().isoformat())
    parser.add_argument("--english-name", default="")
    parser.add_argument("--school", default="")
    parser.add_argument("--contact-name", default="")
    parser.add_argument("--contact-phone", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--root-dir", default=str(Path.home() / "StudentGrowthOps"))
    return parser.parse_args()


def safe_segment(value: str) -> str:
    text = value.strip()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[\\/:\*\?\"<>\|]+", "", text)
    return text or "unknown"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_teacher_txt(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def status_directory(root_dir: Path, status: str) -> Path:
    mapping = {
        "leads": "Leads",
        "lead": "Leads",
        "active": "Active",
        "renewal-watch": "RenewalWatch",
        "renewalwatch": "RenewalWatch",
        "archived": "Archived",
    }
    key = status.strip().lower()
    folder = mapping.get(key, "Leads")
    return root_dir / folder


def main() -> None:
    args = parse_args()
    root_dir = Path(args.root_dir).expanduser()
    target_root = status_directory(root_dir, args.status)
    ensure_dir(target_root)

    folder_name = "-".join(
        [safe_segment(args.grade), safe_segment(args.student_name), safe_segment(args.start_date)]
    )
    student_dir = target_root / folder_name
    ensure_dir(student_dir)

    data_dir = student_dir / "_data"
    ensure_dir(data_dir)

    lesson_columns = [
        "lesson_date",
        "lesson_theme",
        "goal_completion",
        "classroom_engagement",
        "accuracy_observation",
        "homework_completion",
        "parent_reminder_needed",
        "risk_flag",
        "teacher_note",
    ]

    record = {
        "schemaVersion": 1,
        "studentProfile": {
            "studentName": args.student_name,
            "englishName": args.english_name,
            "grade": args.grade,
            "school": args.school,
            "status": args.status,
            "startDate": args.start_date,
            "sourceChannel": "",
            "contactName": args.contact_name,
            "contactPhone": args.contact_phone,
            "city": args.city,
            "currentLevel": "",
            "personalityTraits": [],
            "studyHabits": [],
            "teacherNotes": "",
        },
        "parentNeeds": {
            "primaryGoals": [],
            "secondaryGoals": [],
            "painPoints": [],
            "decisionBarriers": [],
            "parentStyle": "",
            "budgetSensitivity": "",
            "timePreference": "",
            "expectedResultsWindow": "",
            "followupPriority": "",
            "nextFollowupDate": "",
            "notes": "",
        },
        "learningBaseline": {
            "assessmentDate": "",
            "listeningLevel": "",
            "speakingLevel": "",
            "readingLevel": "",
            "phonicsVocabularyLevel": "",
            "focusInteractionLevel": "",
            "familySupportLevel": "",
            "strengths": [],
            "weakPoints": [],
            "priorityGoals30d": [],
            "teacherStrategy": [],
            "parentAdvice": [],
        },
        "lessonLog": {
            "columns": lesson_columns,
            "rows": [],
        },
        "weeklyFollowup": {
            "weekRange": "",
            "weeklyStatus": "",
            "progressHighlights": [],
            "mainIssues": [],
            "teacherActions": [],
            "parentCommunicationAdvice": [],
            "riskLevel": "",
            "needPriorityFollowup": False,
            "nextActionDate": "",
        },
        "tags": {
            "studentTags": [],
            "parentTags": [],
            "riskTags": [],
            "teachingTags": [],
        },
    }

    write_json(data_dir / "student-record.json", record)

    write_teacher_txt(
        student_dir / "02-家长需求.txt",
        [
            "【家长诉求建档摘要】长期跟进用；与「发给家长的即时微信/话术」不同，后者默认只在对话里直接发文本。",
            "（可与 _data/student-record.json 内 parentNeeds 对照，或请 AI 在需要落档时同步摘要）",
            "",
            f"学生：{args.student_name}　年级：{args.grade}",
            "",
            "主要目标：",
            "痛点与顾虑：",
            "下次沟通要点：",
        ],
    )
    write_teacher_txt(
        student_dir / "03-课后跟进记录.txt",
        [
            "【课后跟进记录】（按日期追加；结构化明细在 _data/student-record.json 的 lessonLog / weeklyFollowup）",
            "",
            f"学生：{args.student_name}",
            "",
            "—— 在此按周或按课记录要点 ——",
        ],
    )
    print(student_dir)


if __name__ == "__main__":
    main()
