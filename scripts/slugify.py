#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "python-slugify",
# ]
# ///
"""Convert text into a URL-safe slug (unicode aware)."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import typer
from rich import print
from slugify import slugify as _slugify


def main(
    text: str = typer.Argument(help="Text to slugify"),
) -> None:
    """
    Convert text into a URL-safe slug. Handles unicode (including CJK transliteration).
    """

    print(_slugify(text))


if __name__ == "__main__":
    typer.run(main)
