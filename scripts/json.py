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

import sys as _sys
from pathlib import Path as _Path

# This file is named json.py — drop our dir off sys.path so stdlib `json`
# (and typer's internals) resolve correctly instead of shadowing.
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

# Add ../lib for shared output helpers (envelope, fail, parse_host).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import re
from json import dumps, loads, JSONDecodeError
from pathlib import Path
from typing import Any, Optional

import typer

from _envelope import emit, fail  # noqa: E402


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


def _human_value(data: Any, _meta: dict) -> None:
    if isinstance(data, (dict, list)):
        print(dumps(data, indent=2, ensure_ascii=False))
    else:
        print(data)


def _human_minified(data: Any, _meta: dict) -> None:
    print(dumps(data, separators=(",", ":"), ensure_ascii=False))


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
        fail(
            f"file not found: {path}",
            why="path does not exist or is not a regular file",
            hint="check the path; or pipe the JSON in and write to a temp file first",
        )

    raw = path.read_text(encoding="utf-8")

    try:
        data = loads(raw)
    except JSONDecodeError as e:
        fail(
            f"invalid JSON in {path}",
            why=f"{e.msg} at line {e.lineno}, column {e.colno}",
            hint="fix the syntax error, then re-run; --validate just reports parse status",
        )

    if validate:
        emit({"valid": True}, {"path": str(path)})
        return

    if extract is not None:
        try:
            value = walk_path(data, extract)
        except (KeyError, IndexError, TypeError) as e:
            fail(
                f"path didn't lead anywhere: {extract}",
                why=str(e),
                hint=f"run `utils json {path}` (no --extract) to see the actual shape",
            )
        emit(value, {"path": str(path), "extract": extract}, human=_human_value)
        return

    if pretty:
        emit(data, {"path": str(path), "format": "pretty"}, human=_human_value)
    else:
        emit(data, {"path": str(path), "format": "minified"}, human=_human_minified)


if __name__ == "__main__":
    typer.run(main)
