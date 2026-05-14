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

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()
err = Console(stderr=True, style="red")


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
STALE_DAYS = 90
DESC_MIN = 50
DESC_MAX = 500


def find_skills(root: Path, recursive: bool) -> list[Path]:
    """SKILL.md files under root. Default top-level only (skips sync artifacts
    like ~/skills/.agents/skills/...)."""
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
    path: Path = typer.Argument(Path.home() / "skills", help="Directory to scan (top-level SKILL.md files)."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Recurse into subdirectories (off by default to skip sync artifacts)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show clean skills too."),
):
    """Lint Claude Code skills under <path>. Default path: ~/skills/ (Loki's source repo)."""
    if not path.exists():
        err.print(f"skill-lint: {path} doesn't exist")
        raise typer.Exit(1)
    skills = find_skills(path, recursive)
    if not skills:
        console.print(f"[dim](no SKILL.md found under {path})[/]")
        return

    results = [(s, lint_skill(s)) for s in skills]
    with_issues = [(s, iss) for s, iss in results if iss]
    clean = [s for s, iss in results if not iss]

    if with_issues:
        table = Table(title=f"Skill lint · {path}", show_header=True)
        table.add_column("skill", style="bold")
        table.add_column("issues", style="yellow")
        for s, iss in with_issues:
            table.add_row(s.parent.name, " · ".join(iss))
        console.print(table)

    if verbose and clean:
        ct = Table(title="Clean skills", show_header=True)
        ct.add_column("skill", style="green")
        for s in clean:
            ct.add_row(s.parent.name)
        console.print(ct)

    console.print(
        f"\n[bold]{len(results)}[/] skills scanned · "
        f"[yellow]{len(with_issues)}[/] with issues · "
        f"[green]{len(clean)}[/] clean"
    )


if __name__ == "__main__":
    typer.run(main)
