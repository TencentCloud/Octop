#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Cluster Health Scorer
# ==============================================================================
# Purpose:  Implement the 100-point deduction model from
#           references/cluster-health-score.md, removing arithmetic from LLM.
#
# Usage (single node):
#   echo "instance_state=RUNNING load_ratio=0.85 mem_pct=78 disk_root_pct=55 \
#         sshd_active=true cpu_cloud_avg_pct=65 mem_cloud_avg_pct=70 \
#         tat_available=true node=ins-abc123 name=web-1" \
#     | bash scripts/cluster_score.sh
#
# Usage (multi-node, one KV line per node):
#   bash scripts/cluster_score.sh nodes.txt
#
# Output:  JSON array of node scores, plus cluster summary (MIN score wins)
#
# Field reference (all optional; unset fields are skipped gracefully):
#   instance_state     RUNNING | STOPPED | SHUTDOWN | TERMINATING | REBOOTING
#   load_ratio         float  (load / ncpu)
#   mem_pct            int    (0-100)
#   disk_root_pct      int    (0-100)
#   sshd_active        true | false
#   cpu_cloud_avg_pct  int    (0-100, from GetMonitorData)
#   mem_cloud_avg_pct  int    (0-100, from GetMonitorData)
#   tat_available      true | false  (default: true)
#   node               string (InstanceId)
#   name               string (InstanceName, optional)
# ==============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Parse a key=value string; print value for given key (empty if absent)
kv_get() {
  local key="$1"
  local line="$2"
  printf '%s' "$line" | grep -oE "(^| )${key}=[^ ]+" | head -1 | sed "s/.*${key}=//"
}

# Compare floats using awk (returns 0 if true, 1 if false)
float_gt() {
  awk "BEGIN {exit !($1 > $2)}"
}

# Score a single node KV line; prints one JSON object
score_node() {
  local line="$1"

  # Extract fields
  local node name instance_state load_ratio mem_pct disk_root_pct
  local sshd_active cpu_cloud mem_cloud tat_available

  node=$(            kv_get "node"                "$line")
  name=$(            kv_get "name"                "$line")
  instance_state=$(  kv_get "instance_state"      "$line")
  load_ratio=$(      kv_get "load_ratio"           "$line")
  mem_pct=$(         kv_get "mem_pct"              "$line")
  disk_root_pct=$(   kv_get "disk_root_pct"        "$line")
  sshd_active=$(     kv_get "sshd_active"          "$line")
  cpu_cloud=$(       kv_get "cpu_cloud_avg_pct"    "$line")
  mem_cloud=$(       kv_get "mem_cloud_avg_pct"    "$line")
  tat_available=$(   kv_get "tat_available"        "$line")

  # Defaults
  node="${node:-unknown}"
  name="${name:-$node}"
  instance_state="${instance_state:-RUNNING}"
  tat_available="${tat_available:-true}"
  sshd_active="${sshd_active:-true}"

  local score=100
  local deductions="[]"
  local grade="healthy"
  local notes=""

  # --------------------------------------------------------------------------
  # Layer 1: Instance state
  # --------------------------------------------------------------------------
  case "$instance_state" in
    STOPPED|SHUTDOWN|TERMINATING)
      # Instant 0
      cat <<EOF
{"node": "$node", "name": "$name", "score": 0, "grade": "critical", "instance_state": "$instance_state", "deductions": [{"reason": "instance_state=$instance_state", "points": -100}], "notes": "Instance unavailable", "raw_metrics": null}
EOF
      return
      ;;
    REBOOTING)
      cat <<EOF
{"node": "$node", "name": "$name", "score": null, "grade": "rebooting", "instance_state": "$instance_state", "deductions": [], "notes": "Instance rebooting — skipped this cycle", "raw_metrics": null}
EOF
      return
      ;;
    RUNNING) : ;;
    *)       : ;;   # Unknown state: continue with scoring
  esac

  # Accumulate deductions as a JSON array string
  local ded_list=""

  add_deduction() {
    local reason="$1"
    local pts="$2"   # negative number
    score=$(( score + pts ))
    [[ $score -lt 0 ]] && score=0
    if [[ -n "$ded_list" ]]; then
      ded_list+=","
    fi
    ded_list+="{\"reason\": \"$reason\", \"points\": $pts}"
  }

  # --------------------------------------------------------------------------
  # Layer 2B (OS metrics via TAT) — skip if tat_available=false
  # --------------------------------------------------------------------------
  if [[ "$tat_available" == "true" ]]; then

    # Load ratio
    if [[ -n "$load_ratio" ]]; then
      if float_gt "$load_ratio" "2.0"; then
        add_deduction "load_ratio=${load_ratio} > 2.0 (200%)" -25
      elif float_gt "$load_ratio" "1.5"; then
        add_deduction "load_ratio=${load_ratio} > 1.5 (150%)" -10
      elif float_gt "$load_ratio" "1.0"; then
        add_deduction "load_ratio=${load_ratio} > 1.0 (100%)" -5
      fi
    fi

    # Memory %
    if [[ -n "$mem_pct" ]]; then
      if (( mem_pct > 90 )); then
        add_deduction "mem_pct=${mem_pct}% > 90%" -20
      elif (( mem_pct > 75 )); then
        add_deduction "mem_pct=${mem_pct}% > 75%" -10
      elif (( mem_pct > 60 )); then
        add_deduction "mem_pct=${mem_pct}% > 60%" -5
      fi
    fi

    # Disk root %
    if [[ -n "$disk_root_pct" ]]; then
      if (( disk_root_pct > 90 )); then
        add_deduction "disk_root_pct=${disk_root_pct}% > 90%" -25
      elif (( disk_root_pct > 80 )); then
        add_deduction "disk_root_pct=${disk_root_pct}% > 80%" -10
      elif (( disk_root_pct > 70 )); then
        add_deduction "disk_root_pct=${disk_root_pct}% > 70%" -5
      fi
    fi

    # SSHD active
    if [[ "$sshd_active" == "false" ]]; then
      add_deduction "sshd_active=false" -40
    fi

  else
    notes="OS-layer deductions skipped (TAT unavailable); low confidence"
  fi

  # --------------------------------------------------------------------------
  # Layer 2A (Cloud metrics from GetMonitorData)
  # --------------------------------------------------------------------------

  # CPU cloud avg
  if [[ -n "$cpu_cloud" ]]; then
    if (( cpu_cloud > 85 )); then
      add_deduction "cpu_cloud_avg_pct=${cpu_cloud}% > 85%" -15
    elif (( cpu_cloud > 70 )); then
      add_deduction "cpu_cloud_avg_pct=${cpu_cloud}% > 70%" -5
    fi
  fi

  # Memory cloud avg
  if [[ -n "$mem_cloud" ]]; then
    if (( mem_cloud > 90 )); then
      add_deduction "mem_cloud_avg_pct=${mem_cloud}% > 90%" -15
    elif (( mem_cloud > 80 )); then
      add_deduction "mem_cloud_avg_pct=${mem_cloud}% > 80%" -5
    fi
  fi

  # --------------------------------------------------------------------------
  # Grade
  # --------------------------------------------------------------------------
  if   (( score >= 90 )); then grade="healthy"
  elif (( score >= 75 )); then grade="minor"
  elif (( score >= 60 )); then grade="attention"
  elif (( score >= 40 )); then grade="abnormal"
  else                         grade="critical"
  fi

  # Build deductions JSON array
  if [[ -n "$ded_list" ]]; then
    deductions="[$ded_list]"
  fi

  # Build raw_metrics object — include every field that was provided so the
  # dashboard can render heatmaps and per-metric trends without parsing reason strings.
  local raw_cpu="${cpu_cloud:-null}"
  local raw_mem="${mem_pct:-null}"
  local raw_mem_cloud="${mem_cloud:-null}"
  local raw_disk="${disk_root_pct:-null}"
  local raw_load="${load_ratio:-null}"
  # Wrap numeric strings in quotes only if they are non-null string values;
  # null stays as JSON null.
  [[ "$raw_cpu"       == "null" ]] || raw_cpu="$raw_cpu"
  [[ "$raw_mem"       == "null" ]] || raw_mem="$raw_mem"
  [[ "$raw_mem_cloud" == "null" ]] || raw_mem_cloud="$raw_mem_cloud"
  [[ "$raw_disk"      == "null" ]] || raw_disk="$raw_disk"
  [[ "$raw_load"      == "null" ]] || raw_load="$raw_load"

  cat <<EOF
{"node": "$node", "name": "$name", "score": $score, "grade": "$grade", "instance_state": "$instance_state", "deductions": $deductions, "notes": "$notes", "raw_metrics": {"cpu_cloud_avg_pct": $raw_cpu, "mem_pct": $raw_mem, "mem_cloud_avg_pct": $raw_mem_cloud, "disk_root_pct": $raw_disk, "load_ratio": $raw_load}}
EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

INPUT_FILE="${1:-}"
declare -a node_scores
declare -a node_score_vals

# Read node KV lines from file or stdin
mapfile -t lines < <(
  if [[ -n "$INPUT_FILE" && -f "$INPUT_FILE" ]]; then
    grep -v '^#' "$INPUT_FILE" | grep -v '^[[:space:]]*$'
  else
    cat
  fi
)

if [[ ${#lines[@]} -eq 0 ]]; then
  echo "Usage: echo \"node=ins-xxx instance_state=RUNNING load_ratio=0.8 ...\" | bash scripts/cluster_score.sh" >&2
  exit 1
fi

# Score each node
for line in "${lines[@]}"; do
  result=$(score_node "$line")
  node_scores+=("$result")
done

# Compute cluster score = MIN of all numeric scores
cluster_score=100
cluster_weakest=""
cluster_grade="healthy"

for result in "${node_scores[@]}"; do
  # Extract score value (may be null for rebooting nodes)
  s=$(printf '%s' "$result" | grep -oE '"score": [0-9]+' | head -1 | grep -oE '[0-9]+' || true)
  n=$(printf '%s' "$result" | grep -oE '"node": "[^"]*"' | head -1 | sed 's/"node": "//;s/"//')
  [[ -z "$s" ]] && continue
  if (( s < cluster_score )); then
    cluster_score=$s
    cluster_weakest="$n"
  fi
done

# Cluster grade
if   (( cluster_score >= 90 )); then cluster_grade="healthy"
elif (( cluster_score >= 75 )); then cluster_grade="minor"
elif (( cluster_score >= 60 )); then cluster_grade="attention"
elif (( cluster_score >= 40 )); then cluster_grade="abnormal"
else                                  cluster_grade="critical"
fi

# Emit output
printf '{\n'
printf '  "cluster_score": %d,\n' "$cluster_score"
printf '  "cluster_grade": "%s",\n' "$cluster_grade"
printf '  "weakest_node": "%s",\n' "${cluster_weakest:-none}"
printf '  "node_count": %d,\n' "${#node_scores[@]}"
printf '  "nodes": [\n'

total=${#node_scores[@]}
idx=0
for result in "${node_scores[@]}"; do
  idx=$(( idx + 1 ))
  if (( idx < total )); then
    printf '    %s,\n' "$result"
  else
    printf '    %s\n' "$result"
  fi
done

printf '  ]\n'
printf '}\n'
