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

import sys as _sys
from pathlib import Path as _Path

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

# Add ../lib for shared output helpers (envelope, fail).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

from enum import Enum
from pathlib import Path

import tiktoken
import typer

from _envelope import emit, fail  # noqa: E402


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


def _human(data: dict, _meta: dict) -> None:
    suffix = " (approximate)" if data["approximate"] else ""
    print(f"tokens: {data['tokens']}{suffix}")
    print(f"chars:  {data['chars']}")
    print(f"source: {data['source']}")
    print(f"model:  {data['model']}")


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
    is_file = path.is_file()
    if is_file:
        content = path.read_text(encoding="utf-8", errors="replace")
    else:
        content = target

    try:
        enc = tiktoken.get_encoding(_ENCODING_FOR[model])
    except Exception as e:
        fail(
            f"couldn't load tokenizer for {model.value}",
            why=str(e),
            hint="check network access — tiktoken downloads encoding files on first use",
        )

    count = len(enc.encode(content))

    emit(
        {
            "tokens": count,
            "chars": len(content),
            "source": str(path) if is_file else "(inline string)",
            "model": model.value,
            "encoding": _ENCODING_FOR[model],
            "approximate": model in {TokenModel.OPUS, TokenModel.SONNET, TokenModel.HAIKU},
        },
        human=_human,
    )


if __name__ == "__main__":
    typer.run(main)
