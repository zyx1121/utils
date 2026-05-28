#!/usr/bin/env bash
# Play a random sound from ~/.claude/ping/ on Stop / Notification.
# Fires when Claude finishes a turn or needs user attention.
# Drop sound files into ~/.claude/ping/ (mp3/wav/m4a/aiff/aac). Empty dir = silent.

set -e

PING_DIR="${HOME}/.claude/ping"

# Drain stdin so claude doesn't block on the pipe.
cat >/dev/null 2>&1 || true

[ -d "$PING_DIR" ] || exit 0
command -v afplay >/dev/null 2>&1 || exit 0

shopt -s nullglob nocaseglob
files=( "$PING_DIR"/*.mp3 "$PING_DIR"/*.wav "$PING_DIR"/*.m4a "$PING_DIR"/*.aiff "$PING_DIR"/*.aac )
shopt -u nocaseglob

[ ${#files[@]} -gt 0 ] || exit 0

file="${files[RANDOM % ${#files[@]}]}"

# Detach so the hook returns immediately; afplay finishes on its own.
( afplay "$file" >/dev/null 2>&1 & disown ) >/dev/null 2>&1

exit 0
