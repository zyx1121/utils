#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
# ]
# ///
"""Generate UUIDs (v4 random or v7 timestamp-ordered)."""
from __future__ import annotations

# This file is named uuid.py — kick our directory off sys.path so stdlib
# `uuid` (and typer's internal `from uuid import UUID`) resolve correctly.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import os
import time
import uuid as stdlib_uuid
from enum import Enum

import typer
from rich import print


class UUIDVersion(str, Enum):
    V4 = "4"
    V7 = "7"


def uuid7() -> str:
    """Manual UUIDv7: 48 bits ms timestamp, 4 bits version, 12 bits rand_a,
    2 bits variant, 62 bits rand_b. Returns canonical 8-4-4-4-12 hex form."""
    ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bits
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = (rand >> 64) & 0xFFF  # 12 bits
    rand_b = rand & 0x3FFFFFFFFFFFFFFF  # 62 bits

    value = (ts_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    hex_str = f"{value:032x}"
    return f"{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"


def main(
    count: int = typer.Option(1, "--count", help="How many UUIDs to generate"),
    version: UUIDVersion = typer.Option(UUIDVersion.V4, "--version", help="UUID version (4 or 7)"),
) -> None:
    """
    Generate UUIDs. v4 is random; v7 is timestamp-ordered (good for DB keys).
    """

    if count < 1:
        print("count needs to be at least 1, otherwise why are you here")
        raise typer.Exit(1)

    for _ in range(count):
        if version is UUIDVersion.V4:
            print(str(stdlib_uuid.uuid4()))
        else:
            print(uuid7())


if __name__ == "__main__":
    typer.run(main)
