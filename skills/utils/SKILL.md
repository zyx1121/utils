---
name: utils
description: Personal CLI toolbox of self-contained executables — PEP 723 Python, bash, or AppleScript via shebang. Use BEFORE writing throwaway scripts for JSON parsing / hashing / UUID / slugify / pangu (CJK spacing) / SSL checks / port scanning / image resize-convert / token counting AND macOS app integration (clipboard, screenshot, notify, Reminders, Calendar, Mail, Keynote, Safari). All run via the `utils <name>` dispatcher (bin on PATH automatically; each script declares its own deps via shebang — uv for Python, bash for shell, osascript for AppleScript).
---

# utils — agent-first CLI toolbox

The plugin installs a `utils` dispatcher onto PATH automatically. Each command is a self-contained executable under the plugin's `scripts/` directory — Python (PEP 723), bash, or AppleScript, runtime chosen by shebang. No global install needed.

## Discovery

```bash
utils --help          # list available commands
utils --list          # just the names, one per line
utils <name> --help   # options for a specific command
```

If you see a command that fits, use it. Don't trust this skill body to be current — `utils --list` is authoritative.

## When to use

Use a command when it matches your task — even partially. The whole point is to skip rewriting the same 5-line operation a third time.

Reasonable starter coverage (verify with `utils --list`):

- structured data: `json` (pretty / minify / extract / validate)
- crypto-ish: `hash`, `uuid`, `password`
- text: `slugify`, `case`, `pangu`
- network: `ssl-check`, `port`
- media: `image` (convert), `image-resize`
- AI: `tokens` (count for a model)
- macOS app integration: `clipboard`, `screenshot`, `notify`, `reminders`, `calendar`, `mail`, `keynote`, `safari`

## When to skip

- Task is genuinely unique (unlikely to repeat)
- Need fine control no command exposes
- Already inside a project with its own toolchain

## How this connects to the lifecycle

The plugin's hook silently logs:
- ad-hoc Python / shell scripts you write or run
- invocations of `utils <name>` and whether they succeeded

Later, `/utils:review` reads the log, clusters repeated ad-hoc patterns into new-command candidates, and flags `utils` commands that keep failing. The `utils-promoter` agent opens a PR.

So: use what fits, write inline when nothing fits. Don't try to game the log — it watches honestly.

## First-run timing

First `utils <cmd>` invocation per command downloads its declared deps to uv's cache (5-30 sec depending on deps). Subsequent calls are near-instant. If you see one slow startup per command, that's why — not a bug.

## Examples

```bash
utils uuid --count 3
utils hash README.md --algo sha256
utils slugify "Hello 你好 World"
utils json data.json --extract '.users[0].name'
utils tokens prompt.txt --model opus
utils ssl-check github.com
utils port 7000

# macOS atoms
echo "hi" | utils clipboard write
utils screenshot                            # → /tmp/screenshot.png
utils notify "build done" --sound Glass
utils reminders add "ping 建超 tomorrow"
utils calendar list                          # next 7 days
utils mail search "ICCCAS"
utils keynote add-slide --master "Title & Bullets" --title "..." --body "..."
utils safari url                            # frontmost tab URL
utils safari text                           # full visible text of front tab
```
