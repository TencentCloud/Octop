#!/usr/bin/env bash
# mental-health - Health and wellness tracker
set -euo pipefail
VERSION="2.0.0"
DATA_DIR="${MENTAL_HEALTH_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mental-health}"
DB="$DATA_DIR/data.log"
mkdir -p "$DATA_DIR"

show_help() {
    cat << EOF
mental-health v$VERSION

Health and wellness tracker

Usage: mental-health <command> [args]

Commands:
  log                  Log entry
  today                Today summary
  streak               Current streak
  stats                Statistics
  reminder             Set reminder
  tips                 Health tips
  goal                 Set goal
  history              View history
  export               Export data
  reset                Reset tracker
  help                 Show this help
  version              Show version

Data: \$DATA_DIR
EOF
}

_log() { echo "$(date '+%m-%d %H:%M') $1: $2" >> "$DATA_DIR/history.log"; }

cmd_log() {
    echo "$(date +%Y-%m-%d) $*" >> "$DB"; echo "  Logged: $*"
    _log "log" "${1:-}"
}

cmd_today() {
    grep "$(date +%Y-%m-%d)" "$DB" 2>/dev/null || echo "  No entries today"
    _log "today" "${1:-}"
}

cmd_streak() {
    echo "  Streak: check $DB for consecutive days"
    _log "streak" "${1:-}"
}

cmd_stats() {
    echo "  Total entries: $(wc -l < "$DB" 2>/dev/null || echo 0)"
    _log "stats" "${1:-}"
}

cmd_reminder() {
    echo "  Reminder: $1 at ${2:-8:00}"
    _log "reminder" "${1:-}"
}

cmd_tips() {
    echo "  1. Stay hydrated | 2. Move every hour | 3. Sleep 7-8h"
    _log "tips" "${1:-}"
}

cmd_goal() {
    echo "  Goal: $1 | Target: ${2:-daily}"
    _log "goal" "${1:-}"
}

cmd_history() {
    [ -f "$DB" ] && tail -14 "$DB" || echo "No history"
    _log "history" "${1:-}"
}

cmd_export() {
    [ -f "$DB" ] && cat "$DB" || echo "No data"
    _log "export" "${1:-}"
}

cmd_reset() {
    echo "  Use: reset --confirm to clear data"
    _log "reset" "${1:-}"
}

case "${1:-help}" in
    log) shift; cmd_log "$@" ;;
    today) shift; cmd_today "$@" ;;
    streak) shift; cmd_streak "$@" ;;
    stats) shift; cmd_stats "$@" ;;
    reminder) shift; cmd_reminder "$@" ;;
    tips) shift; cmd_tips "$@" ;;
    goal) shift; cmd_goal "$@" ;;
    history) shift; cmd_history "$@" ;;
    export) shift; cmd_export "$@" ;;
    reset) shift; cmd_reset "$@" ;;
    help|-h) show_help ;;
    version|-v) echo "mental-health v$VERSION" ;;
    *) echo "Unknown: $1"; show_help; exit 1 ;;
esac
