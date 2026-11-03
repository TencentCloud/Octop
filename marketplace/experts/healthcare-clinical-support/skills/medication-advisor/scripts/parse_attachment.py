#!/usr/bin/env python3
"""
Attachment Parser for Medication Advisor Skill
Extracts structured medication-related data from medical documents.

Usage:
    python parse_attachment.py <file_path>

Supports: Text files containing medical records, prescriptions,
          health profiles, and examination reports.

Output: JSON with extracted structured data.
"""

import json
import re
import sys
from pathlib import Path


def detect_document_type(text: str) -> str:
    """Detect the type of medical document based on content patterns."""
    patterns = {
        "prescription": [
            r"处方", r"Rx", r"处方号", r"处方日期",
            r"用法用量", r"剂量", r"每日\d+次",
            r"口服|外用|注射|静脉|肌注",
        ],
        "medical_record": [
            r"病历", r"入院记录", r"出院记录", r"门诊病历",
            r"主诉", r"现病史", r"既往史", r"查体",
            r"诊断", r"治疗方案",
        ],
        "health_profile": [
            r"健康档案", r"个人信息", r"既往病史",
            r"过敏史", r"家族史", r"慢性病",
        ],
        "exam_report": [
            r"体检报告", r"检验报告", r"化验单",
            r"参考[值范围]", r"结果", r"异常",
            r"ALT|AST|Cr|BUN|eGFR|血常规|尿常规",
        ],
    }

    scores = {}
    for doc_type, keywords in patterns.items():
        score = sum(1 for kw in keywords if re.search(kw, text, re.IGNORECASE))
        scores[doc_type] = score

    if max(scores.values()) == 0:
        return "unknown"
    return max(scores, key=scores.get)


def extract_drug_names(text: str) -> list:
    """Extract potential drug names from text."""
    drugs = []

    # Common drug name patterns (Chinese)
    cn_drug_patterns = [
        r"[\u4e00-\u9fff]{2,8}(?:片|胶囊|颗粒|注射液|口服液|滴丸|软膏|乳膏|喷雾剂|栓剂|散剂|丸剂|缓释片|控释片|分散片|咀嚼片|泡腾片|肠溶片)",
        r"[\u4e00-\u9fff]{2,6}(?:西林|沙星|洛尔|普利|沙坦|他汀|拉唑|替尼|霉素|磺胺|西泮|曲松|菌素)",
    ]

    for pattern in cn_drug_patterns:
        matches = re.findall(pattern, text)
        drugs.extend(matches)

    # Common English drug names
    en_drug_pattern = r"\b[A-Z][a-z]+(?:cillin|mycin|statin|prazole|sartan|pril|olol|pine|azole|floxacin|caine)\b"
    en_matches = re.findall(en_drug_pattern, text, re.IGNORECASE)
    drugs.extend(en_matches)

    return list(set(drugs))


def extract_dosage_info(text: str) -> list:
    """Extract dosage and administration information."""
    dosage_entries = []

    # Pattern: drug + dosage + frequency
    patterns = [
        r"([\u4e00-\u9fff]+)\s*(\d+\.?\d*)\s*(mg|g|ml|μg|IU|万?单位)\s*[,，]?\s*(每日|一日|qd|bid|tid|qid|q\d+h)?\s*(\d*)\s*次?",
        r"([\u4e00-\u9fff]+)\s*(\d+\.?\d*)\s*(mg|g|ml)\s*[×x]\s*(\d+)\s*(次/日|次/天)",
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for m in matches:
            entry = {
                "raw_text": m.group(0),
                "groups": list(m.groups()),
            }
            dosage_entries.append(entry)

    return dosage_entries


def extract_demographics(text: str) -> dict:
    """Extract patient demographic information."""
    demo = {}

    # Age
    age_match = re.search(r"(?:年龄|Age)[：:]\s*(\d+)\s*岁?", text)
    if age_match:
        demo["age"] = int(age_match.group(1))

    # Gender
    gender_match = re.search(r"(?:性别|Gender)[：:]\s*(男|女|Male|Female)", text)
    if gender_match:
        demo["gender"] = gender_match.group(1)

    # Weight
    weight_match = re.search(r"(?:体重|Weight)[：:]\s*(\d+\.?\d*)\s*(?:kg|公斤)?", text, re.IGNORECASE)
    if weight_match:
        demo["weight"] = float(weight_match.group(1))

    # Pregnancy
    if re.search(r"妊娠|怀孕|孕\d+周|pregnant", text, re.IGNORECASE):
        demo["pregnancy_status"] = True

    # Lactation
    if re.search(r"哺乳|母乳|lactating|breastfeeding", text, re.IGNORECASE):
        demo["lactation_status"] = True

    return demo


def extract_allergies(text: str) -> list:
    """Extract allergy history."""
    allergies = []

    allergy_section = re.search(
        r"(?:过敏史|药物过敏|Allergy)[：:]\s*(.+?)(?:\n|$|[。；;])",
        text,
        re.IGNORECASE,
    )
    if allergy_section:
        content = allergy_section.group(1)
        if not re.search(r"无|否认|未发现|none|nil", content, re.IGNORECASE):
            # Split by common delimiters
            items = re.split(r"[,，、；;]", content)
            allergies = [item.strip() for item in items if item.strip()]

    return allergies


def extract_diagnoses(text: str) -> list:
    """Extract diagnosis information."""
    diagnoses = []

    diag_section = re.search(
        r"(?:诊断|Diagnosis|印象)[：:]\s*(.+?)(?:\n\n|\n[^\d]|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if diag_section:
        content = diag_section.group(1)
        # Split numbered diagnoses
        items = re.split(r"\n\s*\d+[.、]|\n\s*[①②③④⑤]", content)
        if len(items) <= 1:
            items = re.split(r"[,，；;]", content)
        diagnoses = [item.strip() for item in items if item.strip()]

    return diagnoses


def extract_lab_results(text: str) -> dict:
    """Extract key lab results relevant to medication safety."""
    labs = {}

    lab_patterns = {
        "ALT": r"(?:ALT|谷丙转氨酶|丙氨酸氨基转移酶)[：:=\s]*(\d+\.?\d*)",
        "AST": r"(?:AST|谷草转氨酶|天门冬氨酸氨基转移酶)[：:=\s]*(\d+\.?\d*)",
        "Cr": r"(?:Cr|肌酐|血肌酐)[：:=\s]*(\d+\.?\d*)",
        "BUN": r"(?:BUN|尿素氮|血尿素氮)[：:=\s]*(\d+\.?\d*)",
        "eGFR": r"(?:eGFR|肾小球滤过率)[：:=\s]*(\d+\.?\d*)",
        "WBC": r"(?:WBC|白细胞)[：:=\s]*(\d+\.?\d*)",
        "PLT": r"(?:PLT|血小板)[：:=\s]*(\d+\.?\d*)",
        "Hb": r"(?:Hb|HGB|血红蛋白)[：:=\s]*(\d+\.?\d*)",
        "INR": r"(?:INR|国际标准化比值)[：:=\s]*(\d+\.?\d*)",
        "K": r"(?:K\+?|血钾)[：:=\s]*(\d+\.?\d*)",
    }

    for key, pattern in lab_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            labs[key] = float(match.group(1))

    return labs


def parse_medical_document(text: str) -> dict:
    """Main parsing function that orchestrates all extraction."""
    doc_type = detect_document_type(text)

    result = {
        "document_type": doc_type,
        "drugs_found": extract_drug_names(text),
        "dosage_info": extract_dosage_info(text),
        "demographics": extract_demographics(text),
        "allergies": extract_allergies(text),
        "diagnoses": extract_diagnoses(text),
        "lab_results": extract_lab_results(text),
        "raw_text_preview": text[:500] + ("..." if len(text) > 500 else ""),
    }

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_attachment.py <file_path>")
        print("  Parses medical documents and extracts medication-related data.")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    text = file_path.read_text(encoding="utf-8")
    result = parse_medical_document(text)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
