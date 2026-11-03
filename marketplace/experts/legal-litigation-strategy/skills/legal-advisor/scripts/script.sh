#!/usr/bin/env bash
# legal-advisor - Legal document templates, contract review checklists, and compliance guides
set -euo pipefail
VERSION="2.0.0"
DATA_DIR="${LEGAL_ADVISOR_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/legal-advisor}"
mkdir -p "$DATA_DIR"

show_help() {
    cat << EOF
legal-advisor v$VERSION

Legal document templates, contract review checklists, and compliance guides

Usage: legal-advisor <command> [args]

Commands:
  nda                  Generate NDA template
  terms                Terms of service template
  privacy              Privacy policy template
  contract             Contract review checklist
  clause               Common legal clause library
  glossary             Legal terms glossary
  help                 Show this help
  version              Show version

EOF
}

_log() { echo "$(date '+%m-%d %H:%M') $1: $2" >> "$DATA_DIR/history.log"; }

cmd_nda() {
    local parties="${1:?Usage: legal-advisor nda <party1> <party2>}"
    local p2="${2:-Party B}"
    echo "  NON-DISCLOSURE AGREEMENT"
    echo "  Date: $(date +%Y-%m-%d)"
    echo "  Between: $parties (\"Discloser\")"
    echo "  And: $p2 (\"Recipient\")"
    echo ""
    echo "  1. CONFIDENTIAL INFORMATION"
    echo "  All non-public business, technical, financial information."
    echo ""
    echo "  2. OBLIGATIONS"
    echo "  Recipient shall not disclose, copy, or use for unauthorized purposes."
    echo ""
    echo "  3. TERM"
    echo "  This agreement is effective for [2] years from execution date."
    echo ""
    echo "  4. RETURN OF MATERIALS"
    echo "  Upon termination, Recipient shall return all materials."
    echo ""
    echo "  5. GOVERNING LAW"
    echo "  This agreement shall be governed by laws of [jurisdiction]."
}

cmd_terms() {
    echo "  TERMS OF SERVICE — ${1:-Your Company}"
    echo "  Last updated: $(date +%Y-%m-%d)"
    echo ""
    echo "  1. Acceptance of Terms"
    echo "  2. Description of Service"
    echo "  3. User Accounts"
    echo "  4. Acceptable Use Policy"
    echo "  5. Intellectual Property"
    echo "  6. Limitation of Liability"
    echo "  7. Termination"
    echo "  8. Governing Law"
    echo "  9. Changes to Terms"
    echo "  10. Contact Information"
}

cmd_privacy() {
    echo "  PRIVACY POLICY — ${1:-Your App}"
    echo "  Effective: $(date +%Y-%m-%d)"
    echo ""
    echo "  DATA WE COLLECT:"
    echo "  • Personal info (name, email)"
    echo "  • Usage data (pages visited, clicks)"
    echo "  • Device info (browser, OS, IP)"
    echo ""
    echo "  HOW WE USE IT:"
    echo "  • Provide and improve service"
    echo "  • Send important updates"
    echo "  • Never sell to third parties"
    echo ""
    echo "  YOUR RIGHTS:"
    echo "  • Access your data"
    echo "  • Request deletion"
    echo "  • Opt out of marketing"
}

cmd_contract() {
    echo "  CONTRACT REVIEW CHECKLIST"
    echo "  ════════════════════════"
    echo "  [ ] Parties correctly identified?"
    echo "  [ ] Scope of work clear?"
    echo "  [ ] Payment terms defined?"
    echo "  [ ] Delivery timeline specified?"
    echo "  [ ] Termination clauses fair?"
    echo "  [ ] Liability caps reasonable?"
    echo "  [ ] IP ownership stated?"
    echo "  [ ] Non-compete reasonable?"
    echo "  [ ] Dispute resolution method?"
    echo "  [ ] Governing law specified?"
    echo "  [ ] Signature blocks complete?"
}

cmd_clause() {
    local type="${1:-force-majeure}"
    case "$type" in
    force-majeure) echo "  FORCE MAJEURE: Neither party liable for delays caused by\n  events beyond reasonable control (natural disasters, war, pandemic)." ;;
    indemnity) echo "  INDEMNIFICATION: Party A agrees to indemnify and hold harmless\n  Party B from any claims arising from Party A's breach." ;;
    severability) echo "  SEVERABILITY: If any provision is found invalid, remaining\n  provisions shall continue in full force and effect." ;;
    assignment) echo "  ASSIGNMENT: Neither party may assign without prior written\n  consent. Any unauthorized assignment shall be void." ;;
    *) echo "  Types: force-majeure, indemnity, severability, assignment, confidentiality, termination" ;;
    esac
}

cmd_glossary() {
    echo "  LEGAL GLOSSARY"
    echo "  ─────────────"
    echo "  Indemnify    — Compensate for loss or damage"
    echo "  Liability    — Legal responsibility"
    echo "  Jurisdiction — Court authority area"
    echo "  Arbitration  — Dispute resolution outside court"
    echo "  Tort         — Civil wrong causing harm"
    echo "  Breach       — Violation of contract terms"
    echo "  Escrow       — Third-party held funds"
    echo "  Lien         — Claim on property as security"
}

case "${1:-help}" in
    nda) shift; cmd_nda "$@" ;;
    terms) shift; cmd_terms "$@" ;;
    privacy) shift; cmd_privacy "$@" ;;
    contract) shift; cmd_contract "$@" ;;
    clause) shift; cmd_clause "$@" ;;
    glossary) shift; cmd_glossary "$@" ;;
    help|-h) show_help ;;
    version|-v) echo "legal-advisor v$VERSION" ;;
    *) echo "Unknown: $1"; show_help; exit 1 ;;
esac
