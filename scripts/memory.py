#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "pyyaml"]
# ///
"""Browse and search Claude Code memory files (YAML frontmatter + MD body)."""
from __future__ import annotations

# Siblings shadow stdlib (json.py, uuid.py, …) — drop our dir off sys.path.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Browse Claude Code memory — list / recent / search / show.",
)
console = Console()
err = Console(stderr=True, style="red")


# ── path resolution ──────────────────────────────────────────────
def memory_dir() -> Path:
    """Resolve the active memory directory.

    Claude Code stores per-project memory under ``~/.claude/projects/<cwd-encoded>/memory/``
    where the encoding replaces `/` with `-` (so ``/Users/loki`` → ``-Users-loki``).
    Try the current cwd first, then fall back to ``$HOME``'s encoding.
    """
    home = Path.home()
    cwd = Path.cwd()
    for base in (cwd, home):
        encoded = str(base).replace("/", "-")
        candidate = home / ".claude" / "projects" / encoded / "memory"
        if candidate.is_dir():
            return candidate
    err.print(f"memory: no memory directory found (checked {cwd} and {home})")
    raise typer.Exit(1)


# ── parsing ──────────────────────────────────────────────────────
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_memory(path: Path) -> dict:
    """Return name / description / type / body / mtime / path for one memory file."""
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        body = m.group(2).strip()
    else:
        fm, body = {}, text
    return {
        "name": fm.get("name", path.stem),
        "description": fm.get("description", ""),
        "type": (fm.get("metadata") or {}).get("type", "?"),
        "body": body,
        "path": path,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime),
    }


def all_memories() -> list[dict]:
    """All memories, sorted by the `name:` frontmatter field (case-insensitive)."""
    parsed = [parse_memory(f) for f in memory_dir().glob("*.md") if f.name != "MEMORY.md"]
    return sorted(parsed, key=lambda m: m["name"].lower())


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


# ── list ─────────────────────────────────────────────────────────
@app.command(name="list", help="Table of all memories (name, type, description).")
def list_cmd(
    type_: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type: feedback / project / user / reference."),
):
    memories = all_memories()
    if type_:
        memories = [m for m in memories if m["type"] == type_]
    if not memories:
        console.print("[dim](no memories)[/]")
        return
    table = Table(title=f"Memory · {memory_dir()}", show_header=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("name", style="bold")
    table.add_column("type", style="dim")
    table.add_column("description")
    for i, m in enumerate(memories, 1):
        table.add_row(str(i), m["name"], m["type"], _truncate(m["description"], 80))
    console.print(table)


# ── recent ───────────────────────────────────────────────────────
@app.command(help="Memories modified recently (default last 14 days).")
def recent(
    days: int = typer.Option(14, "--days", "-d", help="How many days back to look."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max rows."),
):
    cutoff = datetime.now() - timedelta(days=days)
    memories = sorted(
        (m for m in all_memories() if m["mtime"] >= cutoff),
        key=lambda m: m["mtime"],
        reverse=True,
    )
    if limit:
        memories = memories[:limit]
    if not memories:
        console.print(f"[dim](no memories modified in the last {days} days)[/]")
        return
    table = Table(title=f"Memory · last {days}d", show_header=True)
    table.add_column("mtime", style="cyan")
    table.add_column("name", style="bold")
    table.add_column("type", style="dim")
    table.add_column("description")
    for m in memories:
        table.add_row(m["mtime"].strftime("%Y-%m-%d %H:%M"), m["name"], m["type"], _truncate(m["description"], 60))
    console.print(table)


# ── search ───────────────────────────────────────────────────────
@app.command(help="Grep titles / descriptions / bodies for <query> (case-insensitive).")
def search(
    query: str = typer.Argument(..., help="Substring to match."),
    body: bool = typer.Option(True, "--body/--no-body", help="Search inside bodies (slower)."),
):
    needle = query.lower()
    hits = []
    for m in all_memories():
        haystack = (m["name"] + "\n" + m["description"]).lower()
        if body:
            haystack += "\n" + m["body"].lower()
        if needle in haystack:
            hits.append(m)
    if not hits:
        console.print(f"[dim](no memories matching '{query}')[/]")
        return
    table = Table(title=f"Search '{query}' · {len(hits)} hits", show_header=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("name", style="bold")
    table.add_column("type", style="dim")
    table.add_column("description")
    for i, m in enumerate(hits, 1):
        table.add_row(str(i), m["name"], m["type"], _truncate(m["description"], 80))
    console.print(table)


# ── show ─────────────────────────────────────────────────────────
@app.command(help="Print a memory's full content (frontmatter + body).")
def show(
    name: str = typer.Argument(..., help="Memory name — match `name:` frontmatter, file stem, or substring."),
):
    target: Optional[Path] = None
    d = memory_dir()
    # 1. exact filename match
    for f in d.glob("*.md"):
        if f.name == "MEMORY.md":
            continue
        if f.stem == name:
            target = f
            break
    # 2. exact name-field match
    if not target:
        for m in all_memories():
            if m["name"] == name:
                target = m["path"]
                break
    # 3. case-insensitive substring on stem or name
    if not target:
        lower = name.lower()
        for m in all_memories():
            if lower in m["path"].stem.lower() or lower in m["name"].lower():
                target = m["path"]
                break
    if not target:
        err.print(f"memory: no memory matching '{name}'")
        raise typer.Exit(1)
    console.print(target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    app()
