#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "tiktoken>=0.9.0",
# ]
# ///
"""Count tokens in a file or string (cl100k_base via tiktoken)."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

from enum import Enum
from pathlib import Path

import tiktoken
import typer
from rich import print


class TokenModel(str, Enum):
    OPUS = "opus"
    SONNET = "sonnet"
    HAIKU = "haiku"
    GPT_4 = "gpt-4"
    GPT_3_5 = "gpt-3.5"


_ENCODING_FOR = {
    TokenModel.OPUS: "cl100k_base",
    TokenModel.SONNET: "cl100k_base",
    TokenModel.HAIKU: "cl100k_base",
    TokenModel.GPT_4: "cl100k_base",
    TokenModel.GPT_3_5: "cl100k_base",
}


def main(
    target: str = typer.Argument(help="File path or raw text"),
    model: TokenModel = typer.Option(
        TokenModel.OPUS,
        "--model",
        help="Tokenizer model (Claude models use cl100k_base as an approximation)",
    ),
) -> None:
    """
    Count tokens in a file or string. Claude models don't have a public official
    tokenizer, so opus/sonnet/haiku use cl100k_base and are approximate.
    """

    path = Path(target)
    if path.is_file():
        content = path.read_text(encoding="utf-8", errors="replace")
        source = str(path)
    else:
        content = target
        source = "(stdin string)"

    enc = tiktoken.get_encoding(_ENCODING_FOR[model])
    count = len(enc.encode(content))

    approx = model in {TokenModel.OPUS, TokenModel.SONNET, TokenModel.HAIKU}
    suffix = " (approximate)" if approx else ""
    print(f"tokens: {count}{suffix}")
    print(f"chars:  {len(content)}")
    print(f"source: {source}")
    print(f"model:  {model.value}")


if __name__ == "__main__":
    typer.run(main)
