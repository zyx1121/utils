#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
# ]
# ///
"""Inspect, prettify, minify, validate, or extract values from JSON files."""
from __future__ import annotations

# This file is named json.py — kick our directory off sys.path so stdlib
# `json` (and typer's internals) resolve correctly instead of shadowing.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import re
from json import dumps, loads, JSONDecodeError
from pathlib import Path
from typing import Any, Optional

import typer
from rich import print


_TOKEN = re.compile(r"\.([^.\[\]]+)|\[(\d+)\]")


def walk_path(data: Any, path: str) -> Any:
    """Navigate dot/bracket paths like .data.users[0].name or data.users[0].name."""
    if not path.startswith(".") and not path.startswith("["):
        path = "." + path
    pos = 0
    current = data
    for m in _TOKEN.finditer(path):
        if m.start() != pos:
            raise KeyError(f"unexpected character at position {pos} in {path!r}")
        pos = m.end()
        key, idx = m.group(1), m.group(2)
        if key is not None:
            current = current[key]
        else:
            current = current[int(idx)]
    if pos != len(path):
        raise KeyError(f"couldn't parse remainder of {path!r}")
    return current


def main(
    path: Path = typer.Argument(help="Path to JSON file"),
    pretty: bool = typer.Option(True, "--pretty/--minify", help="Pretty-print or minify output"),
    extract: Optional[str] = typer.Option(
        None, "--extract", help="Extract a value using a jq-style path, e.g. .data.users[0].name"
    ),
    validate: bool = typer.Option(False, "--validate", help="Just check if the file parses"),
) -> None:
    """
    Inspect, prettify, minify, validate, and extract values from JSON files.
    """

    if not path.is_file():
        print(f"Can't find {path} — did you typo it?")
        raise typer.Exit(1)

    raw = path.read_text(encoding="utf-8")

    try:
        data = loads(raw)
    except JSONDecodeError as e:
        if validate:
            print(f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}")
            raise typer.Exit(1)
        print(f"Couldn't parse {path}: {e.msg} (line {e.lineno}, col {e.colno})")
        raise typer.Exit(1)

    if validate:
        print("OK")
        return

    if extract is not None:
        try:
            value = walk_path(data, extract)
        except (KeyError, IndexError, TypeError) as e:
            print(f"Path {extract} didn't lead anywhere: {e}")
            raise typer.Exit(1)
        if isinstance(value, (dict, list)):
            print(dumps(value, indent=2 if pretty else None, ensure_ascii=False))
        else:
            print(value)
        return

    if pretty:
        print(dumps(data, indent=2, ensure_ascii=False))
    else:
        print(dumps(data, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    typer.run(main)
