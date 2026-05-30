#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""statusline — today's skill / agent activity tally + statusline theme manager.

Two modes, dispatched on argv:

  No args (stdin-driven) — emit the activity tally. This is what Claude Code's
  statusLine calls. Add to ~/.claude/settings.json:

      {"statusLine": {"type": "command", "command": "utils statusline"}}

  Output is one short line, e.g.
      utils · skill 7 · task 2 · last method 12s

  Theme subcommands — snapshot / switch the whole statusline look. A "theme" is
  a full, lossless snapshot of the live statusline-command.sh (+ ditto.ans if
  present), stored under <dotfiles>/.claude/statusline-themes/<name>/ so it
  rides along with your dotfiles (versioned + synced).

      utils statusline list                  list themes; ● marks the live one
      utils statusline save <name> [-m msg]  snapshot the live statusline
      utils statusline apply <name>          switch to a saved theme

  apply auto-snapshots the current look to the reserved theme `_prev` first, so
  a switch never loses your working state — `utils statusline apply _prev` undoes it.

Tally honors the same opt-out as events.py: write `observe: off` into
~/.claude/utils.local.md frontmatter and the tally falls back to `utils · off`.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# scripts/json.py shadows stdlib `json` — drop our parent dir from sys.path.
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

EVENTS_DIR = Path.home() / ".claude" / "data" / "utils" / "events"
CONFIG_FILE = Path.home() / ".claude" / "utils.local.md"
OBSERVE_RE = re.compile(r"^\s*observe\s*:\s*(\w+)\s*$", re.MULTILINE)


# ─── tally (default statusLine invocation) ──────────────────────────────────

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


def _tally() -> int:
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


# ─── theme manager ──────────────────────────────────────────────────────────
#
# A theme snapshots a set of statusline files (the "bundle") under
# statusline-themes/<name>/, preserving their relative paths. The bundle defaults
# to statusline-command.sh + ditto.ans, but a `.bundle` manifest in the themes dir
# (one glob per line) can widen it — e.g. to a renderer and its config — so that
# `apply` restores a whole look. Bulk data the manifest omits (large sprite pools,
# …) stays shared and version-controlled separately. Paths resolve through the
# live symlink, so everything lands in the dotfiles repo wherever it lives.

SAVE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")   # user-savable
APPLY_NAME_RE = re.compile(r"^_?[a-z0-9][a-z0-9-]{0,39}$")  # also reserved _prev

ACTIVE_SCRIPT = Path.home() / ".claude" / "statusline-command.sh"
DEFAULT_BUNDLE = ["statusline-command.sh", "ditto.ans"]


def _claude_dir() -> Path:
    return ACTIVE_SCRIPT.resolve().parent


def _themes_dir() -> Path:
    return _claude_dir() / "statusline-themes"


def _live_script() -> Path:
    return _claude_dir() / "statusline-command.sh"


def _bundle_spec() -> list[str]:
    """Glob patterns to snapshot, from statusline-themes/.bundle (one per line)."""
    try:
        lines = (_themes_dir() / ".bundle").read_text(encoding="utf-8").splitlines()
    except OSError:
        return DEFAULT_BUNDLE
    pats = [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    return pats or DEFAULT_BUNDLE


def _bundle_relpaths() -> list[str]:
    """Resolve the spec against the live dir → sorted relpaths of existing files."""
    base = _claude_dir()
    rels: set[str] = set()
    for pat in _bundle_spec():
        for p in base.glob(pat):
            if p.is_file() and "statusline-themes" not in p.relative_to(base).parts:
                rels.add(p.relative_to(base).as_posix())
    return sorted(rels)


def _hash_bundle(base: Path, relpaths: list[str]) -> str | None:
    """Hash the given relpaths under base — for active-theme detection."""
    if not (base / "statusline-command.sh").is_file():
        return None
    h = hashlib.sha256()
    for rel in relpaths:
        f = base / rel
        h.update(rel.encode())
        h.update(b"\x00")
        h.update(f.read_bytes() if f.is_file() else b"\x00missing")
        h.update(b"\x00")
    return h.hexdigest()


def _read_meta(theme_dir: Path) -> dict:
    try:
        return json.loads((theme_dir / "theme.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _snapshot(name: str, description: str) -> list[str]:
    """Copy the bundle into themes/<name>/ (preserving relpaths). Returns the files."""
    relpaths = _bundle_relpaths()
    if "statusline-command.sh" not in relpaths:
        raise FileNotFoundError(f"no live statusline at {_live_script()}")
    base, dest = _claude_dir(), _themes_dir() / name
    shutil.rmtree(dest, ignore_errors=True)
    for rel in relpaths:
        d = dest / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_bytes((base / rel).read_bytes())
    meta = {
        "description": description,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": relpaths,
    }
    (dest / "theme.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return relpaths


def _cmd_list() -> int:
    tdir = _themes_dir()
    themes = sorted(p for p in tdir.glob("*") if p.is_dir()) if tdir.is_dir() else []
    if not themes:
        print(f"no themes yet — `utils statusline save <name>` to snapshot the current look")
        print(f"  ({tdir})")
        return 0

    relpaths = _bundle_relpaths()
    live = _hash_bundle(_claude_dir(), relpaths)
    active_seen = False
    print(f"statusline themes  ({tdir})\n")
    for t in themes:
        is_active = live is not None and _hash_bundle(t, relpaths) == live
        active_seen = active_seen or is_active
        meta = _read_meta(t)
        saved = meta.get("saved_at", "")[:10]
        line = f" {'●' if is_active else ' '} {t.name:<20}"
        if saved:
            line += f" {saved}"
        if meta.get("description"):
            line += f"  {meta['description']}"
        print(line)
    if not active_seen:
        print("\n(現役有未存的改動，不對應任何 theme — `save` 後才會被標記)")
    return 0


def _cmd_save(args: list[str]) -> int:
    name: str | None = None
    msg = ""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-m", "--message"):
            if i + 1 >= len(args):
                print("statusline save: -m needs a value", file=sys.stderr)
                return 2
            msg = args[i + 1]
            i += 2
        elif name is None and not a.startswith("-"):
            name = a
            i += 1
        else:
            print(f"statusline save: unexpected arg '{a}'", file=sys.stderr)
            return 2
    if not name:
        print("usage: utils statusline save <name> [-m message]", file=sys.stderr)
        return 2
    if not SAVE_NAME_RE.match(name):
        print(
            f"statusline save: invalid name '{name}' "
            "(lowercase a-z 0-9 and -, can't start with - or _)",
            file=sys.stderr,
        )
        return 2

    existed = (_themes_dir() / name).is_dir()
    files = _snapshot(name, msg)
    verb = "updated" if existed else "saved"
    print(f"{verb} theme '{name}'  →  {_themes_dir() / name}")
    print(f"  bundled {len(files)} file(s): {', '.join(files)}")
    print("  commit dotfiles to sync across devices")
    return 0


def _cmd_apply(args: list[str]) -> int:
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: utils statusline apply <name>", file=sys.stderr)
        return 2
    name = args[0]
    if not APPLY_NAME_RE.match(name):
        print(f"statusline apply: invalid name '{name}'", file=sys.stderr)
        return 2

    theme = _themes_dir() / name
    if not (theme / "statusline-command.sh").is_file():
        print(f"statusline apply: no theme '{name}' (try `utils statusline list`)", file=sys.stderr)
        return 2

    # Auto-backup the live look so the switch is never destructive.
    backed_up = False
    if name != "_prev" and _live_script().is_file():
        _snapshot("_prev", f"auto-backup before applying '{name}'")
        backed_up = True

    base, restored = _claude_dir(), []
    for f in sorted(theme.rglob("*")):
        if not f.is_file() or f.name == "theme.json":
            continue
        rel = f.relative_to(theme)
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.read_bytes())
        restored.append(rel.as_posix())

    print(f"applied theme '{name}'  →  restored {len(restored)} file(s): {', '.join(restored)}")
    if backed_up:
        print("  previous look saved as '_prev' — `utils statusline apply _prev` to undo")
    print("  commit dotfiles to sync across devices")
    return 0


HELP = """utils statusline — activity tally + theme manager

  utils statusline                       emit the activity tally (statusLine use)
  utils statusline list                  list saved themes; ● marks the live one
  utils statusline save <name> [-m msg]  snapshot the bundle as a theme
  utils statusline apply <name>          switch to a saved theme (backs up to _prev)

A theme snapshots a set of statusline files under
<dotfiles>/.claude/statusline-themes/<name>/. The set defaults to
statusline-command.sh + ditto.ans; a `.bundle` manifest (one glob per line) in
the themes dir widens it so `apply` can restore a full look.
"""


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        return _tally()
    cmd = argv[0]
    if cmd in ("-h", "--help"):
        print(HELP)
        return 0
    if cmd == "list":
        return _cmd_list()
    if cmd == "save":
        return _cmd_save(argv[1:])
    if cmd == "apply":
        return _cmd_apply(argv[1:])
    print(f"statusline: unknown subcommand '{cmd}' — try `utils statusline --help`", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
