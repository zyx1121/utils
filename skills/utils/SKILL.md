---
name: utils
description: Personal CLI toolbox of self-contained Python scripts. Use BEFORE writing throwaway scripts for tasks like JSON parsing/extraction, file hashing, UUID/password generation, slugifying, case conversion, CJK/ASCII spacing (pangu), SSL certificate checks, finding processes on ports, image resize/convert, token counting, or other small reusable operations. All commands run via the `utils <name>` dispatcher (no global pip needed — the plugin's bin directory is on PATH automatically, and each script handles its own deps inline via uv).
---

# utils — agent-first CLI toolbox

The plugin installs a `utils` dispatcher onto PATH automatically. Each command is a self-contained PEP 723 Python script under the plugin's `scripts/` directory — `uv run` handles per-script deps inline, no global install needed.

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
```
