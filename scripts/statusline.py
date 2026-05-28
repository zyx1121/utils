#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""statusline — today's skill / agent activity at a glance, from events.jsonl.

Wired into Claude Code's statusLine: add this to ~/.claude/settings.json

    {"statusLine": {"type": "command", "command": "utils statusline"}}

Output is one short line, e.g.
    utils · skill 7 · task 2 · last method 12s
or with failures
    utils · skill 7 · task 2 · fail 1 · last method 12s

Honors the same opt-out switch as events.py: write
`observe: off` into ~/.claude/utils.local.md frontmatter and this
falls back to `utils · off`.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# scripts/json.py shadows stdlib `json` — drop our parent dir from sys.path.
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EVENTS_DIR = Path.home() / ".claude" / "data" / "utils" / "events"
CONFIG_FILE = Path.home() / ".claude" / "utils.local.md"
OBSERVE_RE = re.compile(r"^\s*observe\s*:\s*(\w+)\s*$", re.MULTILINE)


def _is_off() -> bool:
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    m = OBSERVE_RE.search(parts[1])
    if not m:
        return False
    return m.group(1).strip().lower() in {"off", "false", "no", "0"}


def _today_path() -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return EVENTS_DIR / f"{day}.jsonl"


def _human_ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _short_name(rec: dict) -> str:
    name = rec.get("name") or rec.get("subagent") or rec.get("tool", "?")
    # strip plugin prefix for compactness: "utils:method" → "method"
    if ":" in name:
        name = name.split(":", 1)[1]
    return name


def _summarize(path: Path) -> str:
    if not path.is_file():
        return "utils · no events yet"

    skills = tasks = fails = 0
    last_tool: dict | None = None
    last_ts: str | None = None

    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("kind") != "tool":
                    continue
                tool = rec.get("tool", "")
                if tool == "Skill":
                    skills += 1
                elif tool == "Task":
                    tasks += 1
                if not rec.get("ok", True):
                    fails += 1
                last_tool = rec
                last_ts = rec.get("ts", last_ts)
    except OSError:
        return "utils · ?"

    parts = ["utils", f"skill {skills}", f"task {tasks}"]
    if fails:
        parts.append(f"fail {fails}")
    if last_tool and last_ts:
        try:
            ts = datetime.fromisoformat(last_ts)
            ago = (datetime.now(timezone.utc) - ts).total_seconds()
            parts.append(f"last {_short_name(last_tool)} {_human_ago(ago)}")
        except ValueError:
            pass
    return " · ".join(parts)


def main() -> int:
    # Drain stdin so Claude Code doesn't keep the pipe open.
    try:
        sys.stdin.read()
    except Exception:
        pass
    if _is_off():
        print("utils · off")
        return 0
    print(_summarize(_today_path()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
