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

import sys as _sys
from pathlib import Path as _Path

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

# Add ../lib for shared output helpers (envelope, fail).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import hashlib
from enum import Enum
from pathlib import Path

import typer

from _envelope import emit  # noqa: E402


class HashAlgo(str, Enum):
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    SHA512 = "sha512"


_CHUNK = 1024 * 1024


def _human(data: dict, _meta: dict) -> None:
    if data["source"] == "(inline string)":
        print(data["digest"])
    else:
        print(f"{data['digest']}  {data['source']}")


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
    hashed_file = path.is_file()
    if hashed_file:
        with path.open("rb") as f:
            while chunk := f.read(_CHUNK):
                h.update(chunk)
        source = str(path)
    else:
        h.update(target.encode("utf-8"))
        source = "(inline string)"

    emit(
        {"algorithm": algo.value, "digest": h.hexdigest(), "source": source},
        metadata={"chunk_size": _CHUNK if hashed_file else None},
        human=_human,
    )


if __name__ == "__main__":
    typer.run(main)
