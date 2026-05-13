```
██╗   ██╗████████╗██╗██╗     ███████╗
██║   ██║╚══██╔══╝██║██║     ██╔════╝
██║   ██║   ██║   ██║██║     ███████╗
██║   ██║   ██║   ██║██║     ╚════██║
╚██████╔╝   ██║   ██║███████╗███████║
 ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝
```

# utils

Agent-first CLI toolbox. Hooks watch the throwaway scripts your agent writes, propose new ones when patterns repeat. Each command is a self-contained executable — Python (PEP 723), bash, AppleScript, whatever — runtime declared via shebang. The plugin ships everything; no Poetry, no PyPI, no package management.

## Install

```
/plugin marketplace add zyx1121/marketplace
/plugin install utils@zyx1121
```

Prerequisite: [`uv`](https://docs.astral.sh/uv/) on PATH. After install, the hook starts logging to `~/.claude/data/utils/observations.jsonl`.

## What's inside

A `utils` dispatcher (`bin/utils`) is installed onto PATH automatically by the plugin. Use it like a regular CLI:

```bash
utils --help          # list available commands
utils uuid --count 3
utils hash README.md --algo sha256
utils ssl-check github.com
utils tokens prompt.txt --model opus
echo "hi" | utils clipboard write
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

## Lifecycle

```
[agent writes throwaway script]
            │
            ▼
   PostToolUse hook (cheap, no LLM)
            │
            ▼
~/.claude/data/utils/observations.jsonl
            │
            ▼
   /utils:review (you, on demand)
            │   cluster repeats
            │   flag failing scripts
            ▼
  approve candidate → utils-promoter agent
            │
            ▼
       PR to this repo
            │
            ▼
       merge → next session has it
```

Three layers, kept separate so the cheap thing stays cheap:

- **Observe** (hook) — pure logging. No LLM, no network, ~1ms per event. Filters noise (`ls`, `cat`, `git`, …), records ad-hoc script writes / runs and invocations of this plugin's own scripts.
- **Analyze** (`/utils:review` skill) — read the log, cluster semantically, present candidates as a table. You decide which to promote.
- **Promote** (`utils-promoter` agent) — write the new script, open a PR. You merge.

## Layout

```
.claude-plugin/plugin.json      manifest
bin/
└── utils                       dispatcher — exec uv run on the right script
hooks/
├── hooks.json                  PostToolUse(Write|Bash) → observe.py
└── observe.py                  append-only jsonl logger
skills/
├── utils/SKILL.md              "before writing a script, try `utils <cmd>` first"
└── utils-review/SKILL.md       /utils:review — find candidates
agents/
└── utils-promoter.md           candidate → scripts/<name>.py → PR
scripts/
└── *                           each one self-contained, exec bit + shebang
                                (.py PEP 723, .sh, .applescript, ...)
```

## Storage

```
~/.claude/data/utils/
├── observations.jsonl   everything the hook saw
└── reviewed.jsonl       candidates already promoted or dismissed
```

No auto-rotation yet. Trim by hand if it ever gets big.

## Why this design

An earlier version was a Poetry-managed PyPI package with a global `utils` CLI. That fit human use — `pip install zyx-utils` once, type `utils foo` in any terminal. But the real consumer is the agent, and PyPI carried: build pipeline, version management, sync-across-devices ceremony, release tagging, signing. All overhead for someone who doesn't need a global binary.

So: plugin ships scripts directly. Agent runs them via `uv run`. New device gets everything from `claude plugin install`. No `pip` step, no version mismatch, no PyPI release dance, no Poetry.

## License

[MIT](LICENSE) — if it breaks, you keep both halves.
