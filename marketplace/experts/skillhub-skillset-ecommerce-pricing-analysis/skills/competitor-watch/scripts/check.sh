#!/bin/bash
# competitor-watch/scripts/check.sh — Run monitoring sweep

set -euo pipefail

# --- Config ---
CONFIG_DIR="${CW_CONFIG_DIR:-$HOME/.config/competitor-watch}"
CONFIG_FILE="$CONFIG_DIR/config.json"
DATA_DIR="$CONFIG_DIR/data"
SNAPSHOT_DIR="$DATA_DIR/snapshots"
LAST_CHECKS_FILE="$DATA_DIR/last-checks.json"
CHANGE_LOG_FILE="$DATA_DIR/change-log.json"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# --- Color Codes ---
C_INFO='\033[0;36m'
C_SUCCESS='\033[0;32m'
C_WARN='\033[0;33m'
C_ERROR='\033[0;31m'
C_RESET='\033[0m'

# --- Log Functions ---
log_info() { echo -e "${C_INFO}INFO: $1${C_RESET}"; }
log_success() { echo -e "${C_SUCCESS}SUCCESS: $1${C_RESET}"; }
log_warn() { echo -e "${C_WARN}WARN: $1${C_RESET}"; }
log_error() { echo -e "${C_ERROR}ERROR: $1${C_RESET}"; exit 1; }

# --- Argument Parsing ---
DRY_RUN=false
FORCE_CHECK=false
TARGET_TIER=""
TARGET_COMPETITOR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE_CHECK=true
            shift
            ;;
        --tier)
            TARGET_TIER="$2"
            shift 2
            ;;
        --competitor)
            TARGET_COMPETITOR="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            ;;
    esac
done

# --- Validation ---
if ! command -v jq &> /dev/null; then log_error "jq is not installed."; fi
if [ ! -f "$CONFIG_FILE" ]; then log_error "Config file not found. Run setup.sh first."; fi

# --- Main Logic ---
log_info "Starting competitor check sweep..."
[ "$DRY_RUN" = true ] && log_warn "Running in DRY-RUN mode. No files will be written."

# Load competitors and tiers from config
COMPETITORS=$(jq -c '.competitors[]' "$CONFIG_FILE")
TIERS=$(jq -c '.tiers' "$CONFIG_FILE")

# Loop through each competitor
echo "$COMPETITORS" | while IFS= read -r competitor_json; do
    comp_id=$(echo "$competitor_json" | jq -r '.id')
    comp_name=$(echo "$competitor_json" | jq -r '.name')
    comp_tier=$(echo "$competitor_json" | jq -r '.tier')
    comp_pages=$(echo "$competitor_json" | jq -c '.pages')

    # --- Filtering ---
    if [ -n "$TARGET_TIER" ] && [ "$comp_tier" != "$TARGET_TIER" ]; then continue; fi
    if [ -n "$TARGET_COMPETITOR" ] && [[ "$comp_id" != "$TARGET_COMPETITOR" && "$comp_name" != "$TARGET_COMPETITOR" ]]; then continue; fi

    log_info "Processing: $comp_name (Tier: $comp_tier)"
    tier_config=$(echo "$TIERS" | jq -c ".\"$comp_tier\"")
    check_interval=$(echo "$tier_config" | jq -r '.check_interval_minutes')

    # Loop through each page for the competitor
    echo "$comp_pages" | jq -c 'to_entries[]' | while IFS= read -r page_entry; do
        page_name=$(echo "$page_entry" | jq -r '.key')
        page_url=$(echo "$page_entry" | jq -r '.value')
        check_key="${comp_id}.${page_name}"

        # --- Check Schedule ---
        last_check_timestamp=$(jq -r ".\"$check_key\" // 0" "$LAST_CHECKS_FILE")
        current_timestamp=$(date +%s)
        minutes_since_last_check=$(( (current_timestamp - last_check_timestamp) / 60 ))

        if [ "$FORCE_CHECK" = false ] && [ "$minutes_since_last_check" -lt "$check_interval" ]; then
            echo "  - Skipping '$page_name' (checked $minutes_since_last_check mins ago, interval is $check_interval)"
            continue
        fi

        echo "  - Checking '$page_name' ($page_url)"

        # --- Fetch Content (Simulated with clawd) ---
        # In a real scenario, this would be `clawd web_fetch ...`
        # For this script, we'll use a placeholder.
        fetch_command="clawd web_fetch --url \"$page_url\" --extractMode text"
        echo "    - Running: $fetch_command"

        if [ "$DRY_RUN" = true ]; then
            new_content="DRY RUN CONTENT for $page_url at $(date)"
        else
            # SIMULATED: In a real environment, you'd capture the output of the clawd tool call
            # For now, let's just create some sample content.
            # new_content=$(clawd web_fetch --url "$page_url" --extractMode text)
            new_content="Real content for $page_url at $(date)\n$(head -c 100 /dev/urandom | base64)"
        fi
        
        # --- Manage Snapshots ---
        comp_snapshot_dir="$SNAPSHOT_DIR/$comp_id/$page_name"
        mkdir -p "$comp_snapshot_dir"

        timestamp=$(date +"%Y-%m-%d-%H%M%S")
        new_snapshot_file="$comp_snapshot_dir/$timestamp.txt"
        
        echo "    - Saving snapshot to $new_snapshot_file"
        if [ "$DRY_RUN" = false ]; then
            echo "$new_content" > "$new_snapshot_file"
        fi

        # Find previous snapshot
        previous_snapshot_file=$(ls -1 "$comp_snapshot_dir" | grep -v "$timestamp" | sort -r | head -n 1)

        if [ -z "$previous_snapshot_file" ]; then
            log_warn "    - No previous snapshot found. This is the first check."
        else
            log_info "    - Comparing with previous snapshot: $previous_snapshot_file"
            # --- Call Diff Script ---
            diff_output=$("$SKILL_DIR/scripts/diff.sh" "$comp_snapshot_dir/$previous_snapshot_file" "$new_snapshot_file")
            diff_exit_code=$?
            
            if [ "$diff_exit_code" -eq 1 ]; then
                log_success "    - SIGNIFICANT CHANGE DETECTED!"
                change_id=$(uuidgen)
                
                # Log the change
                if [ "$DRY_RUN" = false ]; then
                    change_data=$(echo "$diff_output" | jq --arg id "$change_id" --arg comp "$comp_id" --arg page "$page_name" '. + {id: $id, competitor: $comp, page: $page, timestamp: now | todate}')
                    jq --argjson data "$change_data" '.[$data.id] = $data' "$CHANGE_LOG_FILE" > tmp.json && mv tmp.json "$CHANGE_LOG_FILE"

                    # --- Call Report Script ---
                    log_info "    - Generating alert..."
                    "$SKILL_DIR/scripts/report.sh" --alert "$change_id"
                else
                    echo "    - DRY RUN: Would log change and generate alert."
                    echo "    - Diff output: $diff_output"
                fi
            else
                log_info "    - No significant changes found."
            fi
        fi

        # Update last check time
        if [ "$DRY_RUN" = false ]; then
            jq --arg key "$check_key" --arg time "$current_timestamp" '.[$key] = ($time | tonumber)' "$LAST_CHECKS_FILE" > tmp.json && mv tmp.json "$LAST_CHECKS_FILE"
        fi
        echo ""

    done
done

log_info "Sweep complete."
