#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich"]
# ///
"""Atomic Mail.app operations via AppleScript.

accounts / inbox / search / read / compose. No `send` op — `compose` opens a
visible draft window for the user to review and send manually.
"""
from __future__ import annotations

# Siblings shadow stdlib — drop our dir off sys.path so typer/rich resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import subprocess
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Atomic Mail.app ops — accounts / inbox / search / read / compose (no auto-send).",
)
console = Console()
err = Console(stderr=True, style="red")


def run_as(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if result.returncode != 0:
        err.print(f"mail: {result.stderr.strip() or 'AppleScript failed'}")
        raise typer.Exit(2)
    return result.stdout.rstrip("\n")


def escape_as(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ── accounts ─────────────────────────────────────────────────────
@app.command(help="List configured Mail accounts.")
def accounts():
    script = '''
tell application "Mail"
    set output to ""
    repeat with a in accounts
        set aName to name of a
        try
            set uName to user name of a
        on error
            set uName to ""
        end try
        try
            set addrs to email addresses of a
            set addrStr to ""
            repeat with x in addrs
                if addrStr is "" then
                    set addrStr to x as string
                else
                    set addrStr to addrStr & ", " & (x as string)
                end if
            end repeat
        on error
            set addrStr to ""
        end try
        set output to output & aName & "\t" & uName & "\t" & addrStr & "<<<EOL>>>"
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    table = Table(title="Mail accounts", show_header=True)
    table.add_column("name", style="bold")
    table.add_column("user", style="dim")
    table.add_column("addresses", style="cyan")
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        parts = line.split("\t")
        if len(parts) == 3:
            table.add_row(parts[0], parts[1], parts[2])
    console.print(table)


# ── inbox ────────────────────────────────────────────────────────
@app.command(help="Recent inbox messages (latest first, across all accounts).")
def inbox(
    unread: bool = typer.Option(False, "--unread", help="Only show unread messages."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows to show."),
):
    filt = "whose read status is false" if unread else ""
    script = f'''
tell application "Mail"
    set msgs to (messages of inbox {filt})
    set total to count of msgs
    if total is 0 then return ""
    if total > {limit} then set total to {limit}
    set output to ""
    repeat with i from 1 to total
        set m to item i of msgs
        try
            set s to subject of m
        on error
            set s to "(no subject)"
        end try
        try
            set snd to sender of m
        on error
            set snd to "(unknown)"
        end try
        try
            set d to (date received of m) as string
        on error
            set d to ""
        end try
        try
            set r to read status of m
        on error
            set r to true
        end try
        set output to output & s & "\t" & snd & "\t" & d & "\t" & r & "<<<EOL>>>"
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    rows = [l.strip() for l in raw.split("<<<EOL>>>") if l.strip()]
    if not rows:
        console.print("[dim](inbox empty or no unread)[/]")
        return
    table = Table(
        title=f"Inbox ({len(rows)}{' unread' if unread else ''})",
        show_header=True,
    )
    table.add_column("#", justify="right", style="cyan")
    table.add_column("subject", style="bold")
    table.add_column("from", style="dim")
    table.add_column("date", style="dim")
    table.add_column("•", style="yellow")
    for i, line in enumerate(rows, start=1):
        parts = line.split("\t")
        if len(parts) >= 4:
            subj, sndr, date, read = parts[0], parts[1], parts[2], parts[3]
            mark = "" if read.lower() == "true" else "●"
            table.add_row(str(i), subj, sndr, date, mark)
    console.print(table)


# ── search ───────────────────────────────────────────────────────
@app.command(help="Substring search across subject + sender, app-wide inbox.")
def search(
    query: str = typer.Argument(..., help="Substring to match in subject or sender."),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows."),
):
    needle = escape_as(query)
    script = f'''
tell application "Mail"
    set msgs to (messages of inbox whose (subject contains "{needle}") or (sender contains "{needle}"))
    set total to count of msgs
    if total is 0 then return ""
    if total > {limit} then set total to {limit}
    set output to ""
    repeat with i from 1 to total
        set m to item i of msgs
        try
            set s to subject of m
        on error
            set s to "(no subject)"
        end try
        try
            set snd to sender of m
        on error
            set snd to "(unknown)"
        end try
        try
            set d to (date received of m) as string
        on error
            set d to ""
        end try
        set output to output & s & "\t" & snd & "\t" & d & "<<<EOL>>>"
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    rows = [l.strip() for l in raw.split("<<<EOL>>>") if l.strip()]
    if not rows:
        console.print(f"[dim](no inbox messages matching '{query}')[/]")
        return
    table = Table(title=f"Search: '{query}'", show_header=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("subject", style="bold")
    table.add_column("from", style="dim")
    table.add_column("date", style="dim")
    for i, line in enumerate(rows, start=1):
        parts = line.split("\t")
        if len(parts) >= 3:
            table.add_row(str(i), parts[0], parts[1], parts[2])
    console.print(table)


# ── read ─────────────────────────────────────────────────────────
@app.command(help="Print the first inbox message whose subject matches (exact match preferred, falls back to contains).")
def read(
    subject: str = typer.Argument(..., help="Subject to match (exact, then contains-fallback)."),
):
    needle = escape_as(subject)
    script = f'''
tell application "Mail"
    set candidates to (messages of inbox whose subject is "{needle}")
    if (count of candidates) is 0 then
        set candidates to (messages of inbox whose subject contains "{needle}")
    end if
    if (count of candidates) is 0 then return ""
    set m to item 1 of candidates
    try
        set s to subject of m
    on error
        set s to "(no subject)"
    end try
    try
        set snd to sender of m
    on error
        set snd to "(unknown)"
    end try
    try
        set rcpt to ""
        repeat with r in to recipients of m
            if rcpt is "" then
                set rcpt to address of r
            else
                set rcpt to rcpt & ", " & (address of r)
            end if
        end repeat
    on error
        set rcpt to ""
    end try
    try
        set d to (date received of m) as string
    on error
        set d to ""
    end try
    try
        set body to content of m
    on error
        set body to "(no content)"
    end try
    return s & "<<<SEP>>>" & snd & "<<<SEP>>>" & rcpt & "<<<SEP>>>" & d & "<<<SEP>>>" & body
end tell
'''
    raw = run_as(script)
    if not raw:
        console.print(f"[dim](no inbox message with subject '{subject}')[/]")
        raise typer.Exit(1)
    parts = raw.split("<<<SEP>>>")
    if len(parts) != 5:
        err.print("mail: unexpected output format")
        raise typer.Exit(2)
    s, snd, rcpt, d, body = parts
    console.print(f"[bold cyan]Subject:[/] {s}")
    console.print(f"[bold cyan]From:[/]    {snd}")
    if rcpt:
        console.print(f"[bold cyan]To:[/]      {rcpt}")
    if d:
        console.print(f"[bold cyan]Date:[/]    {d}")
    console.print()
    console.print(body)


# ── compose ──────────────────────────────────────────────────────
@app.command(help="Open a draft compose window. User reviews and sends manually — no auto-send.")
def compose(
    to: List[str] = typer.Option(..., "--to", "-t", help="Recipient address (can repeat)."),
    subject: str = typer.Option(..., "--subject", "-s", help="Subject line."),
    body: str = typer.Option("", "--body", "-b", help="Body text. Use \\n for line breaks."),
    cc: List[str] = typer.Option([], "--cc", help="CC recipient (can repeat)."),
    bcc: List[str] = typer.Option([], "--bcc", help="BCC recipient (can repeat)."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Send-from account name (default: Mail.app default)."),
):
    # Convert literal \n into actual newlines so AppleScript-side returns are honored
    body_text = body.replace("\\n", "\n")

    def recipient_block(addr_list: List[str], kind: str) -> str:
        out = []
        for a in addr_list:
            out.append(
                f'make new {kind} with properties {{address:"{escape_as(a)}"}}'
            )
        return "\n        ".join(out)

    to_block = recipient_block(to, "to recipient")
    cc_block = recipient_block(cc, "cc recipient")
    bcc_block = recipient_block(bcc, "bcc recipient")

    # Escape the body for AppleScript string. Newlines are converted to & linefeed &.
    if "\n" in body_text:
        lines = body_text.split("\n")
        body_expr = '" & linefeed & "'.join(escape_as(p) for p in lines)
        body_as = f'"{body_expr}"'
    else:
        body_as = f'"{escape_as(body_text)}"'

    account_clause = (
        f'set sender of newMsg to "{escape_as(account)}"'
        if account else ""
    )

    script = f'''
tell application "Mail"
    set newMsg to make new outgoing message with properties {{subject:"{escape_as(subject)}", content:{body_as}, visible:true}}
    tell newMsg
        {to_block}
        {cc_block}
        {bcc_block}
    end tell
    {account_clause}
    activate
    return subject of newMsg
end tell
'''
    name_out = run_as(script)
    msg = f"draft opened: [bold]{name_out}[/] → {', '.join(to)}"
    if cc:
        msg += f" · cc {', '.join(cc)}"
    if bcc:
        msg += f" · bcc {', '.join(bcc)}"
    if account:
        msg += f" · from {account}"
    msg += "\n[dim](review the Mail window and click Send when ready — no auto-send)[/]"
    console.print(msg)


if __name__ == "__main__":
    app()
