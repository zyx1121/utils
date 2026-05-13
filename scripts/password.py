#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
# ]
# ///
"""Generate cryptographically random passwords."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import secrets
import string

import typer
from rich import print


def main(
    length: int = typer.Option(20, "--length", help="Length of each password"),
    count: int = typer.Option(1, "--count", help="How many passwords to generate"),
    symbols: bool = typer.Option(True, "--symbols/--no-symbols", help="Include punctuation"),
) -> None:
    """
    Generate cryptographically random passwords using the secrets module.
    """

    if length < 4:
        print("length under 4 is more of a vibe than a password — bump it up")
        raise typer.Exit(1)
    if count < 1:
        print("count needs to be at least 1")
        raise typer.Exit(1)

    alphabet = string.ascii_letters + string.digits
    if symbols:
        alphabet += string.punctuation

    for _ in range(count):
        print("".join(secrets.choice(alphabet) for _ in range(length)))


if __name__ == "__main__":
    typer.run(main)
