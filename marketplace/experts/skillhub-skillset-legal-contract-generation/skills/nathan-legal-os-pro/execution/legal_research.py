#!/usr/bin/env python3
"""
LegalDoc AI - Legal Research Assistant
AI-powered legal research across case law, statutes, and regulations.
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional
import urllib.request
import urllib.parse
import urllib.error


# API Configuration
COURTLISTENER_API = "https://www.courtlistener.com/api/rest/v3"
COURTLISTENER_KEY = os.environ.get("COURTLISTENER_API_KEY", "")

# Jurisdiction mappings
JURISDICTIONS = {
    "federal": ["scotus", "ca1", "ca2", "ca3", "ca4", "ca5", "ca6", "ca7", "ca8", "ca9", "ca10", "ca11", "cadc", "cafc"],
    "scotus": ["scotus"],
    "ca": ["cal", "calctapp", "calag"],
    "ny": ["ny", "nyappdiv", "nysupct"],
    "tx": ["tex", "texapp", "texcrimapp"],
    "fl": ["fla", "fladistctapp"],
    "il": ["ill", "illappct"],
    "pa": ["pa", "pasuperct"],
    "oh": ["ohio", "ohioctapp"],
    "ga": ["ga", "gactapp"],
    "mi": ["mich", "michctapp"],
    "nj": ["nj", "njsuperctappdiv"],
    "va": ["va", "vactapp"],
    "wa": ["wash", "washctapp"],
    "ma": ["mass", "massappct"],
    "az": ["ariz", "arizctapp"],
    "co": ["colo", "coloctapp"],
    "in": ["ind", "indctapp"],
    "tn": ["tenn", "tennctapp"],
    "mo": ["mo", "moctapp"],
    "md": ["md", "mdctspecapp"],
    "wi": ["wis", "wisctapp"],
    "mn": ["minn", "minnctapp"],
    "nc": ["nc", "ncctapp"],
    "al": ["ala", "alacivapp", "alacrimapp"],
}

# Research topic templates
RESEARCH_TEMPLATES = {
    "breach_of_contract": {
        "queries": [
            "breach of contract damages elements",
            "material breach contract requirements",
            "anticipatory breach remedies",
        ],
        "key_cases": [
            "Hadley v. Baxendale (consequential damages)",
            "Jacob & Youngs v. Kent (substantial performance)",
        ],
        "statutes": ["UCC Article 2", "Restatement (Second) of Contracts"]
    },
    "negligence": {
        "queries": [
            "negligence elements duty breach causation damages",
            "reasonable person standard negligence",
            "proximate cause foreseeability",
        ],
        "key_cases": [
            "Palsgraf v. Long Island Railroad (proximate cause)",
            "MacPherson v. Buick (duty of care)",
        ],
        "statutes": ["Restatement (Third) of Torts"]
    },
    "employment": {
        "queries": [
            "wrongful termination at-will employment",
            "employment discrimination Title VII",
            "wage and hour FLSA violations",
        ],
        "key_cases": [
            "McDonnell Douglas v. Green (burden shifting)",
            "Griggs v. Duke Power (disparate impact)",
        ],
        "statutes": ["Title VII", "FLSA", "FMLA", "ADA", "ADEA"]
    },
    "ip_infringement": {
        "queries": [
            "patent infringement claim construction",
            "copyright fair use four factors",
            "trademark likelihood confusion",
        ],
        "key_cases": [
            "Alice Corp. v. CLS Bank (patent eligibility)",
            "Sony v. Universal (fair use)",
        ],
        "statutes": ["35 U.S.C.", "17 U.S.C.", "Lanham Act"]
    },
    "securities": {
        "queries": [
            "securities fraud 10b-5 elements",
            "insider trading materiality",
            "securities offering exemptions",
        ],
        "key_cases": [
            "Basic v. Levinson (fraud on the market)",
            "SEC v. Texas Gulf Sulphur (insider trading)",
        ],
        "statutes": ["Securities Act 1933", "Exchange Act 1934", "Regulation D"]
    },
}


@dataclass
class CaseResult:
    """Represents a case law search result."""
    case_name: str
    citation: str
    court: str
    date_decided: str
    summary: str
    relevance_score: float
    url: Optional[str] = None
    key_holdings: list[str] = field(default_factory=list)


@dataclass
class StatuteResult:
    """Represents a statute or regulation result."""
    title: str
    section: str
    text: str
    jurisdiction: str
    effective_date: Optional[str] = None
    url: Optional[str] = None


@dataclass
class ResearchResult:
    """Complete research result package."""
    query: str
    jurisdiction: str
    research_type: str
    generated_at: str
    cases: list[CaseResult]
    statutes: list[StatuteResult]
    practice_notes: list[str]
    suggested_queries: list[str]
    
    def to_dict(self) -> dict:
        result = asdict(self)
        return result


def api_request(url: str, headers: dict = None) -> dict:
    """Make an API request and return JSON response."""
    if headers is None:
        headers = {}
    
    if COURTLISTENER_KEY:
        headers["Authorization"] = f"Token {COURTLISTENER_KEY}"
    
    headers["User-Agent"] = "LegalDoc-AI/1.0"
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Exception("Rate limited. Please wait and try again.")
        raise Exception(f"API error: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error: {e.reason}")


def search_courtlistener(query: str, jurisdiction: str = "federal") -> list[CaseResult]:
    """Search CourtListener for case law."""
    results = []
    
    # Build court filter
    courts = JURISDICTIONS.get(jurisdiction.lower(), JURISDICTIONS["federal"])
    court_filter = ",".join(courts)
    
    # URL encode query
    encoded_query = urllib.parse.quote(query)
    
    url = f"{COURTLISTENER_API}/search/?q={encoded_query}&type=o&court={court_filter}&order_by=score%20desc"
    
    try:
        data = api_request(url)
        
        for item in data.get("results", [])[:10]:
            case = CaseResult(
                case_name=item.get("caseName", "Unknown"),
                citation=item.get("citation", ["N/A"])[0] if item.get("citation") else "N/A",
                court=item.get("court", "Unknown Court"),
                date_decided=item.get("dateFiled", "Unknown"),
                summary=item.get("snippet", "")[:500] if item.get("snippet") else "",
                relevance_score=float(item.get("score", 0)),
                url=f"https://www.courtlistener.com{item.get('absolute_url', '')}",
                key_holdings=[]
            )
            results.append(case)
    
    except Exception as e:
        # Return mock results for demo if API fails
        print(f"Note: Using sample data (API: {e})", file=sys.stderr)
        results = generate_sample_cases(query, jurisdiction)
    
    return results


def generate_sample_cases(query: str, jurisdiction: str) -> list[CaseResult]:
    """Generate sample case results for demonstration."""
    
    # Detect topic from query
    query_lower = query.lower()
    
    sample_cases = []
    
    if "contract" in query_lower or "breach" in query_lower:
        sample_cases = [
            CaseResult(
                case_name="Hadley v. Baxendale",
                citation="156 Eng. Rep. 145 (1854)",
                court="Court of Exchequer",
                date_decided="1854-02-23",
                summary="Landmark case establishing the rule for consequential damages in contract. Damages must be foreseeable at time of contract formation.",
                relevance_score=0.95,
                url="https://en.wikipedia.org/wiki/Hadley_v_Baxendale",
                key_holdings=["Consequential damages must be foreseeable", "Notice of special circumstances required"]
            ),
            CaseResult(
                case_name="Jacob & Youngs, Inc. v. Kent",
                citation="230 N.Y. 239 (1921)",
                court="New York Court of Appeals",
                date_decided="1921-01-18",
                summary="Established substantial performance doctrine. Minor deviations from contract specifications may not justify withholding payment.",
                relevance_score=0.88,
                url=None,
                key_holdings=["Substantial performance doctrine", "Willfulness of breach matters"]
            ),
        ]
    
    elif "negligence" in query_lower or "tort" in query_lower:
        sample_cases = [
            CaseResult(
                case_name="Palsgraf v. Long Island Railroad Co.",
                citation="248 N.Y. 339 (1928)",
                court="New York Court of Appeals",
                date_decided="1928-05-29",
                summary="Foundational proximate cause case. Defendant not liable if injury to plaintiff was not foreseeable consequence of negligent act.",
                relevance_score=0.92,
                url=None,
                key_holdings=["Duty owed only to foreseeable plaintiffs", "Proximate cause limits liability"]
            ),
        ]
    
    elif "employment" in query_lower or "termination" in query_lower:
        sample_cases = [
            CaseResult(
                case_name="McDonnell Douglas Corp. v. Green",
                citation="411 U.S. 792 (1973)",
                court="Supreme Court of the United States",
                date_decided="1973-05-14",
                summary="Established burden-shifting framework for employment discrimination claims under Title VII.",
                relevance_score=0.94,
                url=None,
                key_holdings=["Prima facie case requirements", "Burden shifts to employer to show legitimate reason"]
            ),
        ]
    
    else:
        sample_cases = [
            CaseResult(
                case_name="Sample v. Example Corp.",
                citation="123 F.3d 456 (9th Cir. 2024)",
                court="Ninth Circuit Court of Appeals",
                date_decided="2024-06-15",
                summary=f"Sample case result for query: {query}. Connect API key for real results.",
                relevance_score=0.75,
                url=None,
                key_holdings=["Sample holding 1", "Sample holding 2"]
            ),
        ]
    
    return sample_cases


def search_statutes(query: str, jurisdiction: str = "federal") -> list[StatuteResult]:
    """Search for relevant statutes and regulations."""
    
    statutes = []
    query_lower = query.lower()
    
    # Match against known statutory frameworks
    statutory_references = {
        "contract": [
            StatuteResult(
                title="Uniform Commercial Code",
                section="Article 2 (Sales)",
                text="Governs contracts for the sale of goods. Key provisions include: breach remedies (§2-711 to §2-717), statute of frauds (§2-201), warranty (§2-312 to §2-318).",
                jurisdiction="State (adopted by 49 states)",
                url="https://www.law.cornell.edu/ucc/2"
            ),
        ],
        "employment": [
            StatuteResult(
                title="Fair Labor Standards Act",
                section="29 U.S.C. § 201 et seq.",
                text="Federal law establishing minimum wage, overtime pay, recordkeeping, and youth employment standards. Covers employees in private sector and government.",
                jurisdiction="Federal",
                url="https://www.law.cornell.edu/uscode/text/29/chapter-8"
            ),
            StatuteResult(
                title="Title VII of the Civil Rights Act",
                section="42 U.S.C. § 2000e et seq.",
                text="Prohibits employment discrimination based on race, color, religion, sex, or national origin. Applies to employers with 15+ employees.",
                jurisdiction="Federal",
                url="https://www.law.cornell.edu/uscode/text/42/2000e"
            ),
        ],
        "discrimination": [
            StatuteResult(
                title="Americans with Disabilities Act",
                section="42 U.S.C. § 12101 et seq.",
                text="Prohibits discrimination against individuals with disabilities in employment, public services, and accommodations.",
                jurisdiction="Federal",
                url="https://www.law.cornell.edu/uscode/text/42/12101"
            ),
        ],
        "copyright": [
            StatuteResult(
                title="Copyright Act",
                section="17 U.S.C. § 101 et seq.",
                text="Federal copyright protection for original works of authorship. Fair use codified at § 107. Registration and infringement at §§ 408-412, 501-513.",
                jurisdiction="Federal",
                url="https://www.law.cornell.edu/uscode/text/17"
            ),
        ],
        "patent": [
            StatuteResult(
                title="Patent Act",
                section="35 U.S.C. § 1 et seq.",
                text="Federal patent law. Patentability requirements (§§ 101-103), infringement (§ 271), remedies (§§ 281-287).",
                jurisdiction="Federal",
                url="https://www.law.cornell.edu/uscode/text/35"
            ),
        ],
        "securities": [
            StatuteResult(
                title="Securities Exchange Act",
                section="15 U.S.C. § 78a et seq.",
                text="Regulates secondary trading of securities. Rule 10b-5 (anti-fraud), insider trading prohibitions, reporting requirements.",
                jurisdiction="Federal",
                url="https://www.law.cornell.edu/uscode/text/15/78a"
            ),
        ],
        "privacy": [
            StatuteResult(
                title="California Consumer Privacy Act",
                section="Cal. Civ. Code § 1798.100 et seq.",
                text="Consumer privacy rights including right to know, delete, and opt-out of sale of personal information. As amended by CPRA.",
                jurisdiction="California",
                url="https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?division=3.&part=4.&lawCode=CIV&title=1.81.5"
            ),
        ],
    }
    
    # Find matching statutes
    for keyword, statute_list in statutory_references.items():
        if keyword in query_lower:
            statutes.extend(statute_list)
    
    # If jurisdiction-specific, filter
    if jurisdiction.lower() not in ["federal", "all"]:
        jurisdiction_name = jurisdiction.upper()
        statutes = [s for s in statutes if jurisdiction_name in s.jurisdiction.upper() or s.jurisdiction == "Federal"]
    
    return statutes[:5]


def generate_practice_notes(query: str, cases: list, statutes: list) -> list[str]:
    """Generate practice notes based on research results."""
    
    notes = []
    query_lower = query.lower()
    
    # General practice notes based on topic
    if "damages" in query_lower:
        notes.append("💡 Document all damages with specificity. Courts require proof of actual harm with reasonable certainty.")
    
    if "contract" in query_lower:
        notes.append("💡 Review the choice of law provision—UCC vs common law affects available remedies significantly.")
        notes.append("💡 Check statute of limitations: typically 4-6 years for written contracts, 2-4 years for oral.")
    
    if "negligence" in query_lower:
        notes.append("💡 Establish all four elements: duty, breach, causation, and damages. Weakness in any element is fatal.")
        notes.append("💡 Consider comparative/contributory negligence rules in your jurisdiction.")
    
    if "employment" in query_lower:
        notes.append("💡 Check administrative exhaustion requirements (EEOC filing for Title VII claims).")
        notes.append("💡 Review arbitration agreements—many employment contracts require arbitration.")
    
    if "liability" in query_lower:
        notes.append("💡 California courts increasingly pierce liability caps for willful/gross negligence breaches.")
    
    # Default notes
    if not notes:
        notes = [
            "💡 Verify all citations before relying on them in filings.",
            "💡 Check for subsequent history (overruling, distinguishing cases).",
            "💡 Consider jurisdiction-specific variations in legal standards.",
        ]
    
    return notes


def suggest_related_queries(query: str, results: list) -> list[str]:
    """Suggest related research queries."""
    
    suggestions = []
    query_lower = query.lower()
    
    # Topic-based suggestions
    if "breach" in query_lower and "contract" in query_lower:
        suggestions = [
            "specific performance breach of contract",
            "anticipatory repudiation remedies",
            "mitigation of damages contract law",
            "liquidated damages enforceability",
        ]
    elif "negligence" in query_lower:
        suggestions = [
            "comparative negligence apportionment",
            "duty of care professional malpractice",
            "negligence per se statutory violation",
            "gross negligence punitive damages",
        ]
    elif "employment" in query_lower:
        suggestions = [
            "at-will employment exceptions public policy",
            "constructive discharge hostile work environment",
            "retaliation whistleblower protection",
            "non-compete agreement enforceability",
        ]
    else:
        suggestions = [
            f"{query} jurisdiction specific",
            f"{query} recent developments 2024",
            f"{query} defense strategies",
            f"{query} damages calculation",
        ]
    
    return suggestions[:4]


def conduct_research(
    query: str,
    jurisdiction: str = "federal",
    research_type: str = "all"
) -> ResearchResult:
    """Conduct comprehensive legal research."""
    
    cases = []
    statutes = []
    
    if research_type in ["all", "case_law"]:
        cases = search_courtlistener(query, jurisdiction)
    
    if research_type in ["all", "statute", "regulation"]:
        statutes = search_statutes(query, jurisdiction)
    
    practice_notes = generate_practice_notes(query, cases, statutes)
    suggested_queries = suggest_related_queries(query, cases)
    
    return ResearchResult(
        query=query,
        jurisdiction=jurisdiction,
        research_type=research_type,
        generated_at=datetime.utcnow().isoformat() + "Z",
        cases=cases,
        statutes=statutes,
        practice_notes=practice_notes,
        suggested_queries=suggested_queries
    )


def format_research(result: ResearchResult, output_format: str = "markdown") -> str:
    """Format research results for output."""
    
    if output_format == "json":
        return json.dumps(result.to_dict(), indent=2, default=str)
    
    # Markdown format
    lines = [
        "# 🔍 Legal Research Results",
        "",
        f"**Query:** {result.query}",
        f"**Jurisdiction:** {result.jurisdiction.upper()}",
        f"**Type:** {result.research_type}",
        f"**Generated:** {result.generated_at}",
        "",
        "---",
        "",
    ]
    
    # Cases
    if result.cases:
        lines.extend([
            "## 📚 Relevant Case Law",
            ""
        ])
        
        for i, case in enumerate(result.cases, 1):
            relevance = int(case.relevance_score * 100)
            lines.append(f"### {i}. {case.case_name}")
            lines.append(f"**Citation:** {case.citation}")
            lines.append(f"**Court:** {case.court} | **Date:** {case.date_decided}")
            lines.append(f"**Relevance:** {relevance}%")
            lines.append("")
            lines.append(case.summary)
            
            if case.key_holdings:
                lines.append("")
                lines.append("**Key Holdings:**")
                for holding in case.key_holdings:
                    lines.append(f"  - {holding}")
            
            if case.url:
                lines.append(f"")
                lines.append(f"[View Full Case]({case.url})")
            
            lines.append("")
        
        lines.append("")
    
    # Statutes
    if result.statutes:
        lines.extend([
            "## 📖 Statutory Framework",
            ""
        ])
        
        for statute in result.statutes:
            lines.append(f"### {statute.title}")
            lines.append(f"**Section:** {statute.section}")
            lines.append(f"**Jurisdiction:** {statute.jurisdiction}")
            lines.append("")
            lines.append(statute.text)
            if statute.url:
                lines.append(f"")
                lines.append(f"[View Statute]({statute.url})")
            lines.append("")
        
        lines.append("")
    
    # Practice Notes
    if result.practice_notes:
        lines.extend([
            "## 💡 Practice Notes",
            ""
        ])
        for note in result.practice_notes:
            lines.append(note)
        lines.append("")
    
    # Suggested Queries
    if result.suggested_queries:
        lines.extend([
            "## 🔎 Related Research",
            ""
        ])
        for query in result.suggested_queries:
            lines.append(f"- `{query}`")
        lines.append("")
    
    lines.extend([
        "---",
        "",
        "*Research powered by LegalDoc AI. Verify all citations before use in legal filings.*"
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Conduct AI-powered legal research"
    )
    parser.add_argument("query", help="Research query")
    parser.add_argument(
        "--jurisdiction", "-j",
        default="federal",
        help="Jurisdiction (federal, ca, ny, tx, etc.)"
    )
    parser.add_argument(
        "--type", "-t",
        choices=["all", "case_law", "statute", "regulation"],
        default="all",
        help="Type of research"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format"
    )
    parser.add_argument(
        "--list-jurisdictions",
        action="store_true",
        help="List available jurisdictions"
    )
    
    args = parser.parse_args()
    
    if args.list_jurisdictions:
        print("Available jurisdictions:")
        for jur in sorted(JURISDICTIONS.keys()):
            print(f"  - {jur}")
        return
    
    try:
        print(f"Researching: {args.query}", file=sys.stderr)
        print(f"Jurisdiction: {args.jurisdiction}", file=sys.stderr)
        
        result = conduct_research(
            args.query,
            args.jurisdiction,
            args.type
        )
        
        output = format_research(result, args.output)
        print(output)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
