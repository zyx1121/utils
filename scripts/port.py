#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "psutil",
# ]
# ///
"""Find which process is listening on a TCP/UDP port."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

from dataclasses import dataclass
from typing import List, Optional

import psutil
import typer
from rich import print


@dataclass
class Listener:
    pid: Optional[int]
    ip: str
    port: int


def collect_listeners(port_number: int) -> List[Listener]:
    """System-wide call needs root on macOS; fall back to a per-process scan."""
    try:
        results = []
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port_number and c.status == psutil.CONN_LISTEN:
                results.append(Listener(pid=c.pid, ip=c.laddr.ip, port=c.laddr.port))
        return results
    except (psutil.AccessDenied, PermissionError):
        pass

    results = []
    for proc in psutil.process_iter():
        try:
            for c in proc.connections(kind="inet"):
                if c.laddr and c.laddr.port == port_number and c.status == psutil.CONN_LISTEN:
                    results.append(Listener(pid=proc.pid, ip=c.laddr.ip, port=c.laddr.port))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return results


def main(
    port_number: int = typer.Argument(help="TCP/UDP port number to look up"),
) -> None:
    """
    Find which process is listening on a port.
    """

    if not 0 < port_number < 65536:
        print(f"{port_number} isn't a real port (must be 1-65535)")
        raise typer.Exit(1)

    listeners = collect_listeners(port_number)

    if not listeners:
        print(f"{port_number} looks quiet, nothing listening")
        return

    seen_pids = set()
    for entry in listeners:
        if entry.pid is None or entry.pid in seen_pids:
            continue
        seen_pids.add(entry.pid)
        try:
            proc = psutil.Process(entry.pid)
            name = proc.name()
            cmdline = " ".join(proc.cmdline()) or "(no cmdline)"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            name = "?"
            cmdline = "(access denied — try sudo)"
        print(f"pid:     {entry.pid}")
        print(f"name:    {name}")
        print(f"cmdline: {cmdline}")
        print(f"addr:    {entry.ip}:{entry.port}")
        print("---")


if __name__ == "__main__":
    typer.run(main)
