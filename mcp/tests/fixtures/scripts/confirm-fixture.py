#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer"]
# ///
"""Minimal fixture atom — calls typer.confirm() directly, no bypass flag.

Exists to probe one thing: what happens when the MCP executor runs a
confirm-gated command with stdio[0] = "ignore" (ADR-0001's hard rule)?
click/typer's confirm() reads a line from stdin; on EOF (which "ignore"
produces immediately — the child sees a closed/empty stdin, not a blocking
TTY) it raises EOFError, which click wraps as Abort(). This script prints a
marker either way and always exits non-zero when not confirmed, so the test
asserts "fast abort" rather than "hang".
"""
import sys

import typer


def main() -> None:
    try:
        ok = typer.confirm("proceed?")
    except Exception as e:  # click.exceptions.Abort on EOF, or anything else
        print(f"abort: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    if ok:
        print("confirmed")
        sys.exit(0)
    print("declined", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    typer.run(main)
