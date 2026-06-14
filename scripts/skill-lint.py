#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "pyyaml"]
# ///
"""Lint Claude Code skills — frontmatter, description length, staleness, name match."""
from __future__ import annotations

# Siblings shadow stdlib (json.py, uuid.py, …) — drop our dir off sys.path.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
# Add ../lib for shared output helpers (envelope, fail).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import re
from datetime import datetime
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from _envelope import emit, fail  # noqa: E402

console = Console()


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
STALE_DAYS = 90
DESC_MIN = 50
DESC_MAX = 500


def find_skills(root: Path, recursive: bool) -> list[Path]:
    """SKILL.md files under root. Default top-level only (skips sync artifacts
    like ~/.kilo/skills/.agents/skills/...)."""
    if recursive:
        return sorted(
            f for f in root.rglob("SKILL.md")
            if not any(part.startswith(".") for part in f.relative_to(root).parts[:-1])
        )
    return sorted(root.glob("*/SKILL.md"))


def lint_skill(path: Path) -> list[str]:
    """Return list of issue strings for one SKILL.md (empty list = clean)."""
    issues: list[str] = []
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return ["no-frontmatter"]
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        return [f"yaml-parse-error ({e.__class__.__name__})"]
    body = m.group(2).strip()
    if not fm.get("name"):
        issues.append("missing-name")
    if not fm.get("description"):
        issues.append("missing-description")
    else:
        d = fm["description"]
        if len(d) < DESC_MIN:
            issues.append(f"description-short ({len(d)} chars)")
        elif len(d) > DESC_MAX:
            issues.append(f"description-long ({len(d)} chars)")
    expected = path.parent.name
    if fm.get("name") and fm["name"] != expected:
        issues.append(f"name-mismatch (name={fm['name']} vs dir={expected})")
    age = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).days
    if age > STALE_DAYS:
        issues.append(f"stale ({age}d)")
    if not body:
        issues.append("empty-body")
    return issues


def main(
    path: Path = typer.Argument(Path.home() / ".kilo" / "skills", help="Directory to scan (top-level SKILL.md files)."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Recurse into subdirectories (off by default to skip sync artifacts)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show clean skills too."),
):
    """Lint Claude Code skills under <path>. Default path: ~/.kilo/skills/ (Loki's kilo source repo)."""
    if not path.exists():
        fail(f"{path} doesn't exist", hint="pass a directory containing */SKILL.md")
    skills = find_skills(path, recursive)
    results = [(s, lint_skill(s)) for s in skills]
    with_issues = [{"skill": s.parent.name, "issues": iss} for s, iss in results if iss]
    clean = [s.parent.name for s, iss in results if not iss]

    data = {
        "scanned": len(results),
        "with_issues": with_issues,
        "clean": clean if verbose else [],
    }

    def human(d, _meta):
        if not skills:
            console.print(f"[dim](no SKILL.md found under {path})[/]")
            return
        if d["with_issues"]:
            table = Table(title=f"Skill lint · {path}", show_header=True)
            table.add_column("skill", style="bold")
            table.add_column("issues", style="yellow")
            for row in d["with_issues"]:
                table.add_row(row["skill"], " · ".join(row["issues"]))
            console.print(table)
        if verbose and clean:
            ct = Table(title="Clean skills", show_header=True)
            ct.add_column("skill", style="green")
            for name in clean:
                ct.add_row(name)
            console.print(ct)
        console.print(
            f"\n[bold]{d['scanned']}[/] skills scanned · "
            f"[yellow]{len(d['with_issues'])}[/] with issues · "
            f"[green]{len(clean)}[/] clean"
        )

    emit(
        data,
        {"path": str(path), "scanned": len(results),
         "issues": len(with_issues), "clean": len(clean)},
        human=human,
    )


if __name__ == "__main__":
    app = typer.Typer(rich_markup_mode=None, add_completion=False)
    app.command()(main)
    app()
