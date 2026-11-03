#!/bin/bash
# competitor-watch/scripts/report.sh — Format and send change reports

set -euo pipefail

# --- Config ---
CONFIG_DIR="${CW_CONFIG_DIR:-$HOME/.config/competitor-watch}"
CONFIG_FILE="$CONFIG_DIR/config.json"
CHANGE_LOG_FILE="$CONFIG_DIR/data/change-log.json"

# --- Argument Parsing ---
MODE=""
ARG=""

case "$1" in
    --alert)
        MODE="alert"
        ARG="$2"
        ;;
    --daily-digest)
        MODE="digest"
        ;;
    --list)
        MODE="list"
        ;;
    *)
        echo "Usage: $0 [MODE]"
        echo "Modes:"
        echo "  --alert <change_id>   Send a real-time alert for a specific change."
        echo "  --daily-digest        Generate and send a digest of recent changes."
        echo "  --list                List recent changes from the log."
        exit 1
        ;;
esac

# --- Validation ---
if ! command -v jq &> /dev/null; then echo "jq not installed"; exit 1; fi
if [ ! -f "$CHANGE_LOG_FILE" ]; then echo "Change log not found."; exit 1; fi

# --- Functions ---

format_alert() {
    local change_id="$1"
    local change_json=$(jq -r ".\"$change_id\"" "$CHANGE_LOG_FILE")
    
    if [ "$change_json" == "null" ]; then
        echo "Error: Change with ID $change_id not found."
        return 1
    fi

    local comp_id=$(echo "$change_json" | jq -r '.competitor')
    local page_name=$(echo "$change_json" | jq -r '.page')
    local comp_name=$(jq -r --arg id "$comp_id" '.competitors[] | select(.id == $id) | .name' "$CONFIG_FILE")
    local comp_tier=$(jq -r --arg id "$comp_id" '.competitors[] | select(.id == $id) | .tier' "$CONFIG_FILE")
    local added=$(echo "$change_json" | jq -r '.summary.added')
    local removed=$(echo "$change_json" | jq -r '.summary.removed')
    local score=$(echo "$change_json" | jq -r '.score')
    
    local report=""
    report+="🚨 COMPETITOR CHANGE: $comp_name ($comp_tier)\n"
    report+="========================================\n"
    report+="Page: $page_name\n"
    report+="Detected: $(echo "$change_json" | jq -r '.timestamp')\n"
    report+="Significance Score: $score\n\n"

    if [ -n "$added" ]; then
        report+="What's New:\n$added\n\n"
    fi
    if [ -n "$removed" ]; then
        report+="What's Removed:\n$removed\n\n"
    fi
    
    report+="---\n"
    report+="Raw diff available in change log."

    echo -e "$report"
}

send_alert() {
    local formatted_report="$1"
    local alert_channel=$(jq -r '.alerts.channel' "$CONFIG_FILE")

    # This is a simulation of sending a message via the clawd tool
    echo "--- Sending Alert via $alert_channel ---"
    # In a real environment:
    # clawd message send --channel "$alert_channel" --message "$formatted_report"
    echo "$formatted_report"
    echo "------------------------------------"
}

# --- Main Logic ---

case "$MODE" in
    "alert")
        if [ -z "$ARG" ]; then
            echo "Error: --alert requires a change_id."
            exit 1
        fi
        formatted_report=$(format_alert "$ARG")
        if [ $? -eq 0 ]; then
            send_alert "$formatted_report"
        fi
        ;;
    "digest")
        echo "Daily digest feature not yet implemented."
        # Future logic:
        # 1. Get all changes from the last 24 hours from CHANGE_LOG_FILE
        # 2. Group them by competitor
        # 3. Format a summary report
        # 4. Send the report
        ;;
    "list")
        echo "--- Recent Changes ---"
        jq -r 'to_entries[] | .value | "\(.timestamp) | \(.competitor) (\(.page)) | Score: \(.score)"' "$CHANGE_LOG_FILE" | sort -r | head -n 20
        ;;
esac

exit 0
