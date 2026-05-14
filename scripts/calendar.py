#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich"]
# ///
"""Atomic Calendar.app operations via AppleScript.

show-cals / list / add / search / delete. Dates are built locale-independently
to avoid `date "..."` string parsing failing on non-English Macs.
"""
from __future__ import annotations

# Siblings shadow stdlib — drop our dir off sys.path so typer/rich resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import subprocess
from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Atomic Calendar.app ops — show-cals / list / add / search / delete.",
)
console = Console()
err = Console(stderr=True, style="red")


def run_as(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, check=False, timeout=60,
    )
    if result.returncode != 0:
        err.print(f"calendar: {result.stderr.strip() or 'AppleScript failed'}")
        raise typer.Exit(2)
    return result.stdout.rstrip("\n")


def escape_as(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def parse_when(when: str) -> datetime:
    """Accept ISO date/datetime, HH:MM (today), 'today', 'tomorrow', 'next week'."""
    s = when.strip().lower()
    now = datetime.now().replace(second=0, microsecond=0)
    if s == "now":
        return now
    if s == "today":
        return now.replace(hour=0, minute=0)
    if s == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=9, minute=0)
    if s in ("next week", "next-week"):
        return (now + timedelta(days=7)).replace(hour=9, minute=0)
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M"):
        try:
            dt = datetime.strptime(when.strip(), fmt)
            if fmt == "%H:%M":
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt
        except ValueError:
            continue
    err.print(f"calendar: can't parse '{when}' — try YYYY-MM-DD, YYYY-MM-DDTHH:MM, 'today', 'tomorrow', 'now'")
    raise typer.Exit(2)


def as_date_block(dt: datetime, var: str = "theDate") -> str:
    return (
        f'set {var} to current date\n'
        f'set year of {var} to {dt.year}\n'
        f'set month of {var} to {dt.month}\n'
        f'set day of {var} to {dt.day}\n'
        f'set hours of {var} to {dt.hour}\n'
        f'set minutes of {var} to {dt.minute}\n'
        f'set seconds of {var} to 0'
    )


def cal_clause(cal: Optional[str]) -> str:
    return f'calendar "{escape_as(cal)}"' if cal else 'first calendar whose writable is true'


# ── show-cals ────────────────────────────────────────────────────
@app.command(name="show-cals", help="List all calendars with writability.")
def show_cals():
    script = '''
tell application "Calendar"
    set output to ""
    repeat with c in calendars
        set w to writable of c
        set output to output & (name of c) & "\t" & w & "<<<EOL>>>"
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    table = Table(title="Calendars", show_header=True)
    table.add_column("name", style="bold")
    table.add_column("writable", style="green")
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        parts = line.split("\t")
        if len(parts) == 2:
            name, w = parts
            mark = "✓" if w.lower() == "true" else "—"
            table.add_row(name, mark)
    console.print(table)


# ── list ─────────────────────────────────────────────────────────
@app.command(name="list", help="List events in a date range. Default range: today → +7 days.")
def list_cmd(
    cal: Optional[str] = typer.Option(None, "--cal", "-c", help="Filter to a single calendar (default: all)."),
    from_: Optional[str] = typer.Option(None, "--from", help="Range start (default: today 00:00)."),
    to: Optional[str] = typer.Option(None, "--to", help="Range end (default: today + 7 days)."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Cap rows shown."),
):
    start_dt = parse_when(from_) if from_ else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_when(to) if to else start_dt + timedelta(days=7)

    cal_filter = f'calendar "{escape_as(cal)}"' if cal else "every calendar"
    script = f'''
tell application "Calendar"
    {as_date_block(start_dt, "rangeStart")}
    {as_date_block(end_dt, "rangeEnd")}
    set output to ""
    set cals to {cal_filter}
    repeat with c in cals
        set evts to (events of c whose start date is greater than or equal to rangeStart and start date is less than or equal to rangeEnd)
        repeat with e in evts
            set esum to summary of e
            set estart to (start date of e) as string
            set ecal to name of c
            try
                set eloc to location of e
                if eloc is missing value then set eloc to ""
            on error
                set eloc to ""
            end try
            set output to output & ecal & "\t" & estart & "\t" & esum & "\t" & eloc & "<<<EOL>>>"
        end repeat
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    rows = [l.strip() for l in raw.split("<<<EOL>>>") if l.strip()]
    if limit:
        rows = rows[:limit]
    if not rows:
        console.print(f"[dim](no events in {start_dt.strftime('%Y-%m-%d')} – {end_dt.strftime('%Y-%m-%d')})[/]")
        return
    table = Table(title=f"Events {start_dt.strftime('%Y-%m-%d')} – {end_dt.strftime('%Y-%m-%d')}", show_header=True)
    table.add_column("calendar", style="cyan")
    table.add_column("start", style="dim")
    table.add_column("summary", style="bold")
    table.add_column("location", style="dim")
    for line in rows:
        parts = line.split("\t")
        if len(parts) >= 3:
            cal_name = parts[0]
            start = parts[1]
            summary = parts[2]
            loc = parts[3] if len(parts) > 3 else ""
            table.add_row(cal_name, start, summary, loc or "—")
    console.print(table)


# ── add ──────────────────────────────────────────────────────────
@app.command(help="Add a new event. --at and --duration set the time window.")
def add(
    summary: str = typer.Argument(..., help="Event title."),
    at: str = typer.Option(..., "--at", "-a", help="Start time (YYYY-MM-DDTHH:MM, 'tomorrow', etc.)."),
    duration: int = typer.Option(60, "--duration", "-d", help="Duration in minutes (default 60)."),
    cal: Optional[str] = typer.Option(None, "--cal", "-c", help="Calendar name (default: first writable)."),
    location: Optional[str] = typer.Option(None, "--location", "-L", help="Location."),
    notes: Optional[str] = typer.Option(None, "--notes", "-N", help="Description / notes."),
):
    start_dt = parse_when(at)
    end_dt = start_dt + timedelta(minutes=duration)

    props = [f'summary:"{escape_as(summary)}"', "start date:startDt", "end date:endDt"]
    if location:
        props.append(f'location:"{escape_as(location)}"')
    if notes:
        props.append(f'description:"{escape_as(notes)}"')
    props_str = ", ".join(props)

    script = f'''
tell application "Calendar"
    {as_date_block(start_dt, "startDt")}
    {as_date_block(end_dt, "endDt")}
    tell {cal_clause(cal)}
        set newE to make new event with properties {{{props_str}}}
        return summary of newE
    end tell
end tell
'''
    name_out = run_as(script)
    msg = f"added: [bold]{name_out}[/] · {start_dt.strftime('%Y-%m-%d %H:%M')} → {end_dt.strftime('%H:%M')}"
    if cal:
        msg += f" · {cal}"
    if location:
        msg += f" @ {location}"
    console.print(msg)


# ── search ───────────────────────────────────────────────────────
@app.command(help="Search event summaries within a date range (default: today → +30 days).")
def search(
    query: str = typer.Argument(..., help="Search text (case-insensitive substring of summary)."),
    cal: Optional[str] = typer.Option(None, "--cal", "-c", help="Filter to one calendar (default: all)."),
    from_: Optional[str] = typer.Option(None, "--from", help="Range start (default: today)."),
    to: Optional[str] = typer.Option(None, "--to", help="Range end (default: today + 30 days)."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Cap rows shown."),
):
    start_dt = parse_when(from_) if from_ else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_when(to) if to else start_dt + timedelta(days=30)

    cal_filter = f'calendar "{escape_as(cal)}"' if cal else "every calendar"
    needle = escape_as(query)
    script = f'''
tell application "Calendar"
    {as_date_block(start_dt, "rangeStart")}
    {as_date_block(end_dt, "rangeEnd")}
    set output to ""
    set cals to {cal_filter}
    repeat with c in cals
        set evts to (events of c whose start date is greater than or equal to rangeStart and start date is less than or equal to rangeEnd and summary contains "{needle}")
        repeat with e in evts
            set esum to summary of e
            set estart to (start date of e) as string
            set ecal to name of c
            set output to output & ecal & "\t" & estart & "\t" & esum & "<<<EOL>>>"
        end repeat
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    rows = [l.strip() for l in raw.split("<<<EOL>>>") if l.strip()]
    if limit:
        rows = rows[:limit]
    if not rows:
        console.print(f"[dim](no events matching '{query}')[/]")
        return
    table = Table(title=f"Search: '{query}'", show_header=True)
    table.add_column("calendar", style="cyan")
    table.add_column("start", style="dim")
    table.add_column("summary", style="bold")
    for line in rows:
        parts = line.split("\t")
        if len(parts) >= 3:
            table.add_row(parts[0], parts[1], parts[2])
    console.print(table)


# ── delete ───────────────────────────────────────────────────────
@app.command(help="Delete the first event matching <summary> in the date range. Requires --cal for safety.")
def delete(
    summary: str = typer.Argument(..., help="Event summary (exact match)."),
    cal: str = typer.Option(..., "--cal", "-c", help="Calendar to search (required, no fuzzy delete)."),
    from_: Optional[str] = typer.Option(None, "--from", help="Range start (default: today)."),
    to: Optional[str] = typer.Option(None, "--to", help="Range end (default: today + 30 days)."),
):
    start_dt = parse_when(from_) if from_ else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_when(to) if to else start_dt + timedelta(days=30)

    script = f'''
tell application "Calendar"
    {as_date_block(start_dt, "rangeStart")}
    {as_date_block(end_dt, "rangeEnd")}
    tell calendar "{escape_as(cal)}"
        set target to first event whose start date is greater than or equal to rangeStart and start date is less than or equal to rangeEnd and summary is "{escape_as(summary)}"
        set foundName to summary of target
        delete target
        return foundName
    end tell
end tell
'''
    name_out = run_as(script)
    console.print(f"deleted: [bold]{name_out}[/] from [cyan]{cal}[/]")


if __name__ == "__main__":
    app()
