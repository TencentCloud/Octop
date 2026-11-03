#!/bin/bash
# competitor-watch/scripts/add-competitor.sh — Add a new competitor to the config

set -euo pipefail

CONFIG_DIR="${CW_CONFIG_DIR:-$HOME/.config/competitor-watch}"
CONFIG_FILE="$CONFIG_DIR/config.json"

# --- Help ---
show_help() {
cat << EOF
Usage: $0 [OPTIONS] "Competitor Name" "https://homepage.url"

Add a new competitor to the monitoring configuration.
Can be run interactively or with command-line flags.

Options:
  --tier <name>      Set competitor tier (e.g., fierce, important).
  --pages <p1,p2>    Comma-separated list of pages to track (e.g., pricing,blog).
  --tags <t1,t2>     Comma-separated list of tags.
  --twitter <handle> Twitter handle (without @).
  --linkedin <path>  LinkedIn company path.
  --notes "..."      Notes about the competitor.
  -h, --help         Show this help message.

Example:
  $0 "Acme Corp" https://acme.com --tier fierce --pages pricing,features
EOF
}

# --- Check Dependencies ---
if ! command -v jq &> /dev/null; then
    echo "Error: jq is not installed. Please install it to manage config. (e.g., 'brew install jq')"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file not found at $CONFIG_FILE"
    echo "Please run 'scripts/setup.sh' first."
    exit 1
fi

# --- Parse Arguments ---
NAME=""
HOMEPAGE=""
TIER=""
PAGES_STR=""
TAGS_STR=""
TWITTER=""
LINKEDIN=""
NOTES=""

# Use a while loop for robust argument parsing
if [ "$#" -eq 0 ]; then
    # Interactive mode if no arguments
    echo "Entering interactive mode..."
    read -p "Competitor Name: " NAME
    read -p "Homepage URL: " HOMEPAGE
    read -p "Tier (e.g., fierce, important, watching): " TIER
    read -p "Pages to track (comma-separated, e.g., pricing,blog): " PAGES_STR
    read -p "Tags (comma-separated): " TAGS_STR
    echo ""
else
    # Flag mode
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_help
                exit 0
                ;;
            --tier)
                TIER="$2"
                shift 2
                ;;
            --pages)
                PAGES_STR="$2"
                shift 2
                ;;
            --tags)
                TAGS_STR="$2"
                shift 2
                ;;
            --twitter)
                TWITTER="$2"
                shift 2
                ;;
            --linkedin)
                LINKEDIN="$2"
                shift 2
                ;;
            --notes)
                NOTES="$2"
                shift 2
                ;;
            -*)
                echo "Unknown option: $1"
                show_help
                exit 1
                ;;
            *)
                if [ -z "$NAME" ]; then
                    NAME="$1"
                elif [ -z "$HOMEPAGE" ]; then
                    HOMEPAGE="$1"
                else
                    echo "Unknown positional argument: $1"
                    show_help
                    exit 1
                fi
                shift
                ;;
        esac
    done
fi

# --- Validation ---
if [ -z "$NAME" ] || [ -z "$HOMEPAGE" ]; then
    echo "Error: Competitor Name and Homepage URL are required."
    show_help
    exit 1
fi

ID=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr -s '[:punct:][:space:]' '-' | sed 's/^-//;s/-$//')
echo "Generated Competitor ID: $ID"

# Check if ID already exists
if jq -e --arg id "$ID" '.competitors[] | select(.id == $id)' "$CONFIG_FILE" > /dev/null; then
    echo "Error: Competitor with ID '$ID' already exists. Choose a different name."
    exit 1
fi

# --- Build JSON Objects ---
PAGES_JSON="{}"
if [ -n "$PAGES_STR" ]; then
    PAGES_JSON=$(echo "$PAGES_STR" | tr ',' '\n' | awk -F ':' '{
        if (NF==1) { key=$1; value="/\"" key "\"" } else { key=$1; value=$2 }
        print "    \"" key "\": \"" value
    }' | sed 's|: "/|: "|' | paste -sd, - | sed 's/^/{ /;s/$/ }/')
    # A bit complex to handle simple names (pricing -> /pricing) and full URLs
    # For this script, we'll keep it simple and assume page names map to subpaths
    PAGES_JSON=$(echo "$PAGES_STR" | tr ',' '\n' | while read -r page; do
        echo "\"$page\": \"$HOMEPAGE/$page\""
    done | paste -sd, - | sed 's/^/{ /;s/$/ }/')
fi

SOCIAL_JSON="{}"
if [ -n "$TWITTER" ] || [ -n "$LINKEDIN" ]; then
    TWITTER_JSON=""
    [ -n "$TWITTER" ] && TWITTER_JSON="\"twitter\": \"$TWITTER\""
    LINKEDIN_JSON=""
    [ -n "$LINKEDIN" ] && LINKEDIN_JSON="\"linkedin\": \"$LINKEDIN\""

    SOCIAL_JSON=$(echo "$TWITTER_JSON $LINKEDIN_JSON" | sed 's/  */, /g;s/^, //;s/, $//;s/^/{ /;s/$/ }/')
fi

TAGS_JSON="[]"
if [ -n "$TAGS_STR" ]; then
    TAGS_JSON=$(echo "$TAGS_STR" | tr ',' '\n' | jq -R . | jq -s . | jq -c .)
fi

# --- Construct Final Competitor Object ---
NEW_COMPETITOR=$(jq -n \
    --arg id "$ID" \
    --arg name "$NAME" \
    --arg homepage "$HOMEPAGE" \
    --arg tier "$TIER" \
    --argjson pages "$PAGES_JSON" \
    --argjson social "$SOCIAL_JSON" \
    --argjson tags "$TAGS_JSON" \
    --arg notes "$NOTES" \
    '{
        id: $id,
        name: $name,
        homepage: $homepage,
        tier: $tier,
        tags: $tags,
        pages: $pages,
        social: $social,
        notes: $notes
    }')

# --- Update Config File ---
TMP_CONFIG=$(mktemp)
jq --argjson new_comp "$NEW_COMPETITOR" '.competitors += [$new_comp]' "$CONFIG_FILE" > "$TMP_CONFIG" && mv "$TMP_CONFIG" "$CONFIG_FILE"

echo ""
echo "✅ Successfully added '$NAME' to the configuration."
echo "Review the changes in: $CONFIG_FILE"
