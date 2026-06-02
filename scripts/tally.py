#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich"]
# ///
"""Tally tool usage from the observation log — calls, active days, burst vs habitual."""
from __future__ import annotations

# Siblings shadow stdlib (json.py, uuid.py) — drop our dir off sys.path so typer/rich resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from _envelope import emit, fail  # noqa: E402

LOG = Path.home() / ".claude" / "data" / "utils" / "observations.jsonl"
SCRIPTS_DIR = Path(__file__).resolve().parent
# Synthetic sessions the observer writes during its own tests — never real usage.
TEST_SESSIONS = {"test123", ""}

app = typer.Typer(rich_markup_mode=None, add_completion=False)
console = Console(highlight=False)


def _known_tools() -> set[str]:
    """The real command set = executable scripts in this dir. Self-maintaining:
    a tool added tomorrow is recognized without touching a hardcoded allowlist."""
    names = set()
    for f in SCRIPTS_DIR.iterdir():
        if f.is_file() and f.name != "__init__.py" and not f.name.startswith("_"):
            names.add(f.stem)
    return names


def _classify(active_days: int, peak: int, total: int) -> str:
    """one-off (single day) / burst (few days, mostly one spike) / habitual (spread out).
    Raw totals mislead — a tool tested 200× on one dev day reads as 'heavy' but isn't a
    habit. active_days + peak-share separate the dev spike from the daily reliance."""
    if active_days <= 1:
        return "one-off"
    if active_days <= 3 and peak / total >= 0.5:
        return "burst"
    return "habitual"


def main(
    since: Optional[str] = typer.Option(None, "--since", help="Only count records on/after this date (YYYY-MM-DD)."),
    until: Optional[str] = typer.Option(None, "--until", help="Only count records on/before this date (YYYY-MM-DD)."),
    top: Optional[int] = typer.Option(None, "--top", "-n", help="Show only the top N tools by call count."),
    show_all: bool = typer.Option(False, "--all", help="Also list every unrecognized name in full (regex false positives, ad-hoc strings)."),
) -> None:
    """Aggregate `utils <tool>` invocations recorded by the observe hook. Totals alone
    mislead, so each tool is tagged one-off / burst / habitual from its active-day spread."""
    if not LOG.exists():
        fail(
            f"no observation log at {LOG}",
            why="the observe hook hasn't recorded anything yet",
            hint="run a few `utils <cmd>` calls, then try again",
        )

    known = _known_tools()
    tool_days: dict[str, Counter] = defaultdict(Counter)  # name -> {day: count}
    unrecognized: Counter = Counter()
    by_kind: Counter = Counter()
    sessions: set[str] = set()
    parsed = 0

    for line in LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if r.get("session") in TEST_SESSIONS:
            continue
        day = (r.get("ts") or "")[:10]
        if since and day < since:
            continue
        if until and day > until:
            continue
        parsed += 1
        by_kind[r.get("kind") or "?"] += 1
        sessions.add(r.get("session") or "")
        if r.get("kind") != "utils-usage":
            continue
        name = r.get("script")
        if not name or not day:
            continue
        if name in known:
            tool_days[name][day] += 1
        else:
            unrecognized[name] += 1

    tools = []
    for name, days in tool_days.items():
        total = sum(days.values())
        peak_day, peak = days.most_common(1)[0]
        tools.append({
            "name": name,
            "calls": total,
            "active_days": len(days),
            "span": [min(days), max(days)],
            "peak_day": peak_day,
            "peak_calls": peak,
            "class": _classify(len(days), peak, total),
        })
    tools.sort(key=lambda t: (-t["calls"], t["name"]))
    if top:
        tools = tools[:top]

    unrec = [{"name": n, "calls": c} for n, c in unrecognized.most_common()]
    days_seen = sorted({d for days in tool_days.values() for d in days} | set())
    data = {
        "tools": tools,
        "unrecognized": unrec if show_all else unrec[:5],
        "by_kind": dict(by_kind.most_common()),
    }
    meta = {
        "log": str(LOG),
        "records": parsed,
        "sessions": len(sessions - {""}),
        "range": [days_seen[0], days_seen[-1]] if days_seen else None,
        "since": since,
        "until": until,
        "unrecognized_total": sum(unrecognized.values()),
        "unrecognized_distinct": len(unrecognized),
    }

    def human(d: dict, m: dict) -> None:
        rng = f" {m['range'][0]}→{m['range'][1]}" if m.get("range") else ""
        table = Table(title=f"utils tool usage{rng}", show_header=True, header_style="bold")
        table.add_column("tool", style="bold")
        table.add_column("calls", justify="right", style="cyan")
        table.add_column("days", justify="right")
        table.add_column("peak", justify="right", style="dim")
        table.add_column("class")
        cstyle = {"habitual": "green", "burst": "yellow", "one-off": "dim"}
        for t in d["tools"]:
            table.add_row(
                t["name"], str(t["calls"]), str(t["active_days"]),
                f"{t['peak_calls']}@{t['peak_day'][5:]}",
                f"[{cstyle.get(t['class'],'')}]{t['class']}[/]",
            )
        console.print(table)
        kinds = " · ".join(f"{k} {v}" for k, v in d["by_kind"].items())
        console.print(f"[dim]by kind:[/] {kinds}")
        if m["unrecognized_total"]:
            top_unrec = ", ".join(f"{u['name']}({u['calls']})" for u in d["unrecognized"])
            more = "" if len(d["unrecognized"]) == m["unrecognized_distinct"] else f" … +{m['unrecognized_distinct']-len(d['unrecognized'])} more (--all)"
            console.print(f"[dim]unrecognized:[/] {m['unrecognized_total']} calls / {m['unrecognized_distinct']} names — {top_unrec}{more}")

    emit(data, meta, human=human)


if __name__ == "__main__":
    app.command()(main)
    app()
