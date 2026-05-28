#!/usr/bin/env python3
"""utils plugin event log — local-only Claude Code session observability.

Captures session boundaries and Skill / Task tool invocations into a daily
jsonl file. Only metadata is written — never the skill arguments, agent
prompts, or file contents. Opt out by adding YAML frontmatter to
~/.claude/utils.local.md:

    ---
    observe: off
    ---
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EVENTS_DIR = Path.home() / ".claude" / "data" / "utils" / "events"
CONFIG_FILE = Path.home() / ".claude" / "utils.local.md"
OBSERVE_RE = re.compile(r"^\s*observe\s*:\s*(\w+)\s*$", re.MULTILINE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def _emit(record: dict) -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = EVENTS_DIR / f"{day}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_record(event: dict) -> dict | None:
    hook = event.get("hook_event_name", "")
    base = {
        "ts": _now(),
        "session": event.get("session_id", ""),
        "cwd": event.get("cwd", ""),
    }

    if hook == "SessionStart":
        return {**base, "kind": "session", "phase": "start",
                "source": event.get("source", "")}

    if hook == "Stop":
        return {**base, "kind": "session", "phase": "stop"}

    if hook == "PostToolUse":
        tool = event.get("tool_name", "")
        if tool not in ("Skill", "Task"):
            return None
        tool_input = event.get("tool_input") or {}
        tool_response = event.get("tool_response") or {}
        record = {**base, "kind": "tool", "phase": "post", "tool": tool}
        if tool == "Skill":
            record["name"] = tool_input.get("skill") or tool_input.get("name", "")
        elif tool == "Task":
            record["subagent"] = tool_input.get("subagent_type", "")
        record["ok"] = not bool(tool_response.get("interrupted", False))
        return record

    return None


def main() -> int:
    if _is_off():
        return 0
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    record = _build_record(event)
    if record is None:
        return 0
    try:
        _emit(record)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
