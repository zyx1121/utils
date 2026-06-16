```
██╗   ██╗████████╗██╗██╗     ███████╗
██║   ██║╚══██╔══╝██║██║     ██╔════╝
██║   ██║   ██║   ██║██║     ███████╗
██║   ██║   ██║   ██║██║     ╚════██║
╚██████╔╝   ██║   ██║███████╗███████║
 ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝
```

# utils

Loki's personal CLI toolbox for agents. Each command is a self-contained executable — Python (PEP 723), bash, AppleScript — looked up by name and `exec`'d; runtime declared via shebang. One dispatcher, no package management.

> **Scope:** utils is *just the CLI* now. The agent machinery it used to bundle — skills, hooks, subagents, and the observe → review → promote lifecycle — moved to Loki's personal config repo (`kilo`), which symlinks into `~/.claude/`. utils is no longer wired as a Claude Code plugin; the leftover `hooks/`, `agents/`, and `.claude-plugin/` are retired packaging superseded by kilo.

## Install

The dispatcher goes on PATH with a one-line shim that `exec`s the repo — edits to `scripts/` are live, no reinstall:

```bash
printf '#!/usr/bin/env bash\nexec "$HOME/utils/bin/utils" "$@"\n' > ~/.local/bin/utils && chmod +x ~/.local/bin/utils
```

Prerequisite: [`uv`](https://docs.astral.sh/uv/) on PATH — the first Python run fetches declared deps to uv's cache, later runs are near-instant.

## Usage

```bash
utils --help              # list available commands
utils --list              # bare names, authoritative

# basics
utils uuid --count 3
utils hash README.md --algo sha256
utils ssl-check github.com
utils tokens prompt.txt --model opus
utils skill-usage                            # per-skill adoption / dormant
utils skill-lint                             # lint SKILL.md frontmatter

# macOS atoms
echo "hi" | utils clipboard write
utils screenshot                             # → /tmp/screenshot.png
utils notify "build done" --sound Glass
utils reminders add "ping 建超 tomorrow"
utils calendar list                          # this week
utils mail search "ICCCAS"
utils keynote open ~/Desktop/deck.key
utils safari url                             # frontmost tab URL
```

Under the hood, each command is a self-contained executable. Most are PEP 723 Python:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "..."]
# ///
"""<purpose>"""
import typer
def main(...): ...
if __name__ == "__main__":
    typer.run(main)
```

Bash or AppleScript also work — anything with a shebang and exec bit. The dispatcher just looks up `scripts/<cmd>` or `scripts/<cmd>.<ext>` and `exec`s the first match; shebang does the rest. First Python invocation downloads declared deps to uv's cache; later runs are near-instant. No `pip install` step ever.

The README doesn't enumerate commands — that list grows. `utils --list` is authoritative.

## Output contract

Scripts emit a JSON envelope on stdout when piped or redirected, and a human-friendly view when stdout is a terminal — toggle is automatic, no `--json` flag.

```bash
$ utils ssl-check github.com | jq -r .data.days_remaining
79
```

The envelope shape is fixed:

```jsonc
// success
{"success": true,  "data": <value>, "metadata": {...}}
// failure (exit code non-zero)
{"success": false, "error": {"message": "...", "why": "...", "hint": "..."}}
```

`data` is whatever the command produced; `metadata` carries provenance bits an agent might branch on (source path, format flag, etc). On failure, `error` gives three fields — `message` for what broke, `why` for the underlying cause, `hint` for what to try next. Errors are documentation: agents read them before they read `--help`.

Shared helpers live in [`lib/_envelope.py`](lib/_envelope.py) — `emit`, `fail`, `parse_host`. Every Python script imports them; see [`scripts/ssl-check.py`](scripts/ssl-check.py) for the canonical shape.

## Per-command setup

A few commands need a one-time macOS-side tweak before they work:

- **`safari js` / `safari selection`** — these eval JavaScript in the frontmost Safari tab. Apple gates this behind:
  1. Safari → Settings → Advanced → ✅ *Show Develop menu in menu bar*
  2. Develop menu → ✅ *Allow JavaScript from Apple Events*

  Plain `safari url` / `title` / `text` / `tabs` / `open` / `close` work out of the box without this. The `text` op alone covers most "extract page content" agent flows — JS is only needed when you want the current selection or arbitrary DOM queries.

## Layout

```
bin/
└── utils            dispatcher — looks up scripts/<cmd> and exec's it
lib/
└── _envelope.py     shared output helpers — emit / fail / parse_host
scripts/
├── skill-usage.py   `utils skill-usage` — per-skill adoption / recency / co-occurrence / dormant
├── skill-lint.py    `utils skill-lint` — lint SKILL.md frontmatter
└── *                each self-contained, exec bit + shebang (.py PEP 723, .sh, .applescript, ...)
```

`hooks/`, `agents/`, and `.claude-plugin/` still sit in the tree but are **retired plugin packaging** — the live versions run from the kilo repo. They'll be removed once confirmed dead.

## Why this design

An earlier version was a Poetry-managed PyPI package with a global `utils` CLI. That fit human use — `pip install zyx-utils` once, type `utils foo` in any terminal. But the real consumer is the agent, and PyPI carried: build pipeline, version management, sync ceremony, release tagging, signing — all overhead for someone who doesn't need a published binary.

So: scripts live in the repo, the dispatcher `exec`s them via `uv run`, and a one-line shim puts `utils` on PATH. Edit a script, it's live. No `pip`, no version mismatch, no PyPI release dance, no Poetry.

## License

[MIT](LICENSE) — if it breaks, you keep both halves.
