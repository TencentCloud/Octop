#!/usr/bin/env python3
"""
LegalDoc AI - Main CLI Entry Point
Unified interface for legal document automation.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path


# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.resolve()

# Component scripts
SCRIPTS = {
    "extract": SCRIPT_DIR / "clause_extractor.py",
    "summarize": SCRIPT_DIR / "document_summarizer.py",
    "research": SCRIPT_DIR / "legal_research.py",
    "deadlines": SCRIPT_DIR / "deadline_tracker.py",
}


def print_banner():
    """Print the LegalDoc AI banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ⚖️  LegalDoc AI                                              ║
║   Legal Document Automation for Modern Law Firms              ║
║                                                               ║
║   Version 1.0.0 | © 2026 Manas AI                             ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def run_component(component: str, args: list) -> int:
    """Run a component script with arguments."""
    script_path = SCRIPTS.get(component)
    
    if not script_path or not script_path.exists():
        print(f"Error: Component '{component}' not found", file=sys.stderr)
        return 1
    
    cmd = [sys.executable, str(script_path)] + args
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="LegalDoc AI - Legal Document Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  legaldoc extract clauses contract.pdf
  legaldoc extract clauses contract.pdf --type indemnification,liability
  legaldoc summarize agreement.docx --type executive
  legaldoc research "breach of contract damages" --jurisdiction CA
  legaldoc deadlines list --upcoming 30d
  legaldoc deadlines extract court_order.pdf --save
  legaldoc deadlines sol 2024-01-15 personal_injury
  legaldoc compare draft.pdf final.pdf --type redline

For help on a specific command:
  legaldoc extract --help
  legaldoc summarize --help
  legaldoc research --help
  legaldoc deadlines --help
"""
    )
    
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version and exit"
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        choices=["extract", "summarize", "research", "deadlines", "compare", "help"],
        help="Command to run"
    )
    
    parser.add_argument(
        "subcommand",
        nargs="?",
        help="Subcommand (e.g., 'clauses' for extract)"
    )
    
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments for the command"
    )
    
    args = parser.parse_args()
    
    if args.version:
        print("LegalDoc AI v1.0.0")
        print("© 2026 Manas AI")
        return 0
    
    if not args.command or args.command == "help":
        print_banner()
        parser.print_help()
        print("\n📚 Quick Start:")
        print("  1. Extract clauses:  legaldoc extract clauses <file>")
        print("  2. Summarize doc:    legaldoc summarize <file>")
        print("  3. Research topic:   legaldoc research \"<query>\"")
        print("  4. Track deadlines:  legaldoc deadlines list")
        return 0
    
    # Handle extract command with subcommand
    if args.command == "extract":
        if args.subcommand == "clauses":
            return run_component("extract", args.args)
        else:
            # Treat subcommand as file path if no explicit subcommand
            all_args = [args.subcommand] + args.args if args.subcommand else args.args
            return run_component("extract", all_args)
    
    # Handle summarize command
    elif args.command == "summarize":
        all_args = [args.subcommand] + args.args if args.subcommand else args.args
        return run_component("summarize", all_args)
    
    # Handle research command
    elif args.command == "research":
        all_args = [args.subcommand] + args.args if args.subcommand else args.args
        return run_component("research", all_args)
    
    # Handle deadlines command
    elif args.command == "deadlines":
        all_args = [args.subcommand] + args.args if args.subcommand else args.args
        return run_component("deadlines", all_args)
    
    # Handle compare command (placeholder)
    elif args.command == "compare":
        print("Document comparison feature coming soon!")
        print("Usage: legaldoc compare <file1> <file2> --type redline|summary")
        return 0
    
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
