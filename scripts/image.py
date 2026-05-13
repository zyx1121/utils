#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "pillow",
# ]
# ///
"""Convert images between png/jpg/jpeg/webp."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

from enum import Enum
from pathlib import Path

import typer
from PIL import Image
from rich import print


class ImageFormat(str, Enum):
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"


def convert_file(
    file_path: Path,
    from_format: ImageFormat,
    to_format: ImageFormat,
    force: bool = False,
) -> None:
    try:
        if not str(file_path).lower().endswith(f".{from_format.value}"):
            print(f"Skipping {file_path}: Not a {from_format} file")
            return

        if "_converted" in file_path.stem and not force:
            print(f"Skipping {file_path}: Already converted")
            return

        with Image.open(file_path) as img:
            new_stem = f"{file_path.stem}_converted"
            output_path = file_path.with_name(f"{new_stem}.{to_format.value}")

            if output_path.exists() and not force:
                print(f"Skipping {file_path}: Output file already exists")
                return

            if from_format.value == "png" and to_format.value in ["jpg", "jpeg"]:
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ["RGBA", "LA"]:
                    background.paste(img, mask=img.getchannel("A"))
                    img = background

            save_format = (
                "JPEG" if to_format.value in ["jpg", "jpeg"] else to_format.value
            )
            img.save(output_path, format=save_format)
            print(f"Converted {file_path} to {output_path}")

    except Exception as e:
        print(f"Error converting {file_path}: {str(e)}")


def convert_directory(
    directory: Path,
    from_format: ImageFormat,
    to_format: ImageFormat,
    force: bool = False,
) -> None:
    for file_path in directory.glob(f"*.{from_format.value}"):
        convert_file(file_path, from_format, to_format, force)


def main(
    path: Path = typer.Argument(help="Path to image file or directory"),
    from_format: ImageFormat = typer.Option(..., "--from", help="Source image format"),
    to_format: ImageFormat = typer.Option(..., "--to", help="Target image format"),
    force: bool = typer.Option(
        False, "--force", help="Force convert even if converted file exists"
    ),
) -> None:
    """
    Convert images from one format to another.
    Supports local files, directories and URLs.
    """

    if path.is_dir():
        convert_directory(path, from_format, to_format, force)
        return

    if path.is_file():
        convert_file(path, from_format, to_format, force)
        return

    print(f"Error path {path} does not exist!")


if __name__ == "__main__":
    typer.run(main)
