#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# wireframe/scripts/script.sh — Generate wireframes, components, and flows
# Version: 3.0.0 | Author: BytesAgain
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Helpers ────────────────────────────────────────────────────────────────

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "▸ $*"; }

write_file() {
  local path="$1"
  shift
  local dir
  dir="$(dirname "$path")"
  mkdir -p "$dir"
  cat > "$path"
  info "Written: $path"
}

svg_header() {
  local w="${1:-800}" h="${2:-600}"
  echo "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"${w}\" height=\"${h}\" viewBox=\"0 0 ${w} ${h}\">"
  echo "  <style>"
  echo "    rect, line { stroke: #999; stroke-width: 1; fill: #f5f5f5; }"
  echo "    text { font-family: sans-serif; font-size: 12px; fill: #666; }"
  echo "    .label { font-size: 14px; font-weight: bold; fill: #333; }"
  echo "    .wireframe-line { stroke: #ccc; stroke-dasharray: 4,4; }"
  echo "  </style>"
}

svg_footer() {
  echo "</svg>"
}

svg_box() {
  local x="$1" y="$2" w="$3" h="$4" label="${5:-}" fill="${6:-#f5f5f5}"
  echo "  <rect x=\"${x}\" y=\"${y}\" width=\"${w}\" height=\"${h}\" rx=\"4\" fill=\"${fill}\" />"
  if [[ -n "$label" ]]; then
    local tx=$(( x + w/2 ))
    local ty=$(( y + h/2 + 4 ))
    echo "  <text x=\"${tx}\" y=\"${ty}\" text-anchor=\"middle\" class=\"label\">${label}</text>"
  fi
}

svg_line_h() {
  local x1="$1" y1="$2" x2="$3"
  echo "  <line x1=\"${x1}\" y1=\"${y1}\" x2=\"${x2}\" y2=\"${y1}\" class=\"wireframe-line\" />"
}

# ─── ASCII wireframe sections ──────────────────────────────────────────────

ascii_section() {
  local name="$1" width="${2:-60}"
  local border
  border=$(printf '%0.s─' $(seq 1 "$width"))
  echo "┌${border}┐"
  local pad=$(( (width - ${#name}) / 2 ))
  local left_pad right_pad
  left_pad=$(printf '%*s' "$pad" '')
  right_pad=$(printf '%*s' $(( width - pad - ${#name} )) '')
  echo "│${left_pad}${name}${right_pad}│"
  echo "└${border}┘"
}

ascii_placeholder() {
  local name="$1" width="${2:-60}" height="${3:-3}"
  local border
  border=$(printf '%0.s─' $(seq 1 "$width"))
  echo "┌${border}┐"
  local pad=$(( (width - ${#name}) / 2 ))
  local left_pad right_pad
  left_pad=$(printf '%*s' "$pad" '')
  right_pad=$(printf '%*s' $(( width - pad - ${#name} )) '')
  echo "│${left_pad}${name}${right_pad}│"
  for _ in $(seq 2 "$height"); do
    local empty
    empty=$(printf '%*s' "$width" '')
    echo "│${empty}│"
  done
  echo "└${border}┘"
}

# ─── Commands ───────────────────────────────────────────────────────────────

cmd_help() {
  cat <<'EOF'
wireframe — Generate wireframes, component sketches, and user flows

Commands:
  page       Generate full-page wireframe (ASCII or SVG)
  component  Generate single component wireframe
  flow       Generate user flow diagram
  annotate   Add annotations to SVG wireframe
  export     Export wireframe to HTML
  template   Generate wireframe from built-in template

Run: bash scripts/script.sh <command> [options]
EOF
}

cmd_page() {
  local sections_str="header,main,footer" format="ascii" output="" width=800 height=600
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --sections) sections_str="$2"; shift 2 ;;
      --format)   format="$2";       shift 2 ;;
      --output)   output="$2";       shift 2 ;;
      --width)    width="$2";        shift 2 ;;
      --height)   height="$2";       shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  IFS=',' read -ra sections <<< "$sections_str"
  local section_count=${#sections[@]}

  if [[ "$format" == "ascii" ]]; then
    local ascii_width=60
    local result=""
    result+="$(printf '%60s' '' | tr ' ' '=')"$'\n'
    result+="  PAGE WIREFRAME"$'\n'
    result+="$(printf '%60s' '' | tr ' ' '=')"$'\n'
    result+=$'\n'
    for section in "${sections[@]}"; do
      section="$(echo "$section" | tr '[:lower:]' '[:upper:]' | xargs)"
      result+="$(ascii_placeholder "$section" "$ascii_width" 4)"$'\n'
      result+=$'\n'
    done

    if [[ -n "$output" ]]; then
      echo "$result" | write_file "$output"
    else
      echo "$result"
    fi

  elif [[ "$format" == "svg" ]]; then
    local margin=20
    local usable_w=$(( width - 2 * margin ))
    local section_gap=10
    local total_gap=$(( (section_count - 1) * section_gap ))
    local section_h=$(( (height - 2 * margin - total_gap) / section_count ))

    local svg_content=""
    svg_content+="$(svg_header "$width" "$height")"$'\n'
    svg_content+="  <rect x=\"0\" y=\"0\" width=\"${width}\" height=\"${height}\" fill=\"#ffffff\" stroke=\"none\" />"$'\n'

    local y_pos=$margin
    for section in "${sections[@]}"; do
      section="$(echo "$section" | xargs)"
      svg_content+="$(svg_box "$margin" "$y_pos" "$usable_w" "$section_h" "$section" "#f0f0f0")"$'\n'
      y_pos=$(( y_pos + section_h + section_gap ))
    done

    svg_content+="$(svg_footer)"$'\n'

    if [[ -n "$output" ]]; then
      echo "$svg_content" | write_file "$output"
    else
      echo "$svg_content"
    fi
  else
    die "Unknown format: $format (ascii|svg)"
  fi
}

cmd_component() {
  local type="card" fields_str="" output="" width=300 height=200
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --type)   type="$2";       shift 2 ;;
      --fields) fields_str="$2"; shift 2 ;;
      --output) output="$2";     shift 2 ;;
      --width)  width="$2";      shift 2 ;;
      --height) height="$2";     shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  # Default fields per component type
  if [[ -z "$fields_str" ]]; then
    case "$type" in
      card)   fields_str="image,title,text,button" ;;
      form)   fields_str="label,input,label,input,submit" ;;
      nav)    fields_str="logo,link,link,link,button" ;;
      table)  fields_str="header,row,row,row,pagination" ;;
      modal)  fields_str="title,body,actions" ;;
      *)      fields_str="header,content,footer" ;;
    esac
  fi

  IFS=',' read -ra fields <<< "$fields_str"
  local field_count=${#fields[@]}
  local margin=10
  local usable_w=$(( width - 2 * margin ))
  local field_gap=5
  local total_gap=$(( (field_count - 1) * field_gap ))
  local field_h=$(( (height - 2 * margin - total_gap) / field_count ))
  [[ $field_h -lt 10 ]] && field_h=10

  # Recalculate height to fit
  local needed_h=$(( field_count * (field_h + field_gap) - field_gap + 2 * margin ))
  [[ $needed_h -gt $height ]] && height=$needed_h

  local svg=""
  svg+="$(svg_header "$width" "$height")"$'\n'
  svg+="  <rect x=\"0\" y=\"0\" width=\"${width}\" height=\"${height}\" rx=\"8\" fill=\"#ffffff\" stroke=\"#ddd\" stroke-width=\"2\" />"$'\n'

  local y_pos=$margin
  for field in "${fields[@]}"; do
    field="$(echo "$field" | xargs)"
    local fill="#f5f5f5"
    case "$field" in
      image)  fill="#e0e0e0" ;;
      button|submit|actions) fill="#e8e8ff" ;;
      input)  fill="#ffffff" ;;
    esac
    svg+="$(svg_box "$margin" "$y_pos" "$usable_w" "$field_h" "$field" "$fill")"$'\n'
    y_pos=$(( y_pos + field_h + field_gap ))
  done

  svg+="$(svg_footer)"$'\n'

  if [[ -n "$output" ]]; then
    echo "$svg" | write_file "$output"
  else
    echo "$svg"
  fi
}

cmd_flow() {
  local steps_str="" decisions_str="" output="" width=800
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --steps)     steps_str="$2";     shift 2 ;;
      --decisions) decisions_str="$2"; shift 2 ;;
      --output)    output="$2";        shift 2 ;;
      --width)     width="$2";         shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done
  [[ -n "$steps_str" ]] || die "Missing --steps"

  IFS=',' read -ra steps <<< "$steps_str"
  local step_count=${#steps[@]}

  # Parse decisions: "key:yes/no" format
  declare -A decision_map
  if [[ -n "$decisions_str" ]]; then
    IFS=',' read -ra dec_pairs <<< "$decisions_str"
    for dp in "${dec_pairs[@]}"; do
      IFS=':' read -r dkey dvals <<< "$dp"
      decision_map["$dkey"]="$dvals"
    done
  fi

  local box_w=140 box_h=50 gap_y=30
  local margin=40
  local center_x=$(( width / 2 ))
  local total_h=$(( margin + step_count * (box_h + gap_y) + margin ))

  local svg=""
  svg+="$(svg_header "$width" "$total_h")"$'\n'
  svg+="  <defs><marker id=\"arrow\" markerWidth=\"10\" markerHeight=\"7\" refX=\"10\" refY=\"3.5\" orient=\"auto\"><polygon points=\"0 0, 10 3.5, 0 7\" fill=\"#999\"/></marker></defs>"$'\n'

  local y=$margin
  local prev_y=""
  for i in "${!steps[@]}"; do
    local step
    step="$(echo "${steps[$i]}" | xargs)"
    local bx=$(( center_x - box_w / 2 ))

    # Check if this is a decision node
    if [[ -v "decision_map[$step]" ]]; then
      # Diamond shape for decisions
      local cx=$center_x cy=$(( y + box_h / 2 ))
      local dw=$(( box_w / 2 )) dh=$(( box_h / 2 ))
      svg+="  <polygon points=\"${cx},$y $((cx+dw)),$cy ${cx},$((y+box_h)) $((cx-dw)),$cy\" fill=\"#fff8e1\" stroke=\"#999\" />"$'\n'
      svg+="  <text x=\"${cx}\" y=\"$((cy+4))\" text-anchor=\"middle\" class=\"label\">${step}?</text>"$'\n'
      # Decision labels
      local vals="${decision_map[$step]}"
      IFS='/' read -ra opts <<< "$vals"
      svg+="  <text x=\"$((cx+dw+10))\" y=\"$((cy+4))\" font-size=\"11\" fill=\"#4caf50\">${opts[0]:-yes}</text>"$'\n'
      if [[ ${#opts[@]} -gt 1 ]]; then
        svg+="  <text x=\"$((cx-dw-30))\" y=\"$((cy+4))\" font-size=\"11\" fill=\"#f44336\">${opts[1]:-no}</text>"$'\n'
      fi
    else
      # Regular box
      svg+="$(svg_box "$bx" "$y" "$box_w" "$box_h" "$step" "#ffffff")"$'\n'
    fi

    # Arrow from previous
    if [[ -n "$prev_y" ]]; then
      local arrow_y1=$prev_y
      local arrow_y2=$y
      svg+="  <line x1=\"${center_x}\" y1=\"${arrow_y1}\" x2=\"${center_x}\" y2=\"${arrow_y2}\" stroke=\"#999\" stroke-width=\"1.5\" marker-end=\"url(#arrow)\" />"$'\n'
    fi

    prev_y=$(( y + box_h ))
    y=$(( y + box_h + gap_y ))
  done

  svg+="$(svg_footer)"$'\n'

  if [[ -n "$output" ]]; then
    echo "$svg" | write_file "$output"
  else
    echo "$svg"
  fi
}

cmd_annotate() {
  local input="" notes_str="" output=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --input)  input="$2";     shift 2 ;;
      --notes)  notes_str="$2"; shift 2 ;;
      --output) output="$2";    shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done
  [[ -n "$input" ]]     || die "Missing --input SVG file"
  [[ -f "$input" ]]     || die "File not found: $input"
  [[ -n "$notes_str" ]] || die "Missing --notes (format: 1:Label,2:Label)"

  IFS=',' read -ra notes <<< "$notes_str"
  local note_count=${#notes[@]}

  # Read input SVG, inject annotations before closing </svg>
  local svg_content
  svg_content="$(cat "$input")"

  local annotation_block=""
  annotation_block+="  <!-- Annotations -->"$'\n'
  annotation_block+="  <style>.annotation-circle { fill: #ff5252; } .annotation-text { font-size: 10px; fill: white; font-weight: bold; } .annotation-label { font-size: 11px; fill: #333; }</style>"$'\n'

  # Place annotations along the right margin
  local ann_x=30 ann_y=30
  for note in "${notes[@]}"; do
    IFS=':' read -r num label <<< "$note"
    num="$(echo "$num" | xargs)"
    label="$(echo "$label" | xargs)"
    # Marker circle
    annotation_block+="  <circle cx=\"${ann_x}\" cy=\"${ann_y}\" r=\"10\" class=\"annotation-circle\" />"$'\n'
    annotation_block+="  <text x=\"${ann_x}\" y=\"$((ann_y+4))\" text-anchor=\"middle\" class=\"annotation-text\">${num}</text>"$'\n'
    annotation_block+="  <text x=\"$((ann_x+18))\" y=\"$((ann_y+4))\" class=\"annotation-label\">${label}</text>"$'\n'
    ann_y=$(( ann_y + 30 ))
  done

  # Legend at bottom
  annotation_block+="  <!-- Legend -->"$'\n'
  local legend_y=$ann_y
  annotation_block+="  <text x=\"20\" y=\"$((legend_y+10))\" font-size=\"13\" font-weight=\"bold\" fill=\"#333\">Annotations:</text>"$'\n'
  legend_y=$(( legend_y + 25 ))
  for note in "${notes[@]}"; do
    IFS=':' read -r num label <<< "$note"
    num="$(echo "$num" | xargs)"
    label="$(echo "$label" | xargs)"
    annotation_block+="  <text x=\"30\" y=\"${legend_y}\" font-size=\"11\" fill=\"#555\">${num}. ${label}</text>"$'\n'
    legend_y=$(( legend_y + 18 ))
  done

  # Inject before </svg>
  local result
  result="${svg_content//<\/svg>/${annotation_block}<\/svg>}"

  output="${output:-$input}"
  echo "$result" > "$output"
  info "Annotated: $output ($note_count notes)"
}

cmd_export() {
  local input="" format="html" output="" title="Wireframe"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --input)  input="$2";  shift 2 ;;
      --format) format="$2"; shift 2 ;;
      --output) output="$2"; shift 2 ;;
      --title)  title="$2";  shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done
  [[ -n "$input" ]] || die "Missing --input"
  [[ -f "$input" ]] || die "File not found: $input"

  case "$format" in
    html)
      local svg_content
      svg_content="$(cat "$input")"
      local html
      html=$(cat <<HTMLDOC
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  <style>
    body {
      margin: 0;
      padding: 40px;
      background: #fafafa;
      display: flex;
      justify-content: center;
      font-family: sans-serif;
    }
    .wireframe-container {
      background: white;
      padding: 20px;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    h1 {
      text-align: center;
      color: #333;
      margin-bottom: 20px;
    }
  </style>
</head>
<body>
  <div class="wireframe-container">
    <h1>${title}</h1>
    ${svg_content}
  </div>
</body>
</html>
HTMLDOC
      )
      output="${output:-wireframe.html}"
      echo "$html" | write_file "$output"
      ;;
    svg)
      output="${output:-$(basename "$input")}"
      cp "$input" "$output"
      info "Copied: $output"
      ;;
    *)
      die "Unknown export format: $format (html|svg)"
      ;;
  esac
}

cmd_template() {
  local name="landing" format="ascii" output=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --name)   name="$2";   shift 2 ;;
      --format) format="$2"; shift 2 ;;
      --output) output="$2"; shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  local sections=""
  case "$name" in
    landing)
      sections="header,hero,features,testimonials,cta,footer" ;;
    dashboard)
      sections="topbar,sidebar,stats-row,main-chart,data-table,footer" ;;
    blog)
      sections="header,featured-post,post-grid,sidebar,pagination,footer" ;;
    ecommerce)
      sections="header,search-bar,categories,product-grid,pagination,footer" ;;
    login)
      sections="header,logo,login-form,social-login,footer" ;;
    profile)
      sections="header,avatar,user-info,activity,settings,footer" ;;
    *)
      die "Unknown template: $name (landing|dashboard|blog|ecommerce|login|profile)"
      ;;
  esac

  # Delegate to cmd_page
  local args=(--sections "$sections" --format "$format")
  [[ -n "$output" ]] && args+=(--output "$output")
  cmd_page "${args[@]}"
}

# ─── Main dispatcher ───────────────────────────────────────────────────────

main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    page)      cmd_page "$@" ;;
    component) cmd_component "$@" ;;
    flow)      cmd_flow "$@" ;;
    annotate)  cmd_annotate "$@" ;;
    export)    cmd_export "$@" ;;
    template)  cmd_template "$@" ;;
    help|--help|-h) cmd_help ;;
    *) die "Unknown command: $cmd. Run with 'help' for usage." ;;
  esac
}

main "$@"
