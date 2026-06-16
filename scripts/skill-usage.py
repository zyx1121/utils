#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich"]
# ///
"""Skill usage rollup — join ~/.claude.json skillUsage + the events log into per-skill adoption, recency, co-occurrence, and dormant detection."""
from __future__ import annotations

# Siblings shadow stdlib (json.py, …) — drop our dir off sys.path.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
# Add ../lib for shared output helpers (envelope, fail).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from _envelope import emit, fail  # noqa: E402

console = Console()

CLAUDE_JSON = Path.home() / ".claude.json"
EVENTS_DIR = Path.home() / ".kilo" / "data" / "events"
SKILLS_DIR = Path.home() / ".kilo" / "skills"
DORMANT_DAYS = 90
HOME = str(Path.home())


def personal_skills(skills_dir: Path) -> set[str]:
    if not skills_dir.exists():
        return set()
    return {d.name for d in skills_dir.iterdir() if (d / "SKILL.md").is_file()}


def canon(key: str, personal: set[str]) -> str:
    """Collapse a skillUsage/event key to one canonical name.

    `utils:method` and bare `method` are the SAME personal skill — the source
    moved from the utils plugin namespace to the kilo personal-skills symlink,
    so skillUsage carries both keys. External plugin skills (superpowers:*) are
    kept verbatim; they are genuinely different skills."""
    if key in personal:
        return key
    if ":" in key:
        ns, _, suffix = key.partition(":")
        if ns == "utils" and suffix in personal:
            return suffix
    return key


def load_skill_usage(personal: set[str]) -> dict:
    """canonical name -> {count, last_ms, aliases}. Native cross-session counter
    from ~/.claude.json (community-known, NOT an official API — treat as best
    effort; events log is the contract-stable fallback)."""
    try:
        raw = json.loads(CLAUDE_JSON.read_text(encoding="utf-8")).get("skillUsage", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for key, v in raw.items():
        if not isinstance(v, dict):
            continue
        c = canon(key, personal)
        rec = out.setdefault(c, {"count": 0, "last_ms": 0, "aliases": []})
        rec["count"] += int(v.get("usageCount", 0) or 0)
        rec["last_ms"] = max(rec["last_ms"], int(v.get("lastUsedAt", 0) or 0))
        rec["aliases"].append(key)
    return out


def load_events(events_dir: Path, personal: set[str]) -> list[tuple]:
    """(dt, session, cwd, skill, ok) for every Skill tool event. Hook-derived
    (events.py PostToolUse Skill|Task) — the contract-stable usage feed."""
    rows: list[tuple] = []
    if not events_dir.exists():
        return rows
    for f in sorted(events_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") != "tool" or r.get("tool") != "Skill":
                continue
            name = r.get("name")
            if not name:
                continue
            try:
                dt = datetime.fromisoformat(r["ts"])
            except (KeyError, ValueError):
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            rows.append((dt, r.get("session", ""), r.get("cwd", ""),
                         canon(name, personal), bool(r.get("ok", True))))
    return rows


def shorten(p: str) -> str:
    return ("~" + p[len(HOME):]) if p.startswith(HOME) else p


def fmt_ago(ms: int, now: datetime) -> tuple[str, int | None]:
    if not ms:
        return "never", None
    last = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    days = (now - last).days
    return ("today" if days == 0 else f"{days}d"), days


def main(
    days: int = typer.Option(30, "--days", "-d", help="Window for time-series metrics (invocations, launch-ok%, co-occurrence)."),
    personal_only: bool = typer.Option(False, "--personal", "-p", help="Only personal skills (~/.kilo/skills); hide external plugin skills."),
    events_dir: Path = typer.Option(EVENTS_DIR, "--events-dir", help="events.py jsonl directory."),
    skills_dir: Path = typer.Option(SKILLS_DIR, "--skills-dir", help="Personal skills directory (defines the canonical name set)."),
):
    """Per-skill usage rollup: all-time count (skillUsage) + windowed invocations
    (events log) + recency + launch-ok% + co-occurrence + dormant/never flags.

    Answers: is it used (all-time + window + last-used), what is used (which
    skills, per-cwd, co-occurrence), and a WEAK used-well proxy (launch-ok% —
    fires at launch not completion; real 'used well' needs an eval pass)."""
    personal = personal_skills(skills_dir)
    su = load_skill_usage(personal)
    ev = load_events(events_dir, personal)
    if not su and not ev:
        fail("no skill-usage data found",
             why=f"neither {CLAUDE_JSON} skillUsage nor {events_dir}/*.jsonl had usable records",
             hint="invoke a few skills first, or check the events.py PostToolUse hook is wired")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    win: dict[str, dict] = defaultdict(lambda: {"n": 0, "ok": 0, "cwd": Counter()})
    alltime_ev: dict[str, dict] = defaultdict(lambda: {"n": 0, "last": None})
    sess_skills: dict[str, set] = defaultdict(set)
    for dt, sess, cwd, skill, ok in ev:
        a = alltime_ev[skill]
        a["n"] += 1
        if a["last"] is None or dt > a["last"]:
            a["last"] = dt
        if dt >= cutoff:
            w = win[skill]
            w["n"] += 1
            w["ok"] += 1 if ok else 0
            if cwd:
                w["cwd"][cwd] += 1
            if sess:
                sess_skills[sess].add(skill)

    def last_ms(skill: str) -> int:
        ms = su.get(skill, {}).get("last_ms", 0)
        e = alltime_ev.get(skill, {}).get("last")
        if e:
            ms = max(ms, int(e.timestamp() * 1000))
        return ms

    universe = set(personal) | set(su) | set(alltime_ev)
    rows = []
    for s in universe:
        is_personal = s in personal
        if personal_only and not is_personal:
            continue
        w = win.get(s)
        wn = w["n"] if w else 0
        okpct = round(100 * w["ok"] / w["n"]) if (w and w["n"]) else None
        topcwd = w["cwd"].most_common(1)[0][0] if (w and w["cwd"]) else ""
        ms = last_ms(s)
        ago, ago_days = fmt_ago(ms, now)
        rows.append({
            "skill": s,
            "personal": is_personal,
            "all_time": su.get(s, {}).get("count", 0),
            "window": wn,
            "launch_ok_pct": okpct,
            "last_used": ago,
            "last_days": ago_days,
            "top_cwd": shorten(topcwd) if topcwd else "",
            "aliases": su.get(s, {}).get("aliases", []),
        })
    rows.sort(key=lambda r: (-r["window"], -r["all_time"], r["skill"]))

    # Dormant / never-used personal skills (archive candidates).
    dormant = []
    for s in sorted(personal):
        ms = last_ms(s)
        ago, ago_days = fmt_ago(ms, now)
        if ago_days is None:
            dormant.append({"skill": s, "last_used": "never", "last_days": None})
        elif ago_days > DORMANT_DAYS:
            dormant.append({"skill": s, "last_used": ago, "last_days": ago_days})

    # Co-occurrence within the window (same session → pair).
    pairs: Counter = Counter()
    for sk in sess_skills.values():
        for a, b in combinations(sorted(sk), 2):
            pairs[(a, b)] += 1
    co = [{"pair": [a, b], "sessions": n} for (a, b), n in pairs.most_common(15) if n >= 2]

    data = {
        "window_days": days,
        "skills": rows,
        "dormant": dormant,
        "co_occurrence": co,
        "totals": {
            "skills_seen": len(rows),
            "window_invocations": sum(r["window"] for r in rows),
            "dormant_personal": len(dormant),
        },
    }

    def human(d, _meta):
        t = Table(title=f"Skill usage · last {days}d (all-time = ~/.claude.json skillUsage)", show_header=True, header_style="bold")
        t.add_column("skill", style="bold")
        t.add_column("", width=1)  # personal marker
        t.add_column("all-time", justify="right", style="cyan")
        t.add_column(f"{days}d", justify="right", style="green")
        t.add_column("ok%", justify="right", style="dim")
        t.add_column("last", justify="right")
        t.add_column("top cwd", style="dim")
        shown = [r for r in d["skills"] if r["window"] or r["all_time"]]
        for r in shown:
            t.add_row(
                r["skill"],
                "★" if r["personal"] else "",
                str(r["all_time"]) if r["all_time"] else "·",
                str(r["window"]) if r["window"] else "·",
                f"{r['launch_ok_pct']}" if r["launch_ok_pct"] is not None else "·",
                r["last_used"],
                r["top_cwd"],
            )
        console.print(t)

        if d["dormant"]:
            dt = Table(title="Dormant / never-used personal skills (archive candidates)", show_header=True, header_style="bold yellow")
            dt.add_column("skill", style="yellow")
            dt.add_column("last used", justify="right")
            for r in d["dormant"]:
                dt.add_row(r["skill"], r["last_used"])
            console.print(dt)

        if d["co_occurrence"]:
            ct = Table(title=f"Co-occurrence · same session, last {days}d", show_header=True, header_style="bold")
            ct.add_column("skill pair")
            ct.add_column("sessions", justify="right", style="cyan")
            for r in d["co_occurrence"]:
                ct.add_row(" + ".join(r["pair"]), str(r["sessions"]))
            console.print(ct)

        console.print(
            f"\n[dim]★ = personal skill · ok% = LAUNCH success only (not end-to-end) · "
            f"all-time may undercount post-rename · {d['totals']['window_invocations']} invocations in {days}d[/]"
        )

    emit(data, {"window_days": days, "skills_seen": len(rows),
                "dormant_personal": len(dormant)}, human=human)


if __name__ == "__main__":
    app = typer.Typer(rich_markup_mode=None, add_completion=False)
    app.command()(main)
    app()
