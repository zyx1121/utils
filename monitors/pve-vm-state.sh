#!/usr/bin/env bash
# pve-vm-state — emit one JSON line per VM state transition on the PVE host.
#
# Loop: every $UTILS_PVE_MONITOR_INTERVAL seconds (default 30) we ssh into
# $UTILS_PVE_HOST (default: pve), parse `qm list`, diff against the previous
# snapshot, and print one JSON line for every (vmid, name) whose status changed.
# Silent the rest of the time — monitors stdout becomes Claude notifications,
# so spamming would be useless.
#
# Snapshot lives under $XDG_RUNTIME_DIR or /tmp; persists across restarts so
# the first tick after a relaunch doesn't replay every running VM as "new".

set -uo pipefail

PVE_HOST="${UTILS_PVE_HOST:-pve}"
INTERVAL="${UTILS_PVE_MONITOR_INTERVAL:-30}"
SNAPSHOT_DIR="${XDG_RUNTIME_DIR:-/tmp}"
SNAPSHOT="$SNAPSHOT_DIR/utils-pve-vm-state.snapshot"

snapshot_now() {
    ssh -o ConnectTimeout=5 -o BatchMode=yes "$PVE_HOST" 'qm list' 2>/dev/null \
      | awk 'NR>1 && $1 ~ /^[0-9]+$/ {print $1, $2, $3}' \
      | sort
}

emit_changes() {
    local old="$1" new="$2"
    # join on vmid; print transitions where status differs.
    join -j 1 \
        <(echo "$old" | awk '{print $1, $2, $3}') \
        <(echo "$new" | awk '{print $1, $2, $3}') \
        2>/dev/null \
      | awk '$3 != $5 {
            printf "{\"event\":\"pve-vm-state\",\"vmid\":%s,\"name\":\"%s\",\"from\":\"%s\",\"to\":\"%s\"}\n", $1, $2, $3, $5
            fflush()
        }'
    # vms appeared (in new, not in old)
    comm -13 <(echo "$old" | awk '{print $1}' | sort -u) \
             <(echo "$new" | awk '{print $1}' | sort -u) \
      | while read -r vmid; do
            line=$(echo "$new" | awk -v v="$vmid" '$1==v')
            name=$(echo "$line" | awk '{print $2}')
            status=$(echo "$line" | awk '{print $3}')
            printf '{"event":"pve-vm-appeared","vmid":%s,"name":"%s","status":"%s"}\n' "$vmid" "$name" "$status"
        done
    # vms disappeared (in old, not in new)
    comm -23 <(echo "$old" | awk '{print $1}' | sort -u) \
             <(echo "$new" | awk '{print $1}' | sort -u) \
      | while read -r vmid; do
            line=$(echo "$old" | awk -v v="$vmid" '$1==v')
            name=$(echo "$line" | awk '{print $2}')
            printf '{"event":"pve-vm-disappeared","vmid":%s,"name":"%s"}\n' "$vmid" "$name"
        done
}

while true; do
    new=$(snapshot_now || true)
    if [[ -n "$new" && -f "$SNAPSHOT" ]]; then
        old=$(cat "$SNAPSHOT")
        if [[ "$old" != "$new" ]]; then
            emit_changes "$old" "$new"
        fi
    fi
    [[ -n "$new" ]] && echo "$new" > "$SNAPSHOT"
    sleep "$INTERVAL"
done
