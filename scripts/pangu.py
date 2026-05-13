#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "pangu",
# ]
# ///
"""Add spaces between CJK characters and ASCII (pangu rules)."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

from pathlib import Path

import pangu as pangu_lib
import typer
from rich import print


def main(
    target: str = typer.Argument(help="File path or raw text"),
    check: bool = typer.Option(
        False, "--check", help="Only report whether changes would be made (when target is a file)"
    ),
) -> None:
    """
    Add spaces between CJK characters and ASCII. Pass a file path to rewrite in place,
    or pass raw text to print the spaced version.
    """

    path = Path(target)
    if path.is_file():
        original = path.read_text(encoding="utf-8")
        spaced = pangu_lib.spacing_text(original)
        if check:
            if original == spaced:
                print(f"{path}: already tidy")
            else:
                diff = sum(1 for a, b in zip(original, spaced) if a != b) + abs(len(spaced) - len(original))
                print(f"{path}: would change (~{diff} chars different)")
            return
        if original == spaced:
            print(f"{path}: nothing to do")
            return
        path.write_text(spaced, encoding="utf-8")
        print(f"{path}: spaced")
        return

    print(pangu_lib.spacing_text(target))


if __name__ == "__main__":
    typer.run(main)
