#!/usr/bin/env python3
"""
LegalDoc AI - Document Summarizer
Generates executive summaries for legal documents.
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import hashlib


# Document type detection patterns
DOCUMENT_TYPES = {
    "contract": {
        "patterns": [
            r"agreement",
            r"contract",
            r"terms\s+and\s+conditions",
            r"master\s+service",
            r"statement\s+of\s+work",
        ],
        "key_sections": [
            "parties", "term", "payment", "termination", "governing law"
        ]
    },
    "nda": {
        "patterns": [
            r"non-?disclosure",
            r"confidentiality\s+agreement",
            r"nda",
            r"mutual\s+confidentiality",
        ],
        "key_sections": [
            "definition of confidential", "obligations", "term", "exceptions"
        ]
    },
    "employment": {
        "patterns": [
            r"employment\s+agreement",
            r"offer\s+letter",
            r"employment\s+contract",
            r"at-will\s+employment",
        ],
        "key_sections": [
            "position", "compensation", "benefits", "termination", "non-compete"
        ]
    },
    "acquisition": {
        "patterns": [
            r"stock\s+purchase",
            r"asset\s+purchase",
            r"merger\s+agreement",
            r"acquisition\s+agreement",
        ],
        "key_sections": [
            "purchase price", "representations", "conditions", "closing", "indemnification"
        ]
    },
    "lease": {
        "patterns": [
            r"lease\s+agreement",
            r"rental\s+agreement",
            r"commercial\s+lease",
            r"tenancy\s+agreement",
        ],
        "key_sections": [
            "premises", "rent", "term", "maintenance", "termination"
        ]
    },
    "litigation": {
        "patterns": [
            r"complaint",
            r"motion\s+to",
            r"memorandum\s+of\s+law",
            r"brief\s+in\s+support",
        ],
        "key_sections": [
            "parties", "facts", "claims", "prayer for relief"
        ]
    },
}


@dataclass
class DocumentSummary:
    """Structured document summary."""
    document_name: str
    document_type: str
    summary_type: str
    generated_at: str
    
    # Core summary
    executive_summary: str
    
    # Parties
    parties: list[dict]
    
    # Key terms
    key_terms: list[dict]
    
    # Dates and deadlines
    key_dates: list[dict]
    
    # Risk assessment
    risk_summary: dict
    
    # Obligations
    obligations: list[dict]
    
    # Metadata
    page_count: Optional[int]
    word_count: int
    
    def to_dict(self) -> dict:
        return asdict(self)


def load_document(file_path: str) -> tuple[str, Optional[int]]:
    """Load document and return text with page count."""
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")
    
    suffix = path.suffix.lower()
    page_count = None
    
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8")
    
    elif suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            page_count = len(reader.pages)
            text = ""
            for i, page in enumerate(reader.pages):
                text += f"\n[PAGE {i+1}]\n"
                text += page.extract_text() or ""
        except ImportError:
            import subprocess
            result = subprocess.run(
                ["pdftotext", "-layout", file_path, "-"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                text = result.stdout
            else:
                raise RuntimeError("Cannot parse PDF. Install pypdf: pip install pypdf")
    
    elif suffix in [".docx", ".doc"]:
        try:
            import docx
            doc = docx.Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
        except ImportError:
            raise RuntimeError("Cannot parse DOCX. Install python-docx: pip install python-docx")
    
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    
    return text, page_count


def detect_document_type(text: str) -> str:
    """Detect the type of legal document."""
    text_lower = text.lower()[:5000]  # Check first 5000 chars
    
    for doc_type, config in DOCUMENT_TYPES.items():
        matches = sum(1 for p in config["patterns"] if re.search(p, text_lower))
        if matches >= 2:
            return doc_type
    
    return "general"


def extract_parties(text: str) -> list[dict]:
    """Extract parties from the document."""
    parties = []
    
    # Common party patterns
    patterns = [
        r'(?:between|by\s+and\s+between)\s+([A-Z][A-Za-z\s,\.]+?)(?:\s*\(|,\s*a)',
        r'"([A-Za-z\s]+)"\s+(?:means|refers\s+to)',
        r'([A-Z][A-Za-z\s]+(?:Inc\.|LLC|Corp\.|Ltd\.|Company))',
        r'PARTIES[:\s]+([^\n]+)',
    ]
    
    found_names = set()
    
    for pattern in patterns:
        matches = re.finditer(pattern, text[:3000])
        for match in matches:
            name = match.group(1).strip()
            # Clean up
            name = re.sub(r'\s+', ' ', name)
            if len(name) > 5 and len(name) < 100 and name not in found_names:
                found_names.add(name)
                parties.append({
                    "name": name,
                    "role": "party"  # Could be enhanced with role detection
                })
    
    return parties[:6]  # Limit to 6 parties


def extract_key_terms(text: str, doc_type: str) -> list[dict]:
    """Extract key terms and values from the document."""
    terms = []
    
    # Money patterns
    money_pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|M|B|USD))?'
    money_matches = re.finditer(money_pattern, text)
    for match in money_matches:
        value = match.group()
        # Find context
        start = max(0, match.start() - 50)
        context = text[start:match.start()].strip()
        terms.append({
            "type": "monetary_value",
            "value": value,
            "context": context[-50:] if context else "Amount"
        })
        if len(terms) >= 10:
            break
    
    # Duration patterns
    duration_pattern = r'(\d+)\s*(year|month|day|week)s?'
    duration_matches = re.finditer(duration_pattern, text, re.IGNORECASE)
    for match in duration_matches:
        value = f"{match.group(1)} {match.group(2)}s"
        start = max(0, match.start() - 50)
        context = text[start:match.start()].strip()
        terms.append({
            "type": "duration",
            "value": value,
            "context": context[-50:] if context else "Duration"
        })
        if len(terms) >= 15:
            break
    
    # Percentage patterns
    pct_pattern = r'(\d+(?:\.\d+)?)\s*%'
    pct_matches = re.finditer(pct_pattern, text)
    for match in pct_matches:
        value = f"{match.group(1)}%"
        start = max(0, match.start() - 50)
        context = text[start:match.start()].strip()
        terms.append({
            "type": "percentage",
            "value": value,
            "context": context[-50:] if context else "Rate"
        })
        if len(terms) >= 20:
            break
    
    return terms[:15]


def extract_dates(text: str) -> list[dict]:
    """Extract important dates from the document."""
    dates = []
    
    # Date patterns
    patterns = [
        (r'(?:effective\s+(?:as\s+of\s+)?)?(\w+\s+\d{1,2},?\s+\d{4})', "effective_date"),
        (r'(?:dated|as\s+of)\s+(\w+\s+\d{1,2},?\s+\d{4})', "document_date"),
        (r'(\d{1,2}/\d{1,2}/\d{4})', "date"),
        (r'(\d{4}-\d{2}-\d{2})', "date"),
        (r'(?:expire|expiration|termination).{0,30}(\w+\s+\d{1,2},?\s+\d{4})', "expiration_date"),
        (r'(?:deadline|due).{0,30}(\w+\s+\d{1,2},?\s+\d{4})', "deadline"),
    ]
    
    found = set()
    
    for pattern, date_type in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            date_str = match.group(1).strip()
            if date_str not in found:
                found.add(date_str)
                # Get context
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end]
                
                dates.append({
                    "date": date_str,
                    "type": date_type,
                    "context": context.strip()[:150]
                })
    
    return dates[:10]


def extract_obligations(text: str) -> list[dict]:
    """Extract key obligations from the document."""
    obligations = []
    
    # Obligation patterns
    obligation_patterns = [
        (r'shall\s+([^\.]{20,150})', "mandatory"),
        (r'must\s+([^\.]{20,150})', "mandatory"),
        (r'agrees?\s+to\s+([^\.]{20,150})', "agreement"),
        (r'will\s+(?:not\s+)?([^\.]{20,150})', "commitment"),
        (r'(?:is|are)\s+required\s+to\s+([^\.]{20,150})', "requirement"),
    ]
    
    seen = set()
    
    for pattern, ob_type in obligation_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            obligation = match.group(1).strip()
            
            # Clean up
            obligation = re.sub(r'\s+', ' ', obligation)
            
            # Create hash for deduplication
            ob_hash = hashlib.md5(obligation.lower().encode()).hexdigest()[:8]
            
            if ob_hash not in seen and len(obligation) > 20:
                seen.add(ob_hash)
                obligations.append({
                    "type": ob_type,
                    "text": obligation[:200],
                    "full_sentence": match.group(0)[:300]
                })
            
            if len(obligations) >= 15:
                break
    
    return obligations[:15]


def assess_document_risk(text: str, doc_type: str) -> dict:
    """Assess overall document risk profile."""
    
    risk_factors = {
        "high_risk": [],
        "medium_risk": [],
        "low_risk": [],
        "overall_risk": "medium",
        "score": 50
    }
    
    # High risk indicators
    high_risk_patterns = [
        (r'unlimited\s+liability', "Unlimited liability exposure"),
        (r'perpetual', "Perpetual obligations"),
        (r'sole\s+discretion', "Unilateral discretion clauses"),
        (r'waive[sd]?\s+(?:all\s+)?(?:right|claim)', "Waiver of rights"),
        (r'as-is', "As-is delivery (no warranties)"),
        (r'class\s+action\s+waiver', "Class action waiver"),
        (r'non-refundable', "Non-refundable payments"),
    ]
    
    # Medium risk indicators
    medium_risk_patterns = [
        (r'binding\s+arbitration', "Binding arbitration required"),
        (r'automatic\s+renewal', "Auto-renewal clause"),
        (r'assigns?\s+all\s+(?:right|ip)', "Broad IP assignment"),
        (r'worldwide', "Worldwide scope"),
    ]
    
    # Positive indicators
    positive_patterns = [
        (r'mutual', "Mutual/balanced terms"),
        (r'reasonable', "Reasonableness standards"),
        (r'cap(?:ped)?(?:\s+at|\s+liability)', "Liability caps in place"),
        (r'cure\s+period', "Cure period for breaches"),
    ]
    
    text_lower = text.lower()
    
    for pattern, description in high_risk_patterns:
        if re.search(pattern, text_lower):
            risk_factors["high_risk"].append(description)
    
    for pattern, description in medium_risk_patterns:
        if re.search(pattern, text_lower):
            risk_factors["medium_risk"].append(description)
    
    for pattern, description in positive_patterns:
        if re.search(pattern, text_lower):
            risk_factors["low_risk"].append(description)
    
    # Calculate overall score
    score = 50
    score += len(risk_factors["high_risk"]) * 15
    score += len(risk_factors["medium_risk"]) * 5
    score -= len(risk_factors["low_risk"]) * 10
    score = max(10, min(100, score))
    
    risk_factors["score"] = score
    
    if score >= 70:
        risk_factors["overall_risk"] = "high"
    elif score >= 40:
        risk_factors["overall_risk"] = "medium"
    else:
        risk_factors["overall_risk"] = "low"
    
    return risk_factors


def generate_executive_summary(
    text: str,
    doc_type: str,
    parties: list,
    key_terms: list,
    key_dates: list,
    risk_summary: dict
) -> str:
    """Generate a natural language executive summary."""
    
    # Build summary components
    summary_parts = []
    
    # Document type intro
    type_intros = {
        "contract": "This is a commercial agreement",
        "nda": "This Non-Disclosure Agreement",
        "employment": "This employment agreement",
        "acquisition": "This acquisition/purchase agreement",
        "lease": "This lease agreement",
        "litigation": "This litigation document",
        "general": "This legal document",
    }
    
    intro = type_intros.get(doc_type, "This document")
    
    # Parties
    if parties:
        party_names = [p["name"] for p in parties[:2]]
        if len(party_names) == 2:
            intro += f" is between {party_names[0]} and {party_names[1]}"
        elif len(party_names) == 1:
            intro += f" involves {party_names[0]}"
    
    summary_parts.append(intro + ".")
    
    # Key monetary terms
    money_terms = [t for t in key_terms if t["type"] == "monetary_value"]
    if money_terms:
        values = [t["value"] for t in money_terms[:3]]
        summary_parts.append(f"Key financial terms include: {', '.join(values)}.")
    
    # Duration
    duration_terms = [t for t in key_terms if t["type"] == "duration"]
    if duration_terms:
        primary_duration = duration_terms[0]["value"]
        summary_parts.append(f"The term spans {primary_duration}.")
    
    # Key dates
    if key_dates:
        date_info = key_dates[0]
        summary_parts.append(f"Important date: {date_info['date']} ({date_info['type'].replace('_', ' ')}).")
    
    # Risk assessment
    risk_level = risk_summary["overall_risk"]
    if risk_level == "high":
        summary_parts.append(
            f"⚠️ Risk assessment: HIGH. Key concerns include: {', '.join(risk_summary['high_risk'][:3])}."
        )
    elif risk_level == "medium":
        summary_parts.append(
            f"Risk assessment: MODERATE. Review flagged items before execution."
        )
    else:
        summary_parts.append(
            f"Risk assessment: LOW. Document appears to contain balanced terms."
        )
    
    return " ".join(summary_parts)


def summarize_document(
    file_path: str,
    summary_type: str = "executive",
    focus: Optional[str] = None,
    max_length: str = "medium"
) -> DocumentSummary:
    """Generate a comprehensive document summary."""
    
    # Load document
    text, page_count = load_document(file_path)
    word_count = len(text.split())
    
    # Detect document type
    doc_type = detect_document_type(text)
    
    # Extract components
    parties = extract_parties(text)
    key_terms = extract_key_terms(text, doc_type)
    key_dates = extract_dates(text)
    obligations = extract_obligations(text)
    risk_summary = assess_document_risk(text, doc_type)
    
    # Generate executive summary
    exec_summary = generate_executive_summary(
        text, doc_type, parties, key_terms, key_dates, risk_summary
    )
    
    return DocumentSummary(
        document_name=Path(file_path).name,
        document_type=doc_type,
        summary_type=summary_type,
        generated_at=datetime.utcnow().isoformat() + "Z",
        executive_summary=exec_summary,
        parties=parties,
        key_terms=key_terms,
        key_dates=key_dates,
        risk_summary=risk_summary,
        obligations=obligations,
        page_count=page_count,
        word_count=word_count
    )


def format_summary(summary: DocumentSummary, output_format: str = "markdown") -> str:
    """Format the summary for output."""
    
    if output_format == "json":
        return json.dumps(summary.to_dict(), indent=2)
    
    # Markdown format
    risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    
    lines = [
        f"# 📄 Document Summary",
        f"",
        f"**Document:** {summary.document_name}",
        f"**Type:** {summary.document_type.replace('_', ' ').title()}",
        f"**Generated:** {summary.generated_at}",
        f"**Pages:** {summary.page_count or 'N/A'} | **Words:** {summary.word_count:,}",
        f"",
        "---",
        "",
        "## 📋 Executive Summary",
        "",
        summary.executive_summary,
        "",
    ]
    
    # Parties
    if summary.parties:
        lines.extend([
            "## 👥 Parties",
            ""
        ])
        for party in summary.parties:
            lines.append(f"- **{party['name']}** ({party['role']})")
        lines.append("")
    
    # Key Terms
    if summary.key_terms:
        lines.extend([
            "## 💰 Key Terms",
            ""
        ])
        for term in summary.key_terms[:8]:
            lines.append(f"- **{term['type'].replace('_', ' ').title()}:** {term['value']} — _{term['context']}_")
        lines.append("")
    
    # Important Dates
    if summary.key_dates:
        lines.extend([
            "## 📅 Key Dates",
            ""
        ])
        for date in summary.key_dates[:6]:
            lines.append(f"- **{date['date']}** — {date['type'].replace('_', ' ').title()}")
        lines.append("")
    
    # Risk Assessment
    risk = summary.risk_summary
    risk_em = risk_emoji.get(risk['overall_risk'], "⚪")
    lines.extend([
        "## ⚠️ Risk Assessment",
        "",
        f"**Overall Risk:** {risk_em} {risk['overall_risk'].upper()} (Score: {risk['score']}/100)",
        ""
    ])
    
    if risk['high_risk']:
        lines.append("**High Risk Factors:**")
        for factor in risk['high_risk']:
            lines.append(f"  - 🔴 {factor}")
    
    if risk['medium_risk']:
        lines.append("**Medium Risk Factors:**")
        for factor in risk['medium_risk']:
            lines.append(f"  - 🟡 {factor}")
    
    if risk['low_risk']:
        lines.append("**Favorable Terms:**")
        for factor in risk['low_risk']:
            lines.append(f"  - 🟢 {factor}")
    
    lines.append("")
    
    # Key Obligations
    if summary.obligations:
        lines.extend([
            "## 📝 Key Obligations",
            ""
        ])
        for i, ob in enumerate(summary.obligations[:8], 1):
            lines.append(f"{i}. **{ob['type'].title()}:** {ob['text']}")
        lines.append("")
    
    lines.extend([
        "---",
        "",
        "*Generated by LegalDoc AI. Always verify against source document.*"
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate summaries for legal documents"
    )
    parser.add_argument("file_path", help="Path to the document to summarize")
    parser.add_argument(
        "--type", "-t",
        choices=["executive", "detailed", "bullet"],
        default="executive",
        help="Summary type"
    )
    parser.add_argument(
        "--length", "-l",
        choices=["short", "medium", "long"],
        default="medium",
        help="Summary length"
    )
    parser.add_argument(
        "--focus", "-f",
        choices=["obligations", "risks", "terms", "dates"],
        default=None,
        help="Focus area for summary"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format"
    )
    
    args = parser.parse_args()
    
    try:
        print(f"Analyzing document: {args.file_path}", file=sys.stderr)
        
        summary = summarize_document(
            args.file_path,
            summary_type=args.type,
            focus=args.focus,
            max_length=args.length
        )
        
        output = format_summary(summary, args.output)
        print(output)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
