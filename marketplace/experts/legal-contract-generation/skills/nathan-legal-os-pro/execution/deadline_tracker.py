#!/usr/bin/env python3
"""
LegalDoc AI - Deadline Tracker
Automated legal deadline management and alerting system.
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional
import sqlite3
import hashlib


# Default storage location
DEFAULT_DB_PATH = os.environ.get(
    "LEGALDOC_DEADLINES_DB",
    os.path.expanduser("~/.legaldoc/deadlines.db")
)

# Deadline categories with default rules
DEADLINE_CATEGORIES = {
    "court_filing": {
        "description": "Court filing deadlines",
        "default_alert_days": [7, 3, 1],
        "priority": "high",
        "color": "red"
    },
    "discovery": {
        "description": "Discovery deadlines (interrogatories, depositions, etc.)",
        "default_alert_days": [14, 7, 3],
        "priority": "high",
        "color": "orange"
    },
    "statute_of_limitations": {
        "description": "Statute of limitations deadlines",
        "default_alert_days": [90, 30, 14, 7],
        "priority": "critical",
        "color": "red"
    },
    "contract_milestone": {
        "description": "Contract performance milestones",
        "default_alert_days": [30, 14, 7],
        "priority": "medium",
        "color": "yellow"
    },
    "regulatory": {
        "description": "Regulatory filing or compliance deadlines",
        "default_alert_days": [30, 14, 7, 3],
        "priority": "high",
        "color": "orange"
    },
    "corporate": {
        "description": "Corporate governance (board meetings, filings)",
        "default_alert_days": [14, 7, 3],
        "priority": "medium",
        "color": "blue"
    },
    "client_meeting": {
        "description": "Client meetings and consultations",
        "default_alert_days": [3, 1],
        "priority": "low",
        "color": "green"
    },
    "internal": {
        "description": "Internal deadlines and reminders",
        "default_alert_days": [7, 1],
        "priority": "low",
        "color": "gray"
    },
}

# Statute of limitations by claim type (California defaults)
STATUTE_OF_LIMITATIONS = {
    "personal_injury": {"years": 2, "statute": "CCP § 335.1"},
    "medical_malpractice": {"years": 1, "statute": "CCP § 340.5", "notes": "Discovery rule may apply"},
    "wrongful_death": {"years": 2, "statute": "CCP § 335.1"},
    "breach_written_contract": {"years": 4, "statute": "CCP § 337"},
    "breach_oral_contract": {"years": 2, "statute": "CCP § 339"},
    "fraud": {"years": 3, "statute": "CCP § 338(d)", "notes": "Discovery rule applies"},
    "defamation": {"years": 1, "statute": "CCP § 340(c)"},
    "property_damage": {"years": 3, "statute": "CCP § 338(b)"},
    "employment_discrimination": {"years": 1, "statute": "Gov. Code § 12960", "notes": "File with DFEH first"},
    "title_vii": {"days": 300, "statute": "42 USC § 2000e-5", "notes": "EEOC charge required"},
    "wage_claim": {"years": 3, "statute": "CCP § 338", "notes": "Labor Code § 203 penalties: 4 years"},
}


@dataclass
class Deadline:
    """Represents a tracked legal deadline."""
    id: str
    description: str
    date: str  # ISO format YYYY-MM-DD
    category: str
    matter_id: Optional[str] = None
    matter_name: Optional[str] = None
    court: Optional[str] = None
    case_number: Optional[str] = None
    notes: Optional[str] = None
    alert_days: list[int] = field(default_factory=lambda: [7, 3, 1])
    completed: bool = False
    completed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source_document: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Deadline":
        return cls(**data)
    
    def days_until(self) -> int:
        deadline_date = datetime.strptime(self.date, "%Y-%m-%d").date()
        today = datetime.now().date()
        return (deadline_date - today).days
    
    def is_overdue(self) -> bool:
        return self.days_until() < 0 and not self.completed
    
    def urgency_level(self) -> str:
        days = self.days_until()
        if self.completed:
            return "completed"
        elif days < 0:
            return "overdue"
        elif days <= 3:
            return "critical"
        elif days <= 7:
            return "urgent"
        elif days <= 14:
            return "soon"
        else:
            return "normal"


class DeadlineDatabase:
    """SQLite-based deadline storage."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                matter_id TEXT,
                matter_name TEXT,
                court TEXT,
                case_number TEXT,
                notes TEXT,
                alert_days TEXT,
                completed INTEGER DEFAULT 0,
                completed_at TEXT,
                created_at TEXT,
                source_document TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_deadline_date 
            ON deadlines(date)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_deadline_matter 
            ON deadlines(matter_id)
        """)
        
        conn.commit()
        conn.close()
    
    def add(self, deadline: Deadline) -> bool:
        """Add a deadline to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO deadlines 
                (id, description, date, category, matter_id, matter_name, court, 
                 case_number, notes, alert_days, completed, completed_at, created_at, source_document)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                deadline.id,
                deadline.description,
                deadline.date,
                deadline.category,
                deadline.matter_id,
                deadline.matter_name,
                deadline.court,
                deadline.case_number,
                deadline.notes,
                json.dumps(deadline.alert_days),
                1 if deadline.completed else 0,
                deadline.completed_at,
                deadline.created_at,
                deadline.source_document
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def update(self, deadline: Deadline) -> bool:
        """Update an existing deadline."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE deadlines SET
                description = ?,
                date = ?,
                category = ?,
                matter_id = ?,
                matter_name = ?,
                court = ?,
                case_number = ?,
                notes = ?,
                alert_days = ?,
                completed = ?,
                completed_at = ?
            WHERE id = ?
        """, (
            deadline.description,
            deadline.date,
            deadline.category,
            deadline.matter_id,
            deadline.matter_name,
            deadline.court,
            deadline.case_number,
            deadline.notes,
            json.dumps(deadline.alert_days),
            1 if deadline.completed else 0,
            deadline.completed_at,
            deadline.id
        ))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated
    
    def get(self, deadline_id: str) -> Optional[Deadline]:
        """Get a deadline by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM deadlines WHERE id = ?", (deadline_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_deadline(row)
        return None
    
    def list_upcoming(self, days: int = 30, include_completed: bool = False) -> list[Deadline]:
        """List upcoming deadlines."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        
        if include_completed:
            cursor.execute("""
                SELECT * FROM deadlines 
                WHERE date <= ? AND date >= ?
                ORDER BY date ASC
            """, (end_date, today))
        else:
            cursor.execute("""
                SELECT * FROM deadlines 
                WHERE date <= ? AND date >= ? AND completed = 0
                ORDER BY date ASC
            """, (end_date, today))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_deadline(row) for row in rows]
    
    def list_overdue(self) -> list[Deadline]:
        """List overdue deadlines."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute("""
            SELECT * FROM deadlines 
            WHERE date < ? AND completed = 0
            ORDER BY date ASC
        """, (today,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_deadline(row) for row in rows]
    
    def list_by_matter(self, matter_id: str) -> list[Deadline]:
        """List deadlines for a specific matter."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM deadlines 
            WHERE matter_id = ?
            ORDER BY date ASC
        """, (matter_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_deadline(row) for row in rows]
    
    def mark_complete(self, deadline_id: str) -> bool:
        """Mark a deadline as completed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE deadlines 
            SET completed = 1, completed_at = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), deadline_id))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated
    
    def delete(self, deadline_id: str) -> bool:
        """Delete a deadline."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
    
    def _row_to_deadline(self, row: tuple) -> Deadline:
        """Convert database row to Deadline object."""
        return Deadline(
            id=row[0],
            description=row[1],
            date=row[2],
            category=row[3],
            matter_id=row[4],
            matter_name=row[5],
            court=row[6],
            case_number=row[7],
            notes=row[8],
            alert_days=json.loads(row[9]) if row[9] else [7, 3, 1],
            completed=bool(row[10]),
            completed_at=row[11],
            created_at=row[12],
            source_document=row[13]
        )


def extract_deadlines_from_document(file_path: str) -> list[Deadline]:
    """Extract deadlines from a legal document."""
    
    # Load document
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")
    
    # Read text (simplified - in production use proper parsers)
    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8")
    elif path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise RuntimeError("Install pypdf: pip install pypdf")
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    
    deadlines = []
    
    # Date patterns
    date_patterns = [
        (r'(?:due|deadline|by|before|no later than)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})', "deadline"),
        (r'(?:hearing|trial|conference)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})', "court_filing"),
        (r'(?:response|reply|answer)\s+(?:due|deadline)[:\s]+(\w+\s+\d{1,2},?\s+\d{4})', "court_filing"),
        (r'(?:discovery|deposition)[:\s]+.*?(\w+\s+\d{1,2},?\s+\d{4})', "discovery"),
        (r'(?:expire|expiration|terminate)[:\s]+.*?(\w+\s+\d{1,2},?\s+\d{4})', "contract_milestone"),
        (r'(\d{1,2}/\d{1,2}/\d{4})', "deadline"),
        (r'(\d{4}-\d{2}-\d{2})', "deadline"),
    ]
    
    found_dates = set()
    
    for pattern, category in date_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            date_str = match.group(1).strip()
            
            # Parse date
            parsed_date = None
            for fmt in ["%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%Y-%m-%d"]:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            
            if not parsed_date:
                continue
            
            iso_date = parsed_date.strftime("%Y-%m-%d")
            
            if iso_date in found_dates:
                continue
            found_dates.add(iso_date)
            
            # Get context
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()
            context = re.sub(r'\s+', ' ', context)
            
            # Generate ID
            deadline_id = hashlib.md5(
                f"{iso_date}:{context[:50]}".encode()
            ).hexdigest()[:12]
            
            deadline = Deadline(
                id=deadline_id,
                description=context[:200],
                date=iso_date,
                category=category,
                source_document=path.name
            )
            
            deadlines.append(deadline)
    
    return deadlines


def calculate_sol_deadline(
    incident_date: str,
    claim_type: str,
    jurisdiction: str = "CA"
) -> Optional[Deadline]:
    """Calculate statute of limitations deadline."""
    
    sol_info = STATUTE_OF_LIMITATIONS.get(claim_type.lower().replace(" ", "_"))
    if not sol_info:
        return None
    
    incident = datetime.strptime(incident_date, "%Y-%m-%d")
    
    if "years" in sol_info:
        deadline_date = incident.replace(year=incident.year + sol_info["years"])
    elif "days" in sol_info:
        deadline_date = incident + timedelta(days=sol_info["days"])
    else:
        return None
    
    deadline_id = hashlib.md5(
        f"sol:{claim_type}:{incident_date}".encode()
    ).hexdigest()[:12]
    
    notes = f"Statute: {sol_info['statute']}"
    if "notes" in sol_info:
        notes += f"\n{sol_info['notes']}"
    
    return Deadline(
        id=deadline_id,
        description=f"Statute of Limitations - {claim_type.replace('_', ' ').title()}",
        date=deadline_date.strftime("%Y-%m-%d"),
        category="statute_of_limitations",
        notes=notes,
        alert_days=[90, 30, 14, 7, 3, 1]
    )


def format_deadlines(
    deadlines: list[Deadline],
    output_format: str = "markdown",
    show_completed: bool = False
) -> str:
    """Format deadlines for output."""
    
    if not show_completed:
        deadlines = [d for d in deadlines if not d.completed]
    
    if output_format == "json":
        return json.dumps([d.to_dict() for d in deadlines], indent=2)
    
    # Markdown format
    urgency_emoji = {
        "overdue": "🔴",
        "critical": "🔴",
        "urgent": "🟠",
        "soon": "🟡",
        "normal": "🟢",
        "completed": "✅"
    }
    
    lines = [
        "# 📅 Legal Deadline Tracker",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Total Deadlines:** {len(deadlines)}",
        "",
        "---",
        ""
    ]
    
    # Group by urgency
    overdue = [d for d in deadlines if d.is_overdue()]
    critical = [d for d in deadlines if d.urgency_level() == "critical"]
    upcoming = [d for d in deadlines if d.urgency_level() in ["urgent", "soon", "normal"]]
    
    if overdue:
        lines.extend([
            "## 🚨 OVERDUE",
            ""
        ])
        for d in overdue:
            days = abs(d.days_until())
            lines.append(f"- **{d.date}** — {d.description[:80]}")
            lines.append(f"  ⚠️ {days} days overdue | {d.category}")
            if d.matter_name:
                lines.append(f"  📁 Matter: {d.matter_name}")
        lines.append("")
    
    if critical:
        lines.extend([
            "## 🔴 CRITICAL (≤3 days)",
            ""
        ])
        for d in critical:
            lines.append(f"- **{d.date}** ({d.days_until()} days) — {d.description[:80]}")
            lines.append(f"  {d.category}")
            if d.court:
                lines.append(f"  🏛️ {d.court}")
        lines.append("")
    
    if upcoming:
        lines.extend([
            "## 📋 Upcoming",
            ""
        ])
        for d in upcoming:
            emoji = urgency_emoji.get(d.urgency_level(), "⚪")
            lines.append(f"- {emoji} **{d.date}** ({d.days_until()} days)")
            lines.append(f"  {d.description[:80]}")
            lines.append(f"  Category: {d.category}")
            if d.matter_name:
                lines.append(f"  📁 {d.matter_name}")
        lines.append("")
    
    if not deadlines:
        lines.append("*No deadlines found for the specified criteria.*")
        lines.append("")
    
    lines.extend([
        "---",
        "",
        "*Managed by LegalDoc AI. Set up alerts to never miss a deadline.*"
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Track and manage legal deadlines"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List deadlines")
    list_parser.add_argument(
        "--upcoming", "-u",
        type=str,
        default="30d",
        help="Show deadlines within N days (e.g., 30d, 90d)"
    )
    list_parser.add_argument(
        "--matter", "-m",
        help="Filter by matter ID"
    )
    list_parser.add_argument(
        "--overdue",
        action="store_true",
        help="Show only overdue deadlines"
    )
    list_parser.add_argument(
        "--output", "-o",
        choices=["markdown", "json"],
        default="markdown"
    )
    
    # Add command
    add_parser = subparsers.add_parser("add", help="Add a deadline")
    add_parser.add_argument("description", help="Deadline description")
    add_parser.add_argument("--date", "-d", required=True, help="Deadline date (YYYY-MM-DD)")
    add_parser.add_argument("--category", "-c", default="deadline", help="Category")
    add_parser.add_argument("--matter", "-m", help="Matter ID")
    add_parser.add_argument("--matter-name", help="Matter name")
    add_parser.add_argument("--court", help="Court name")
    add_parser.add_argument("--notes", "-n", help="Additional notes")
    
    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Extract deadlines from document")
    extract_parser.add_argument("file_path", help="Path to document")
    extract_parser.add_argument("--save", "-s", action="store_true", help="Save extracted deadlines")
    extract_parser.add_argument("--output", "-o", choices=["markdown", "json"], default="markdown")
    
    # SOL command
    sol_parser = subparsers.add_parser("sol", help="Calculate statute of limitations")
    sol_parser.add_argument("incident_date", help="Incident date (YYYY-MM-DD)")
    sol_parser.add_argument("claim_type", help="Type of claim")
    sol_parser.add_argument("--save", "-s", action="store_true", help="Save to tracker")
    
    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark deadline complete")
    complete_parser.add_argument("deadline_id", help="Deadline ID")
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a deadline")
    delete_parser.add_argument("deadline_id", help="Deadline ID")
    
    # Categories command
    subparsers.add_parser("categories", help="List deadline categories")
    
    # SOL types command
    subparsers.add_parser("sol-types", help="List statute of limitations types")
    
    args = parser.parse_args()
    
    db = DeadlineDatabase()
    
    if args.command == "list":
        # Parse days
        days_match = re.match(r"(\d+)d?", args.upcoming)
        days = int(days_match.group(1)) if days_match else 30
        
        if args.overdue:
            deadlines = db.list_overdue()
        elif args.matter:
            deadlines = db.list_by_matter(args.matter)
        else:
            deadlines = db.list_upcoming(days)
        
        print(format_deadlines(deadlines, args.output))
    
    elif args.command == "add":
        deadline_id = hashlib.md5(
            f"{args.date}:{args.description[:50]}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
        
        deadline = Deadline(
            id=deadline_id,
            description=args.description,
            date=args.date,
            category=args.category,
            matter_id=args.matter,
            matter_name=args.matter_name,
            court=args.court,
            notes=args.notes
        )
        
        if db.add(deadline):
            print(f"✅ Deadline added: {deadline_id}")
            print(f"   Date: {args.date}")
            print(f"   Description: {args.description}")
        else:
            print("❌ Failed to add deadline (may already exist)")
            sys.exit(1)
    
    elif args.command == "extract":
        try:
            deadlines = extract_deadlines_from_document(args.file_path)
            
            if args.save:
                saved = 0
                for d in deadlines:
                    if db.add(d):
                        saved += 1
                print(f"✅ Saved {saved} of {len(deadlines)} deadlines", file=sys.stderr)
            
            print(format_deadlines(deadlines, args.output))
            
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == "sol":
        deadline = calculate_sol_deadline(args.incident_date, args.claim_type)
        
        if deadline:
            if args.save:
                db.add(deadline)
                print(f"✅ Saved SOL deadline", file=sys.stderr)
            
            print(f"📅 Statute of Limitations Deadline")
            print(f"   Claim Type: {args.claim_type}")
            print(f"   Incident Date: {args.incident_date}")
            print(f"   Deadline: {deadline.date}")
            print(f"   Days Remaining: {deadline.days_until()}")
            if deadline.notes:
                print(f"   Notes: {deadline.notes}")
        else:
            print(f"❌ Unknown claim type: {args.claim_type}")
            print("Run 'deadline_tracker.py sol-types' to see available types")
            sys.exit(1)
    
    elif args.command == "complete":
        if db.mark_complete(args.deadline_id):
            print(f"✅ Deadline {args.deadline_id} marked complete")
        else:
            print(f"❌ Deadline not found: {args.deadline_id}")
            sys.exit(1)
    
    elif args.command == "delete":
        if db.delete(args.deadline_id):
            print(f"✅ Deadline {args.deadline_id} deleted")
        else:
            print(f"❌ Deadline not found: {args.deadline_id}")
            sys.exit(1)
    
    elif args.command == "categories":
        print("📋 Deadline Categories:\n")
        for cat, info in DEADLINE_CATEGORIES.items():
            print(f"  {cat}")
            print(f"    {info['description']}")
            print(f"    Priority: {info['priority']}")
            print(f"    Default alerts: {info['default_alert_days']} days before")
            print()
    
    elif args.command == "sol-types":
        print("⏰ Statute of Limitations Types (California defaults):\n")
        for claim, info in STATUTE_OF_LIMITATIONS.items():
            period = f"{info.get('years', '')} years" if 'years' in info else f"{info.get('days', '')} days"
            print(f"  {claim.replace('_', ' ').title()}")
            print(f"    Period: {period}")
            print(f"    Statute: {info['statute']}")
            if 'notes' in info:
                print(f"    Notes: {info['notes']}")
            print()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
