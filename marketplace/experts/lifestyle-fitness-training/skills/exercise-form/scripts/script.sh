#!/usr/bin/env bash
set -euo pipefail

VERSION="3.0.0"
SCRIPT_NAME="exercise-form"
DATA_DIR="$HOME/.local/share/exercise-form"
mkdir -p "$DATA_DIR"

#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
# Powered by BytesAgain | bytesagain.com | hello@bytesagain.com

_info()  { echo "[INFO]  $*"; }
_error() { echo "[ERROR] $*" >&2; }
die()    { _error "$@"; exit 1; }

cmd_guide() {
    local exercise="${2:-}"
    [ -z "$exercise" ] && die "Usage: $SCRIPT_NAME guide <exercise>"
    case $2 in squat) echo 'Squat: feet shoulder-width, chest up, hips back, knees over toes, depth below parallel';; pushup) echo 'Push-up: hands shoulder-width, body straight, elbows 45deg, full ROM';; deadlift) echo 'Deadlift: bar over mid-foot, hips hinge, flat back, drive through heels';; plank) echo 'Plank: forearms on ground, body straight, engage core, hold position';; *) echo 'Exercise $2: maintain proper form, control the movement';; esac
}

cmd_search() {
    local muscle="${2:-}"
    [ -z "$muscle" ] && die "Usage: $SCRIPT_NAME search <muscle>"
    case $2 in chest) echo 'Push-up, bench press, flyes';; back) echo 'Pull-up, row, deadlift';; legs) echo 'Squat, lunge, leg press';; core) echo 'Plank, crunch, leg raise';; *) echo 'Exercises for $2: consult a trainer';; esac
}

cmd_warmup() {
    local type="${2:-}"
    [ -z "$type" ] && die "Usage: $SCRIPT_NAME warmup <type>"
    echo 'Warmup ($2): 5min cardio, dynamic stretches, activation exercises'
}

cmd_routine() {
    local goal="${2:-}"
    local minutes="${3:-}"
    [ -z "$goal" ] && die "Usage: $SCRIPT_NAME routine <goal minutes>"
    echo 'Routine ($2, ${3:-30}min): warmup 5min, main exercises 20min, cooldown 5min'
}

cmd_list() {
    local category="${2:-}"
    [ -z "$category" ] && die "Usage: $SCRIPT_NAME list <category>"
    echo 'Categories: chest, back, legs, core, shoulders, arms, cardio'
}

cmd_tips() {
    local exercise="${2:-}"
    [ -z "$exercise" ] && die "Usage: $SCRIPT_NAME tips <exercise>"
    echo 'Tips for $2: focus on form, breathe properly, progressive overload'
}

cmd_help() {
    echo "$SCRIPT_NAME v$VERSION"
    echo ""
    echo "Commands:"
    printf "  %-25s\n" "guide <exercise>"
    printf "  %-25s\n" "search <muscle>"
    printf "  %-25s\n" "warmup <type>"
    printf "  %-25s\n" "routine <goal minutes>"
    printf "  %-25s\n" "list <category>"
    printf "  %-25s\n" "tips <exercise>"
    printf "  %%-25s\n" "help"
    echo ""
    echo "Powered by BytesAgain | bytesagain.com | hello@bytesagain.com"
}

cmd_version() { echo "$SCRIPT_NAME v$VERSION"; }

main() {
    local cmd="${1:-help}"
    case "$cmd" in
        guide) shift; cmd_guide "$@" ;;
        search) shift; cmd_search "$@" ;;
        warmup) shift; cmd_warmup "$@" ;;
        routine) shift; cmd_routine "$@" ;;
        list) shift; cmd_list "$@" ;;
        tips) shift; cmd_tips "$@" ;;
        help) cmd_help ;;
        version) cmd_version ;;
        *) die "Unknown: $cmd" ;;
    esac
}

main "$@"
