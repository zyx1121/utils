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

Prerequisite: [`uv`](https://docs.astral.sh/uv/) on PATH. After install, two hooks start writing local-only jsonl logs under `~/.claude/data/utils/` — `observations.jsonl` (ad-hoc script activity) and `events/YYYY-MM-DD.jsonl` (session + skill / agent invocations). Both stay on disk; nothing is uploaded.

## What's inside

A `utils` dispatcher (`bin/utils`) is installed onto PATH automatically by the plugin. Use it like a regular CLI:

```bash
utils --help              # list available commands

# basics
utils uuid --count 3
utils hash README.md --algo sha256
utils ssl-check github.com
utils tokens prompt.txt --model opus

# macOS atoms
echo "hi" | utils clipboard write
utils screenshot                            # → /tmp/screenshot.png
utils notify "build done" --sound Glass
utils reminders add "ping 建超 tomorrow"
utils calendar list                          # this week
utils mail search "ICCCAS"
utils keynote open ~/Desktop/deck.key
utils safari url                            # frontmost tab URL
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

Shared helpers live in [`lib/_envelope.py`](lib/_envelope.py) — `emit`, `fail`, `parse_host`. Every Python script imports them; see [`scripts/ssl-check.py`](scripts/ssl-check.py) for the canonical shape and [`agents/utils-promoter.md`](agents/utils-promoter.md) for the import shim new scripts must use.

## Per-command setup

A few commands need a one-time macOS-side tweak before they work:

- **`safari js` / `safari selection`** — these eval JavaScript in the frontmost Safari tab. Apple gates this behind:
  1. Safari → Settings → Advanced → ✅ *Show Develop menu in menu bar*
  2. Develop menu → ✅ *Allow JavaScript from Apple Events*

  Plain `safari url` / `title` / `text` / `tabs` / `open` / `close` work out of the box without this. The `text` op alone covers most "extract page content" agent flows — JS is only needed when you want the current selection or arbitrary DOM queries.

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

## Session events

A second hook (`events.py`) covers a different question than the throwaway-script lifecycle above: *what happened in this session* — which skills fired, which subagents got spawned, when sessions started and stopped. One record per event, one file per UTC day:

```
~/.claude/data/utils/events/YYYY-MM-DD.jsonl
```

Schema is intentionally narrow — only metadata, never the skill arguments, agent prompts, or any file contents touched. That's the privacy boundary: skip them at write time, not redact at read time.

Captured:

- `SessionStart` / `Stop` → `{kind:"session", phase, session, cwd, source}`
- `PostToolUse` for `Skill` / `Task` only → `{kind:"tool", tool, name|subagent, ok}`

Opt out by creating `~/.claude/utils.local.md`:

```markdown
---
observe: off
---
```

The hook returns early when this is present. Remove the file or set `observe: full` to re-enable. Daily files give natural rotation (`find … -mtime +30 -delete` works), and sync across machines is just `rsync` of that directory.

### Statusline

A one-line tally of today's activity. Add to `~/.claude/settings.json`:

```json
{ "statusLine": { "type": "command", "command": "utils statusline" } }
```

Output:

```
utils · skill 7 · task 2 · last method 12s
```

The fail counter only shows when there are any (`fail 1`). With opt-out on, output is `utils · off`; before any events fire today, `utils · no events yet`. Pure stdlib, no LLM call, reads the same `events/YYYY-MM-DD.jsonl`.

#### Themes

The statusline script is a thing you tinker with — colors, layout, mascot art. The same command snapshots and switches whole looks, so an experiment never clobbers a look you liked:

```
utils statusline list                  # list themes; ● marks the live one
utils statusline save monet -m "..."   # snapshot the live look as a theme
utils statusline apply minimal         # switch to a saved theme
```

A theme snapshots the look-defining files under `<dotfiles>/.claude/statusline-themes/<name>/` (relative paths preserved), so it's versioned and synced with your dotfiles. By default the bundle is `statusline-command.sh` + `ditto.ans`; drop a `.bundle` manifest (one glob per line) in the themes dir to widen it — e.g. to a renderer and its config — and `apply` will restore the whole look, not just the `.sh`. Bulk data you leave out of the manifest (large sprite pools, …) stays shared. `apply` auto-backs up the current look to the reserved `_prev` theme first, so `utils statusline apply _prev` always undoes the last switch.

## Layout

```
.claude-plugin/plugin.json      manifest
bin/
└── utils                       dispatcher — exec uv run on the right script
hooks/
├── hooks.json                  PostToolUse → observe / events; SessionStart + Stop → events; Stop / Notification → ping
├── observe.py                  append-only jsonl logger — throwaway script activity (Write / Bash)
├── events.py                   append-only jsonl logger — session + Skill / Task (metadata only, opt-out via utils.local.md)
└── ping.sh                     plays a random sound from ~/.claude/ping/ on turn-end / attention
lib/
└── _envelope.py                shared output helpers — emit / fail / parse_host
skills/
├── catchup/SKILL.md            /utils:catchup — fill in missed daily/weekly reports
├── daily/SKILL.md              /utils:daily — day-end journal (Initiative + PPP + Numbers)
├── journal/                    journal report architecture (loaded by daily / weekly)
│   ├── SKILL.md
│   └── scripts/                journal-collect, journal-install-cron
├── keynote/SKILL.md            Keynote 簡報 building blocks (AppleScript-based)
├── keynote-style/SKILL.md      Loki's deck style guide — cover/outline/content rules + Chinese speaker notes
├── method/                     procedure router — picks the right methodology (rca / cove / steelman / ...)
│   ├── SKILL.md
│   └── assets/                 14 methodologies as progressive-disclosure refs
├── morning/SKILL.md            /utils:morning — day-start briefing from journal / TODO / calendar / mail
├── now/SKILL.md                /utils:now — last-N-hours snapshot
├── post/SKILL.md               /utils:post — idea → ~1500-word blog → private gist
├── pve/SKILL.md                PVE / gateway atoms — wraps utils pve subcommands
├── review/SKILL.md             /utils:review — find candidates (usage log) + lint personal skills (static)
├── session/                    /utils:session — summarize one or many Claude Code sessions
│   ├── SKILL.md
│   └── scripts/                journal-session
├── stats/SKILL.md              /utils:stats — raw numbers, no narrative
├── teaching-slides/SKILL.md   recorded-course deck rules — one point / slide, ≤ 6 lines, big font, prefer images
├── utils/SKILL.md              "before writing a script, try `utils <cmd>` first"
└── weekly/SKILL.md             /utils:weekly — week-end journal with Δ vs last week
agents/
├── pve-provisioner.md          one-shot VM provisioning: clone + DNS + forward + Caddy + smoke test
├── session-summarizer.md       per-session journal entry writer (dispatched in parallel by /utils:session)
└── utils-promoter.md           candidate → scripts/<name>.<ext> → PR
scripts/
├── statusline.py               `utils statusline` — activity tally + theme save/apply/list
└── *                           each one self-contained, exec bit + shebang
                                (.py PEP 723, .sh, .applescript, ...)
```

## Storage

```
~/.claude/data/utils/
├── observations.jsonl   everything observe.py saw
├── reviewed.jsonl       candidates already promoted or dismissed
├── events/
│   └── YYYY-MM-DD.jsonl session + skill / agent events (events.py)
└── journal/
    ├── sessions/        per-session markdown summaries
    └── reports/         YYYY/MM/DD.md daily, YYYY/W<NN>.md weekly
```

No auto-rotation yet. Trim by hand if it ever gets big.

## Why this design

An earlier version was a Poetry-managed PyPI package with a global `utils` CLI. That fit human use — `pip install zyx-utils` once, type `utils foo` in any terminal. But the real consumer is the agent, and PyPI carried: build pipeline, version management, sync-across-devices ceremony, release tagging, signing. All overhead for someone who doesn't need a global binary.

So: plugin ships scripts directly. Agent runs them via `uv run`. New device gets everything from `claude plugin install`. No `pip` step, no version mismatch, no PyPI release dance, no Poetry.

## License

[MIT](LICENSE) — if it breaks, you keep both halves.
