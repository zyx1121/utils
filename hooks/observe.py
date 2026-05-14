#!/usr/bin/env python3
"""utils plugin observer — append ad-hoc script writes, script runs, and utils-script
invocations to a jsonl log.

Stays cheap on purpose: no LLM, no network, ~1ms per event.
Heavy lifting happens later in /utils:review.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path.home() / ".claude" / "data" / "utils"
LOG_FILE = LOG_DIR / "observations.jsonl"
MAX_CONTENT = 4096
MAX_STDERR = 512

NOISE_BASH_FIRST_WORD = {
    "ls", "cd", "cat", "head", "tail", "grep", "find", "git",
    "echo", "pwd", "which", "type", "rg", "fd", "tree", "mkdir",
    "touch", "cp", "mv", "rm", "ln", "stat", "wc", "sort", "uniq",
    "diff", "test", "true", "false", "sleep", "env", "export",
    "source", ".",
}
NOISE_PATH_PARTS = (
    "node_modules", "__pycache__", ".next", ".venv", "venv", "dist",
    "build", ".git/", ".cache",
)
SCRIPT_EXTS = (".py", ".sh", ".ts", ".js", ".mjs", ".rb", ".pl")

SCRIPT_RUN_RE = re.compile(r"\b(python3?|node|bun|deno|sh|bash|zsh|ruby|perl)\s+\S")
UV_RUN_RE = re.compile(r"\buv\s+run\b")
UTILS_CMD_RE = re.compile(r"(?:^|[\s;&|()`])utils\s+([\w-]+)")
PLUGIN_SCRIPT_RE = re.compile(r"/scripts/([\w.\-]+?)\.py\b")
UTILS_META_FLAGS = {"--help", "-h", "--list"}


def _is_noise_bash(cmd: str) -> bool:
    cmd = cmd.strip()
    if not cmd:
        return True
    head = cmd.split(None, 1)[0]
    return head in NOISE_BASH_FIRST_WORD


def _is_script_run(cmd: str) -> bool:
    return bool(SCRIPT_RUN_RE.search(cmd) or UV_RUN_RE.search(cmd))


def _is_utils_call(cmd: str) -> tuple[bool, str | None]:
    # primary path: `utils <name> ...` via the dispatcher in bin/
    # find first non-meta match (handles `utils --list && utils uuid` etc.)
    for match in UTILS_CMD_RE.finditer(cmd):
        name = match.group(1)
        if name not in UTILS_META_FLAGS:
            return True, name
    # fallback: direct invocation of a plugin script by path
    if "CLAUDE_PLUGIN_ROOT" in cmd or ".claude/plugins" in cmd:
        m = PLUGIN_SCRIPT_RE.search(cmd)
        if m:
            return True, m.group(1)
    return False, None


def _is_script_file(path: str) -> bool:
    return path.endswith(SCRIPT_EXTS)


def _in_noise_path(path: str) -> bool:
    return any(part in path for part in NOISE_PATH_PARTS)


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_record(event: dict) -> dict | None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response") or {}
    base = {
        "ts": _now(),
        "session": event.get("session_id", ""),
        "cwd": event.get("cwd", ""),
    }

    if tool == "Write":
        path = tool_input.get("file_path", "") or ""
        if not _is_script_file(path) or _in_noise_path(path):
            return None
        content = tool_input.get("content", "") or ""
        return {
            **base,
            "kind": "write-script",
            "path": path,
            "content_hash": _hash(content),
            "content_preview": content[:MAX_CONTENT],
        }

    if tool == "Bash":
        cmd = (tool_input.get("command", "") or "").strip()
        if not cmd or _is_noise_bash(cmd):
            return None

        stderr_tail = (tool_response.get("stderr", "") or "")[-MAX_STDERR:]
        interrupted = bool(tool_response.get("interrupted", False))

        is_utils, script_name = _is_utils_call(cmd)
        if is_utils:
            return {
                **base,
                "kind": "utils-usage",
                "script": script_name,
                "command": cmd[:MAX_CONTENT],
                "interrupted": interrupted,
                "stderr_tail": stderr_tail,
            }

        if _is_script_run(cmd):
            return {
                **base,
                "kind": "script-run",
                "command": cmd[:MAX_CONTENT],
                "interrupted": interrupted,
                "stderr_tail": stderr_tail,
            }
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    record = _build_record(event)
    if record is not None:
        try:
            _emit(record)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
