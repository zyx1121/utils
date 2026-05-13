#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
# ]
# ///
"""Hash a file or string with md5/sha1/sha256/sha512."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import hashlib
from enum import Enum
from pathlib import Path

import typer
from rich import print


class HashAlgo(str, Enum):
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    SHA512 = "sha512"


_CHUNK = 1024 * 1024


def main(
    target: str = typer.Argument(help="File path or string to hash"),
    algo: HashAlgo = typer.Option(HashAlgo.SHA256, "--algo", help="Hash algorithm"),
) -> None:
    """
    Hash a file or string. If the argument is an existing file path, the file
    contents are hashed; otherwise the raw string bytes are hashed.
    """

    h = hashlib.new(algo.value)
    path = Path(target)
    if path.is_file():
        with path.open("rb") as f:
            while chunk := f.read(_CHUNK):
                h.update(chunk)
        print(f"{h.hexdigest()}  {path}")
    else:
        h.update(target.encode("utf-8"))
        print(h.hexdigest())


if __name__ == "__main__":
    typer.run(main)
