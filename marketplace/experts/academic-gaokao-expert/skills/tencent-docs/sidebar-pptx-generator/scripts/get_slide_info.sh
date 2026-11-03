#!/bin/bash
#
# Inspect a Tencent Docs PPT and return compact JSON for LLM routing.
#
# Usage:
#   bash scripts/get_slide_info.sh <file_url_or_id> [--file-id]
#
# Output:
#   {"action":"write_design_md"|"proceed_next","reason":"...",...}
#

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "ERROR:missing_argument"
    exit 1
fi

INPUT="$1"
FILE_KEY="file_url"
[[ "${2:-}" == "--file-id" ]] && FILE_KEY="file_id"

BASE_ARGS=$(jq -n --arg key "$FILE_KEY" --arg val "$INPUT" '{($key): $val}')

INFO_RESULT=$(mcporter call "slide-mcp" "slide_get_info" --args "$BASE_ARGS" 2>&1) || {
    echo "ERROR:slide_get_info_failed"
    exit 1
}

SLIDE_COUNT=$(echo "$INFO_RESULT" | jq -r '.slide_count // 0')
W_PT=$(echo "$INFO_RESULT" | jq -r '.w_pt // 0')
H_PT=$(echo "$INFO_RESULT" | jq -r '.h_pt // 0')

# ── Permission check ──
# When slide_count=0 but dimensions are valid, it likely means we lack
# VIEW permission rather than the document being truly empty.
# Attempt to verify via tencent-docs check_access.
if [[ "$SLIDE_COUNT" -eq 0 ]] && [[ "$W_PT" -gt 0 ]] && [[ "$H_PT" -gt 0 ]]; then
    # Try to extract file_id from URL (last path segment)
    FILE_ID=""
    if [[ "$FILE_KEY" == "file_url" ]]; then
        FILE_ID=$(echo "$INPUT" | sed -E 's|.*/([^/?#]+).*|\1|')
    else
        FILE_ID="$INPUT"
    fi

    if [[ -n "$FILE_ID" ]]; then
        ACCESS_RESULT=$(mcporter call "tencent-docs" "check_access" --args "{\"file_id\":\"$FILE_ID\",\"actions\":[\"VIEW\"]}" 2>&1 || echo '{"granted_actions":[]}')
        HAS_VIEW=$(echo "$ACCESS_RESULT" | jq -r '(.granted_actions // []) | map(select(. == "VIEW")) | length > 0' 2>/dev/null || echo "false")

        if [[ "$HAS_VIEW" != "true" ]]; then
            jq -n --arg reason "permission_denied" --argjson sc "$SLIDE_COUNT" --argjson w "$W_PT" --argjson h "$H_PT" --arg fid "$FILE_ID" \
                '{action:"ask_user",reason:$reason,slide_count:$sc,w_pt:$w,h_pt:$h,file_id:$fid,hint:"当前账号无 VIEW 权限，请分享文档或下载到本地后重试"}'
            exit 0
        fi
    fi
fi

if [[ "$SLIDE_COUNT" -eq 0 ]] || [[ "$W_PT" -eq 0 ]] || [[ "$H_PT" -eq 0 ]]; then
    jq -n --arg reason "ppt_is_empty" --argjson sc "$SLIDE_COUNT" --argjson w "$W_PT" --argjson h "$H_PT" \
        '{action:"write_design_md",reason:$reason,slide_count:$sc,w_pt:$w,h_pt:$h}'
    exit 0
fi

CONTENT_PAGE_COUNT=0

for i in $(seq 0 $((SLIDE_COUNT - 1))); do
    PAGE_ARGS=$(echo "$BASE_ARGS" | jq --argjson idx "$i" '. + {page_index: $idx}')
    PAGE_RESULT=$(mcporter call "slide-mcp" "slide_get_page_info" --args "$PAGE_ARGS" 2>&1) || continue

    HAS_CONTENT=$(echo "$PAGE_RESULT" | jq '
        [.shapes // [] | .[] | select((.text // "") | gsub("[\\s\\r\\n]"; "") != "")] | length > 0
    ' 2>/dev/null || echo "false")

    [[ "$HAS_CONTENT" == "true" ]] && CONTENT_PAGE_COUNT=$((CONTENT_PAGE_COUNT + 1))
done

if [[ "$CONTENT_PAGE_COUNT" -eq 0 ]]; then
    jq -n --arg reason "ppt_content_is_empty" --argjson sc "$SLIDE_COUNT" --argjson w "$W_PT" --argjson h "$H_PT" --argjson cpc "$CONTENT_PAGE_COUNT" \
        '{action:"write_design_md",reason:$reason,slide_count:$sc,w_pt:$w,h_pt:$h,content_page_count:$cpc}'
    exit 0
fi

DESIGN_RESULT=$(mcporter call "slide-mcp" "slide_get_design" --args "$BASE_ARGS" 2>&1) || {
    echo "ERROR:slide_get_design_failed"
    exit 1
}

DESIGN_EXISTS=$(echo "$DESIGN_RESULT" | jq -r '.exists // false')
DESIGN_MD=$(echo "$DESIGN_RESULT" | jq -r '.design_md // ""')

if [[ "$DESIGN_EXISTS" == "false" ]] || [[ -z "$DESIGN_MD" ]] || [[ "$DESIGN_MD" == '""' ]]; then
    jq -n --arg reason "design_is_empty" --argjson sc "$SLIDE_COUNT" --argjson w "$W_PT" --argjson h "$H_PT" --argjson cpc "$CONTENT_PAGE_COUNT" --argjson de "$DESIGN_EXISTS" \
        '{action:"write_design_md",reason:$reason,slide_count:$sc,w_pt:$w,h_pt:$h,content_page_count:$cpc,design_exists:$de}'
    exit 0
fi

DESIGN_MD_LEN=${#DESIGN_MD}
UPDATED_AT=$(echo "$DESIGN_RESULT" | jq -r '.updated_at // "0"')

jq -n --argjson sc "$SLIDE_COUNT" --argjson w "$W_PT" --argjson h "$H_PT" --argjson cpc "$CONTENT_PAGE_COUNT" --argjson de "$DESIGN_EXISTS" --argjson dml "$DESIGN_MD_LEN" --arg ua "$UPDATED_AT" \
    '{action:"proceed_next",reason:"design_exists",slide_count:$sc,w_pt:$w,h_pt:$h,content_page_count:$cpc,design_exists:$de,design_md_length:$dml,updated_at:$ua}'
