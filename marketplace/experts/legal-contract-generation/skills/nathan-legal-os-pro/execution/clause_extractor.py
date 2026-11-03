#!/usr/bin/env python3
"""
LegalDoc AI - Contract Clause Extractor
Extracts and analyzes specific clauses from legal documents.
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from enum import Enum

# Clause type definitions with patterns and risk indicators
CLAUSE_TYPES = {
    "indemnification": {
        "patterns": [
            r"indemnif(?:y|ication|ied)",
            r"hold\s+harmless",
            r"defend\s+and\s+indemnify",
        ],
        "section_headers": ["indemnification", "indemnity", "hold harmless"],
        "risk_indicators": {
            "high": ["unlimited", "sole expense", "any and all", "broadly"],
            "medium": ["reasonable", "pro rata", "mutual"],
            "low": ["capped", "limited to", "not to exceed"],
        },
    },
    "limitation_of_liability": {
        "patterns": [
            r"limitation\s+of\s+liability",
            r"liability\s+(?:shall|will)\s+(?:not|never)\s+exceed",
            r"aggregate\s+liability",
            r"in\s+no\s+event\s+shall.*liable",
        ],
        "section_headers": ["limitation of liability", "liability cap", "damages limitation"],
        "risk_indicators": {
            "high": ["excludes", "waives", "no liability"],
            "medium": ["fees paid", "12 months", "contract value"],
            "low": ["mutual", "balanced", "reciprocal"],
        },
    },
    "termination": {
        "patterns": [
            r"terminat(?:e|ion|ed)",
            r"(?:either|any)\s+party\s+may\s+terminate",
            r"termination\s+for\s+(?:cause|convenience)",
        ],
        "section_headers": ["termination", "term and termination", "cancellation"],
        "risk_indicators": {
            "high": ["immediate", "without cause", "sole discretion"],
            "medium": ["30 days", "cure period", "mutual"],
            "low": ["90 days", "wind-down", "transition assistance"],
        },
    },
    "force_majeure": {
        "patterns": [
            r"force\s+majeure",
            r"act\s+of\s+god",
            r"beyond\s+(?:the\s+)?(?:reasonable\s+)?control",
            r"unforeseeable\s+circumstances",
        ],
        "section_headers": ["force majeure", "excused performance", "impossibility"],
        "risk_indicators": {
            "high": ["pandemic exclusion", "narrow definition"],
            "medium": ["standard", "typical"],
            "low": ["broad definition", "includes pandemic", "includes supply chain"],
        },
    },
    "confidentiality": {
        "patterns": [
            r"confidential(?:ity)?",
            r"non-disclosure",
            r"proprietary\s+information",
            r"trade\s+secret",
        ],
        "section_headers": ["confidentiality", "non-disclosure", "nda", "proprietary information"],
        "risk_indicators": {
            "high": ["perpetual", "unlimited duration", "no exceptions"],
            "medium": ["3-5 years", "standard exceptions"],
            "low": ["1-2 years", "mutual", "clear carve-outs"],
        },
    },
    "non_compete": {
        "patterns": [
            r"non-?compete",
            r"covenant\s+not\s+to\s+compete",
            r"restrictive\s+covenant",
            r"non-?solicitation",
        ],
        "section_headers": ["non-compete", "non-solicitation", "restrictive covenants"],
        "risk_indicators": {
            "high": ["worldwide", "5+ years", "all industries"],
            "medium": ["2-3 years", "regional", "specific industry"],
            "low": ["1 year", "narrow scope", "specific customers"],
        },
    },
    "ip_assignment": {
        "patterns": [
            r"intellectual\s+property\s+(?:assignment|transfer)",
            r"work\s+(?:made\s+)?for\s+hire",
            r"assigns?\s+(?:all\s+)?(?:right|title|interest)",
            r"ownership\s+of\s+(?:work|deliverables|ip)",
        ],
        "section_headers": ["intellectual property", "ip rights", "ownership", "work for hire"],
        "risk_indicators": {
            "high": ["all ip", "perpetual", "worldwide", "no license back"],
            "medium": ["deliverables only", "limited license back"],
            "low": ["mutual ownership", "broad license back", "pre-existing ip excluded"],
        },
    },
    "governing_law": {
        "patterns": [
            r"governing\s+law",
            r"governed\s+by\s+(?:the\s+)?laws?\s+of",
            r"jurisdiction",
            r"choice\s+of\s+law",
        ],
        "section_headers": ["governing law", "jurisdiction", "choice of law", "applicable law"],
        "risk_indicators": {
            "high": ["foreign jurisdiction", "unfavorable state"],
            "medium": ["neutral jurisdiction"],
            "low": ["home jurisdiction", "favorable state"],
        },
    },
    "dispute_resolution": {
        "patterns": [
            r"dispute\s+resolution",
            r"arbitration",
            r"mediation",
            r"(?:exclusive\s+)?jurisdiction",
        ],
        "section_headers": ["dispute resolution", "arbitration", "mediation", "disputes"],
        "risk_indicators": {
            "high": ["binding arbitration", "waives jury", "class action waiver"],
            "medium": ["mediation first", "optional arbitration"],
            "low": ["litigation permitted", "local courts", "jury trial preserved"],
        },
    },
    "payment_terms": {
        "patterns": [
            r"payment\s+terms?",
            r"net\s+\d+",
            r"(?:due|payable)\s+(?:upon|within)",
            r"late\s+(?:fee|payment|penalty)",
        ],
        "section_headers": ["payment", "fees", "compensation", "invoicing"],
        "risk_indicators": {
            "high": ["payment in advance", "non-refundable", "high late fees"],
            "medium": ["net 30", "standard terms"],
            "low": ["net 60+", "milestone-based", "refundable"],
        },
    },
    "representations_warranties": {
        "patterns": [
            r"represent(?:s|ation)?(?:\s+and\s+warrant(?:s|y|ies)?)?",
            r"warrant(?:s|y|ies)?",
            r"covenants?\s+that",
        ],
        "section_headers": ["representations and warranties", "warranties", "representations"],
        "risk_indicators": {
            "high": ["as-is", "no warranties", "disclaimer"],
            "medium": ["limited warranty", "standard reps"],
            "low": ["full warranty", "comprehensive reps", "survival period"],
        },
    },
    "change_of_control": {
        "patterns": [
            r"change\s+of\s+control",
            r"merger\s+or\s+acquisition",
            r"assignment\s+(?:upon|following)\s+(?:merger|acquisition)",
            r"(?:sale|transfer)\s+of\s+(?:all|substantially\s+all)",
        ],
        "section_headers": ["change of control", "assignment", "successors"],
        "risk_indicators": {
            "high": ["automatic termination", "requires consent"],
            "medium": ["notice required", "option to terminate"],
            "low": ["binding on successors", "no consent needed"],
        },
    },
}


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass
class ExtractedClause:
    """Represents an extracted clause from a document."""
    clause_type: str
    section: Optional[str]
    page: Optional[int]
    text: str
    risk_level: str
    risk_notes: str
    suggested_revision: Optional[str]
    confidence: float
    
    def to_dict(self) -> dict:
        return asdict(self)


def load_document(file_path: str) -> str:
    """
    Load document content. Supports PDF, DOCX, TXT.
    In production, integrate with document parsing libraries.
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")
    
    suffix = path.suffix.lower()
    
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    
    elif suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            text = ""
            for i, page in enumerate(reader.pages):
                text += f"\n[PAGE {i+1}]\n"
                text += page.extract_text() or ""
            return text
        except ImportError:
            # Fallback: use external tool
            import subprocess
            result = subprocess.run(
                ["pdftotext", "-layout", file_path, "-"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout
            raise RuntimeError(f"Cannot parse PDF. Install pypdf: pip install pypdf")
    
    elif suffix in [".docx", ".doc"]:
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        except ImportError:
            raise RuntimeError("Cannot parse DOCX. Install python-docx: pip install python-docx")
    
    else:
        # Try as plain text
        return path.read_text(encoding="utf-8", errors="ignore")


def find_section_boundaries(text: str) -> list[tuple[str, int, int]]:
    """Find section headers and their boundaries in the document."""
    sections = []
    
    # Pattern for section headers like "1.", "1.1", "Section 1", "ARTICLE I"
    section_pattern = re.compile(
        r'^(?:(?:SECTION|ARTICLE|§)\s*)?(\d+(?:\.\d+)*\.?)\s*[:\.\s]+([A-Z][A-Za-z\s]+)',
        re.MULTILINE
    )
    
    matches = list(section_pattern.finditer(text))
    
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_num = match.group(1)
        section_title = match.group(2).strip()
        sections.append((f"{section_num} {section_title}", start, end))
    
    return sections


def extract_page_number(text: str, position: int) -> Optional[int]:
    """Extract page number based on position in text."""
    # Look for [PAGE X] markers
    page_pattern = re.compile(r'\[PAGE\s+(\d+)\]')
    
    # Find all page markers before this position
    text_before = text[:position]
    matches = list(page_pattern.finditer(text_before))
    
    if matches:
        return int(matches[-1].group(1))
    
    return None


def assess_risk_level(text: str, clause_type: str) -> tuple[RiskLevel, str]:
    """Assess risk level of a clause based on indicators."""
    clause_config = CLAUSE_TYPES.get(clause_type, {})
    risk_indicators = clause_config.get("risk_indicators", {})
    
    text_lower = text.lower()
    
    # Check for high risk indicators
    high_matches = [ind for ind in risk_indicators.get("high", []) if ind.lower() in text_lower]
    if high_matches:
        return RiskLevel.HIGH, f"Contains high-risk terms: {', '.join(high_matches)}"
    
    # Check for medium risk indicators
    medium_matches = [ind for ind in risk_indicators.get("medium", []) if ind.lower() in text_lower]
    if medium_matches:
        return RiskLevel.MEDIUM, f"Contains standard terms: {', '.join(medium_matches)}"
    
    # Check for low risk indicators
    low_matches = [ind for ind in risk_indicators.get("low", []) if ind.lower() in text_lower]
    if low_matches:
        return RiskLevel.LOW, f"Contains favorable terms: {', '.join(low_matches)}"
    
    return RiskLevel.UNKNOWN, "Unable to assess risk level automatically"


def generate_revision_suggestion(clause_type: str, risk_level: RiskLevel) -> Optional[str]:
    """Generate suggested revisions based on clause type and risk."""
    suggestions = {
        "indemnification": {
            RiskLevel.HIGH: "Consider: (1) Add mutual indemnification, (2) Cap at contract value or insurance limits, (3) Add carve-outs for gross negligence/willful misconduct, (4) Require prompt notice and cooperation",
            RiskLevel.MEDIUM: "Consider: (1) Verify insurance coverage aligns, (2) Add defense cost provisions",
        },
        "limitation_of_liability": {
            RiskLevel.HIGH: "Consider: (1) Add carve-outs for IP infringement, data breach, confidentiality breach, (2) Ensure liability cap covers realistic exposure, (3) Add consequential damages carve-outs for key obligations",
            RiskLevel.MEDIUM: "Consider: (1) Verify cap amount is sufficient, (2) Confirm mutual application",
        },
        "termination": {
            RiskLevel.HIGH: "Consider: (1) Add cure period (30-60 days), (2) Require wind-down/transition period, (3) Add data return provisions, (4) Clarify survival of key provisions",
            RiskLevel.MEDIUM: "Consider: (1) Align notice period with business needs, (2) Add termination fee provisions if applicable",
        },
        "ip_assignment": {
            RiskLevel.HIGH: "Consider: (1) Carve out pre-existing IP, (2) Obtain license back for assigned IP, (3) Limit to deliverables only, (4) Add joint ownership provisions for collaborative work",
            RiskLevel.MEDIUM: "Consider: (1) Clarify ownership of improvements, (2) Define deliverables precisely",
        },
        "non_compete": {
            RiskLevel.HIGH: "Consider: (1) Narrow geographic scope, (2) Reduce duration (1-2 years), (3) Limit to specific product lines/customers, (4) Review enforceability in jurisdiction",
            RiskLevel.MEDIUM: "Consider: (1) Verify compliance with state law, (2) Add garden leave provisions",
        },
    }
    
    clause_suggestions = suggestions.get(clause_type, {})
    return clause_suggestions.get(risk_level)


def extract_clauses(
    text: str,
    clause_types: Optional[list[str]] = None,
    min_confidence: float = 0.5
) -> list[ExtractedClause]:
    """Extract specified clause types from document text."""
    
    if clause_types is None:
        clause_types = list(CLAUSE_TYPES.keys())
    
    extracted = []
    sections = find_section_boundaries(text)
    
    for clause_type in clause_types:
        if clause_type not in CLAUSE_TYPES:
            continue
        
        config = CLAUSE_TYPES[clause_type]
        patterns = config["patterns"]
        
        # Search for clause patterns
        for pattern in patterns:
            regex = re.compile(pattern, re.IGNORECASE)
            
            for match in regex.finditer(text):
                # Find surrounding context (paragraph)
                start = max(0, match.start() - 500)
                end = min(len(text), match.end() + 1500)
                
                # Expand to paragraph boundaries
                while start > 0 and text[start] != '\n':
                    start -= 1
                while end < len(text) and text[end] != '\n':
                    end += 1
                
                context = text[start:end].strip()
                
                # Skip if too short
                if len(context) < 100:
                    continue
                
                # Find section
                section = None
                for sec_name, sec_start, sec_end in sections:
                    if sec_start <= match.start() < sec_end:
                        section = sec_name
                        break
                
                # Get page number
                page = extract_page_number(text, match.start())
                
                # Assess risk
                risk_level, risk_notes = assess_risk_level(context, clause_type)
                
                # Generate suggestion
                suggestion = generate_revision_suggestion(clause_type, risk_level)
                
                # Calculate confidence based on pattern match quality
                confidence = 0.7 if len(context) > 300 else 0.5
                if section:
                    confidence += 0.1
                if any(header in section.lower() if section else False 
                       for header in config.get("section_headers", [])):
                    confidence += 0.2
                confidence = min(confidence, 1.0)
                
                if confidence >= min_confidence:
                    extracted.append(ExtractedClause(
                        clause_type=clause_type,
                        section=section,
                        page=page,
                        text=context[:2000],  # Limit text length
                        risk_level=risk_level.value,
                        risk_notes=risk_notes,
                        suggested_revision=suggestion,
                        confidence=round(confidence, 2)
                    ))
                
                break  # One match per pattern type is enough
    
    # Deduplicate by position (keep highest confidence)
    seen_positions = {}
    unique_extracted = []
    
    for clause in extracted:
        key = (clause.clause_type, clause.section)
        if key not in seen_positions or clause.confidence > seen_positions[key].confidence:
            seen_positions[key] = clause
    
    unique_extracted = list(seen_positions.values())
    
    return sorted(unique_extracted, key=lambda x: (x.page or 0, x.clause_type))


def format_output(
    clauses: list[ExtractedClause],
    document_name: str,
    output_format: str = "markdown"
) -> str:
    """Format extracted clauses for output."""
    
    if output_format == "json":
        return json.dumps({
            "document": document_name,
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "clause_count": len(clauses),
            "clauses": [c.to_dict() for c in clauses]
        }, indent=2)
    
    elif output_format == "table":
        lines = [
            f"{'Type':<25} {'Section':<15} {'Page':<6} {'Risk':<8} {'Confidence':<10}",
            "-" * 80
        ]
        for c in clauses:
            lines.append(
                f"{c.clause_type:<25} {(c.section or 'N/A')[:15]:<15} "
                f"{str(c.page or 'N/A'):<6} {c.risk_level:<8} {c.confidence:<10}"
            )
        return "\n".join(lines)
    
    else:  # markdown
        risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢", "unknown": "⚪"}
        
        lines = [
            f"# Clause Extraction Report",
            f"",
            f"**Document:** {document_name}",
            f"**Analyzed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Clauses Found:** {len(clauses)}",
            f"",
            "---",
            ""
        ]
        
        for clause in clauses:
            emoji = risk_emoji.get(clause.risk_level, "⚪")
            
            lines.append(f"## {emoji} {clause.clause_type.replace('_', ' ').title()}")
            if clause.section:
                lines.append(f"**Section:** {clause.section}")
            if clause.page:
                lines.append(f"**Page:** {clause.page}")
            lines.append(f"**Risk Level:** {clause.risk_level.upper()}")
            lines.append(f"**Confidence:** {clause.confidence * 100:.0f}%")
            lines.append("")
            lines.append("### Extracted Text")
            lines.append(f"> {clause.text[:500]}...")
            lines.append("")
            lines.append(f"**Analysis:** {clause.risk_notes}")
            if clause.suggested_revision:
                lines.append("")
                lines.append(f"**💡 Suggested Revisions:** {clause.suggested_revision}")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and analyze clauses from legal documents"
    )
    parser.add_argument("file_path", nargs="?", help="Path to the document to analyze")
    parser.add_argument(
        "--type", "-t",
        help="Comma-separated clause types to extract (default: all)",
        default=None
    )
    parser.add_argument(
        "--output", "-o",
        choices=["markdown", "json", "table"],
        default="markdown",
        help="Output format"
    )
    parser.add_argument(
        "--min-confidence", "-c",
        type=float,
        default=0.5,
        help="Minimum confidence threshold (0-1)"
    )
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="List available clause types and exit"
    )
    
    args = parser.parse_args()
    
    if args.list_types:
        print("Available clause types:")
        for ct in CLAUSE_TYPES.keys():
            print(f"  - {ct}")
        return
    
    # Parse clause types
    clause_types = None
    if args.type:
        clause_types = [t.strip() for t in args.type.split(",")]
    
    try:
        # Load and process document
        print(f"Loading document: {args.file_path}", file=sys.stderr)
        text = load_document(args.file_path)
        
        print(f"Extracting clauses...", file=sys.stderr)
        clauses = extract_clauses(text, clause_types, args.min_confidence)
        
        # Format and output
        document_name = Path(args.file_path).name
        output = format_output(clauses, document_name, args.output)
        print(output)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
