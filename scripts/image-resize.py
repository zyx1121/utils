#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "pillow",
# ]
# ///
"""Resize an image with optional aspect-ratio preservation."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

from pathlib import Path
from typing import Optional

import typer
from PIL import Image
from rich import print


def main(
    path: Path = typer.Argument(help="Path to image file"),
    width: Optional[int] = typer.Option(None, "--width", help="Target width in pixels"),
    height: Optional[int] = typer.Option(None, "--height", help="Target height in pixels"),
    force: bool = typer.Option(False, "--force", help="Overwrite if the resized file already exists"),
) -> None:
    """
    Resize an image. Pass --width or --height (or both). With only one given,
    aspect ratio is preserved.
    """

    if width is None and height is None:
        print("give me at least one of --width or --height")
        raise typer.Exit(1)

    if not path.is_file():
        print(f"Can't find {path} — did you typo it?")
        raise typer.Exit(1)

    with Image.open(path) as img:
        src_w, src_h = img.size

        if width and height:
            new_w, new_h = width, height
        elif width:
            new_w = width
            new_h = max(1, round(src_h * (width / src_w)))
        else:
            new_h = height
            new_w = max(1, round(src_w * (height / src_h)))

        output_path = path.with_name(f"{path.stem}_resized{path.suffix}")
        if output_path.exists() and not force:
            print(f"{output_path} already exists — pass --force to overwrite")
            raise typer.Exit(1)

        resized = img.resize((new_w, new_h), Image.LANCZOS)
        resized.save(output_path)
        print(f"resized {src_w}x{src_h} -> {new_w}x{new_h} -> {output_path}")


if __name__ == "__main__":
    typer.run(main)
