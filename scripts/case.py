#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
# ]
# ///
"""Convert text between camelCase, snake_case, kebab-case, PascalCase, CONSTANT_CASE."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import re
from enum import Enum
from typing import List

import typer
from rich import print


class CaseStyle(str, Enum):
    CAMEL = "camel"
    SNAKE = "snake"
    KEBAB = "kebab"
    PASCAL = "pascal"
    CONSTANT = "constant"


_SPLIT = re.compile(r"[\s_\-]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def tokenize(text: str) -> List[str]:
    """Split arbitrary input into word tokens, regardless of source case style."""
    parts = [p for p in _SPLIT.split(text.strip()) if p]
    tokens: List[str] = []
    for part in parts:
        tokens.extend(t for t in _CAMEL_BOUNDARY.split(part) if t)
    return tokens


def main(
    text: str = typer.Argument(help="Text to convert"),
    to: CaseStyle = typer.Option(..., "--to", help="Target case style"),
) -> None:
    """
    Convert text between camelCase, snake_case, kebab-case, PascalCase, CONSTANT_CASE.
    Input case is detected automatically.
    """

    words = tokenize(text)
    if not words:
        print("got nothing to work with — give me some letters")
        raise typer.Exit(1)

    lower = [w.lower() for w in words]

    if to is CaseStyle.SNAKE:
        print("_".join(lower))
    elif to is CaseStyle.KEBAB:
        print("-".join(lower))
    elif to is CaseStyle.CONSTANT:
        print("_".join(w.upper() for w in lower))
    elif to is CaseStyle.CAMEL:
        print(lower[0] + "".join(w.capitalize() for w in lower[1:]))
    elif to is CaseStyle.PASCAL:
        print("".join(w.capitalize() for w in lower))


if __name__ == "__main__":
    typer.run(main)
