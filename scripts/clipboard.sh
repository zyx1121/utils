#!/usr/bin/env bash
# clipboard — read / write / clear the macOS clipboard via pbpaste / pbcopy.
set -euo pipefail

case "${1:-read}" in
    read)
        pbpaste
        ;;
    write)
        # Reads stdin and copies into the clipboard.
        pbcopy
        ;;
    clear)
        printf "" | pbcopy
        ;;
    -h|--help)
        cat <<EOF
clipboard — macOS clipboard read/write/clear

Usage:
  utils clipboard read           print current clipboard to stdout
  utils clipboard write          copy stdin into clipboard
  utils clipboard clear          empty the clipboard
  utils clipboard --help         show this

Examples:
  echo "hello" | utils clipboard write
  utils clipboard read
  pbpaste | wc -c    # equivalent to: utils clipboard read | wc -c
EOF
        ;;
    *)
        echo "clipboard: unknown action '$1' — try read / write / clear / --help" >&2
        exit 2
        ;;
esac
