#!/usr/bin/env bash
# notify — macOS banner notification (via `osascript display notification`).
# Useful for telling the user a long-running task finished while they're
# elsewhere on the screen / in another space.
set -euo pipefail

MSG=""
TITLE="Claude Code"
SUBTITLE=""
SOUND=""

usage() {
    cat <<EOF
notify — macOS banner notification

Usage:
  utils notify <message> [--title T] [--subtitle S] [--sound NAME]
  utils notify -h | --help

Examples:
  utils notify "build done"
  utils notify "Tests passed" --title "CI"
  utils notify "PR #6 merged" --title "utils" --sound Glass

Options:
  --title T       title line below app name (default: "Claude Code")
  --subtitle S    smaller line under the title
  --sound NAME    macOS system sound — Glass, Funk, Bottle, Frog, Ping, Pop,
                  Purr, Sosumi, Submarine, Tink. Default: silent.

Caveat: macOS shows "Script Editor" as the app name at the top of the banner
(that's the host osascript runs under). The --title sits below that. Switching
the app name needs a signed bundle and isn't worth it for one-shot pings.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0;;
        --title) TITLE="${2:?--title needs a value}"; shift 2;;
        --subtitle) SUBTITLE="${2:?--subtitle needs a value}"; shift 2;;
        --sound) SOUND="${2:?--sound needs a name (Glass, Funk, ...)}"; shift 2;;
        --) shift; break;;
        -*) echo "notify: unknown flag '$1' — try --help" >&2; exit 2;;
        *) MSG="$1"; shift;;
    esac
done

[ -z "$MSG" ] && { echo "notify: message required — try --help" >&2; exit 2; }

# Escape backslash and double-quote for AppleScript string literal.
escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

CMD="display notification \"$(escape "$MSG")\" with title \"$(escape "$TITLE")\""
[ -n "$SUBTITLE" ] && CMD="$CMD subtitle \"$(escape "$SUBTITLE")\""
[ -n "$SOUND" ] && CMD="$CMD sound name \"$(escape "$SOUND")\""

osascript -e "$CMD"
