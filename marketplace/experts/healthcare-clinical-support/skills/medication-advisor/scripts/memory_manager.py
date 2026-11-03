#!/usr/bin/env python3
"""
Medication Context Memory Manager
Manages persistent medication consultation context across sessions.

Usage:
    python memory_manager.py read <memory_dir>
    python memory_manager.py update <memory_dir> --field <field_path> --value <json_value>
    python memory_manager.py merge <memory_dir> --source <json_file>
    python memory_manager.py summary <memory_dir>

The memory file is stored as: <memory_dir>/medication-context.md
"""

import json
import sys
from datetime import datetime
from pathlib import Path

MEMORY_FILENAME = "medication-context.md"

DEFAULT_SCHEMA = {
    "patient_profile": {
        "demographics": {
            "age": None,
            "gender": None,
            "weight": None,
            "pregnancy_status": None,
            "lactation_status": None,
            "pediatric": False,
            "geriatric": False,
        },
        "allergy_history": [],
        "medical_history": [],
        "current_diagnoses": [],
        "treatment_history": {
            "current_medications": [],
            "past_medications": [],
            "surgical_history": [],
        },
        "lab_results": {},
        "liver_function": None,
        "renal_function": None,
    },
    "session_context": {
        "current_drugs_in_discussion": [],
        "resolved_questions": [],
        "pending_followups": [],
        "attachment_summaries": [],
    },
    "last_updated": None,
    "update_log": [],
}


def get_memory_path(memory_dir: str) -> Path:
    return Path(memory_dir) / MEMORY_FILENAME


def read_memory(memory_dir: str) -> dict:
    """Read existing medication context memory."""
    path = get_memory_path(memory_dir)
    if not path.exists():
        return DEFAULT_SCHEMA.copy()

    text = path.read_text(encoding="utf-8")

    # Extract JSON block from markdown
    import re
    json_match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            return DEFAULT_SCHEMA.copy()

    return DEFAULT_SCHEMA.copy()


def write_memory(memory_dir: str, data: dict):
    """Write medication context memory as markdown with embedded JSON."""
    path = get_memory_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    data["last_updated"] = datetime.now().isoformat()

    md_content = f"""# 用药咨询上下文记忆 (Medication Context Memory)

> 自动维护的患者用药咨询上下文。每次用药咨询时自动读取和更新。
> 最后更新: {data['last_updated']}

## 患者档案

```json
{json.dumps(data, ensure_ascii=False, indent=2)}
```

## 更新日志

"""
    for entry in data.get("update_log", [])[-10:]:  # Keep last 10 entries
        md_content += f"- [{entry.get('time', 'N/A')}] {entry.get('action', 'N/A')}\n"

    path.write_text(md_content, encoding="utf-8")


def set_nested_value(data: dict, field_path: str, value):
    """Set a value in a nested dict using dot-notation path."""
    keys = field_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    final_key = keys[-1]
    # For lists, append instead of overwrite
    if isinstance(current.get(final_key), list) and isinstance(value, (str, dict)):
        if value not in current[final_key]:
            current[final_key].append(value)
    else:
        current[final_key] = value


def merge_data(existing: dict, new_data: dict, path_prefix: str = "") -> list:
    """Recursively merge new data into existing, tracking changes."""
    changes = []
    for key, value in new_data.items():
        full_path = f"{path_prefix}.{key}" if path_prefix else key

        if key not in existing:
            existing[key] = value
            changes.append(f"Added {full_path}")
        elif isinstance(value, dict) and isinstance(existing[key], dict):
            changes.extend(merge_data(existing[key], value, full_path))
        elif isinstance(value, list) and isinstance(existing[key], list):
            for item in value:
                if item not in existing[key]:
                    existing[key].append(item)
                    changes.append(f"Appended to {full_path}: {item}")
        elif value is not None and existing[key] != value:
            old = existing[key]
            existing[key] = value
            changes.append(f"Updated {full_path}: {old} -> {value}")

    return changes


def get_summary(data: dict) -> str:
    """Generate a human-readable summary of the patient context."""
    profile = data.get("patient_profile", {})
    demo = profile.get("demographics", {})
    session = data.get("session_context", {})

    lines = ["=== 患者上下文摘要 ==="]

    # Demographics
    age = demo.get("age")
    gender = demo.get("gender")
    if age or gender:
        lines.append(f"人口学: {gender or '未知'}, {age or '未知'}岁")
    else:
        lines.append("人口学: 未记录")

    # Special populations
    flags = []
    if demo.get("pregnancy_status"):
        flags.append("妊娠期")
    if demo.get("lactation_status"):
        flags.append("哺乳期")
    if demo.get("pediatric"):
        flags.append("儿童")
    if demo.get("geriatric"):
        flags.append("老年人")
    if flags:
        lines.append(f"特殊人群: {', '.join(flags)}")

    # Allergies
    allergies = profile.get("allergy_history", [])
    lines.append(f"过敏史: {', '.join(allergies) if allergies else '无记录'}")

    # Current medications
    meds = profile.get("treatment_history", {}).get("current_medications", [])
    lines.append(f"当前用药: {', '.join(str(m) for m in meds) if meds else '无记录'}")

    # Diagnoses
    diags = profile.get("current_diagnoses", [])
    lines.append(f"当前诊断: {', '.join(diags) if diags else '无记录'}")

    # Lab results
    labs = profile.get("lab_results", {})
    if labs:
        lines.append(f"化验指标: {json.dumps(labs, ensure_ascii=False)}")

    # Session
    drugs = session.get("current_drugs_in_discussion", [])
    if drugs:
        lines.append(f"当前讨论药品: {', '.join(drugs)}")

    pending = session.get("pending_followups", [])
    if pending:
        lines.append(f"待追问: {', '.join(str(p) for p in pending)}")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    memory_dir = sys.argv[2]

    if action == "read":
        data = read_memory(memory_dir)
        print(json.dumps(data, ensure_ascii=False, indent=2))

    elif action == "update":
        if "--field" not in sys.argv or "--value" not in sys.argv:
            print("Usage: memory_manager.py update <dir> --field <path> --value <json>")
            sys.exit(1)
        field_idx = sys.argv.index("--field") + 1
        value_idx = sys.argv.index("--value") + 1
        field_path = sys.argv[field_idx]
        value = json.loads(sys.argv[value_idx])

        data = read_memory(memory_dir)
        set_nested_value(data, field_path, value)
        data.setdefault("update_log", []).append({
            "time": datetime.now().isoformat(),
            "action": f"Set {field_path} = {value}",
        })
        write_memory(memory_dir, data)
        print(f"Updated {field_path}")

    elif action == "merge":
        if "--source" not in sys.argv:
            print("Usage: memory_manager.py merge <dir> --source <json_file>")
            sys.exit(1)
        source_idx = sys.argv.index("--source") + 1
        source_path = Path(sys.argv[source_idx])
        new_data = json.loads(source_path.read_text(encoding="utf-8"))

        data = read_memory(memory_dir)
        changes = merge_data(data.get("patient_profile", {}), new_data)
        data.setdefault("update_log", []).append({
            "time": datetime.now().isoformat(),
            "action": f"Merged from {source_path.name}: {len(changes)} changes",
        })
        write_memory(memory_dir, data)
        print(f"Merged {len(changes)} changes:")
        for c in changes:
            print(f"  - {c}")

    elif action == "summary":
        data = read_memory(memory_dir)
        print(get_summary(data))

    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
