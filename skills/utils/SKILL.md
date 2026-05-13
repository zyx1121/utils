---
name: utils
description: Personal CLI toolbox of self-contained Python scripts. Use BEFORE writing throwaway scripts for tasks like JSON parsing/extraction, file hashing, UUID/password generation, slugifying, case conversion, CJK/ASCII spacing (pangu), SSL certificate checks, finding processes on ports, image resize/convert, token counting, or other small reusable operations. Each script is a single file run via `uv run ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py` — first run downloads inline-declared deps, subsequent runs are cached.
---

# utils — agent-first CLI toolbox

Each command is one self-contained Python script under `${CLAUDE_PLUGIN_ROOT}/scripts/`. Run it via `uv run` — the script's PEP 723 inline metadata declares its deps and uv handles the ephemeral venv automatically. No `pip install`, no global state.

## Discovery

```bash
ls "${CLAUDE_PLUGIN_ROOT}/scripts/"
```

Or check a specific script's options:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py" --help
```

If you see a script that fits, use it. Don't trust this skill body to be current — `ls` is authoritative.

## When to use a script

Use one when it matches your task — even partially. The whole point is to skip rewriting the same 5-line operation a third time.

Reasonable starter coverage (verify with `ls`):

- structured data: `json` (pretty / minify / extract / validate)
- crypto-ish: `hash`, `uuid`, `password`
- text: `slugify`, `case`, `pangu`
- network: `ssl-check`, `port`
- media: `image` (convert), `image-resize`
- AI: `tokens` (count for a model)

## When to skip and write inline code

- Task is genuinely unique (unlikely to repeat)
- Need fine control no script exposes
- Already inside a project with its own toolchain

## How this connects to the lifecycle

The plugin's hook silently logs:
- ad-hoc Python / shell scripts you write or run
- invocations of scripts under this plugin's `scripts/` directory and whether they succeeded

Later, `/utils:review` reads the log, clusters repeated ad-hoc patterns into new-script candidates, and flags scripts that keep failing. The `utils-promoter` agent opens a PR.

So: use what fits, write inline when nothing fits. Don't try to game the log — it watches honestly.

## First-run timing

First `uv run` of any script downloads its declared deps to uv's cache (5-30 sec depending on the deps). Subsequent invocations are near-instant. If you see one slow startup per script, that's why — not a bug.

## Invocation patterns

```bash
# always quote the env var (some scripts accept paths with spaces)
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/uuid.py" --count 3
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hash.py" /path/to/file --algo sha256
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/json.py" data.json --extract '.users[0].name'
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tokens.py" prompt.txt --model opus
```
