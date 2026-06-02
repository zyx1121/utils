#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "pillow",
# ]
# ///
"""Pad an image to a target aspect ratio or exact canvas — letterbox, never crop."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

from pathlib import Path
from typing import Optional

import typer
from PIL import Image, ImageColor
from rich import print

# Encoders that keep an alpha channel — drives the default fill + flatten step.
_ALPHA_FORMATS = {".png", ".webp"}


def _parse_aspect(spec: str) -> float:
    """'16:9' | '16x9' | '1.777' -> width/height as a float."""
    s = spec.strip().lower().replace("x", ":")
    if ":" in s:
        w, _, h = s.partition(":")
        try:
            wf, hf = float(w), float(h)
        except ValueError:
            raise typer.BadParameter(f"bad aspect {spec!r} — use W:H like 16:9")
        if wf <= 0 or hf <= 0:
            raise typer.BadParameter(f"aspect parts must be positive: {spec!r}")
        return wf / hf
    try:
        v = float(s)
    except ValueError:
        raise typer.BadParameter(f"bad aspect {spec!r} — use W:H like 16:9 or a decimal")
    if v <= 0:
        raise typer.BadParameter(f"aspect must be positive: {spec!r}")
    return v


def _resolve_bg(color: Optional[str], suffix: str) -> tuple[int, int, int, int]:
    """Pick the fill as an RGBA tuple. Default: transparent when the output
    format keeps alpha (png/webp), else white — so a jpg never gets a black box
    behind it."""
    if color is None:
        return (0, 0, 0, 0) if suffix.lower() in _ALPHA_FORMATS else (255, 255, 255, 255)
    if color.strip().lower() in ("transparent", "none", "clear"):
        return (0, 0, 0, 0)
    try:
        rgb = ImageColor.getrgb(color)
    except ValueError:
        raise typer.BadParameter(
            f"unrecognized color {color!r} — try a name, #RRGGBB, or 'transparent'"
        )
    return rgb if len(rgb) == 4 else (*rgb, 255)


def main(
    path: Path = typer.Argument(help="Path to image file"),
    aspect: Optional[str] = typer.Option(
        None, "--aspect", "-a",
        help="Target aspect ratio W:H (e.g. 16:9). Pads the short side; the image is never cropped or scaled.",
    ),
    width: Optional[int] = typer.Option(
        None, "--width", help="Exact target canvas width in px (use with --height for a fixed-size canvas)."
    ),
    height: Optional[int] = typer.Option(
        None, "--height", help="Exact target canvas height in px."
    ),
    color: Optional[str] = typer.Option(
        None, "--color", "-c",
        help="Background fill: a name, #RRGGBB, or 'transparent'. Default: transparent for png/webp, white otherwise.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite if the padded file already exists"),
) -> None:
    """
    Pad an image so it fits a target shape without cropping — add bars of a
    background color around it. Use --aspect to hit a ratio (e.g. 16:9 so a
    center-crop container won't chop the edges) or --width/--height for an exact
    canvas. The original pixels are never scaled or cut.
    """
    if aspect is None and width is None and height is None:
        print("give me --aspect (e.g. 16:9) or --width/--height")
        raise typer.Exit(1)
    if aspect is not None and (width is not None or height is not None):
        print("--aspect and --width/--height are mutually exclusive")
        raise typer.Exit(1)
    if not path.is_file():
        print(f"Can't find {path} — did you typo it?")
        raise typer.Exit(1)

    bg = _resolve_bg(color, path.suffix)

    with Image.open(path) as img:
        src = img.convert("RGBA")
        sw, sh = src.size

        if aspect is not None:
            target = _parse_aspect(aspect)
            if sw / sh < target:          # too narrow -> widen the canvas
                cw, ch = max(sw, round(sh * target)), sh
            else:                         # too wide -> heighten the canvas
                cw, ch = sw, max(sh, round(sw / target))
        else:
            cw = width if width is not None else sw
            ch = height if height is not None else sh
            if cw < sw or ch < sh:
                print(
                    f"target {cw}x{ch} is smaller than {sw}x{sh} — padding can't shrink; "
                    "resize first with `utils image-resize`"
                )
                raise typer.Exit(1)

        output_path = path.with_name(f"{path.stem}_padded{path.suffix}")
        if output_path.exists() and not force:
            print(f"{output_path} already exists — pass --force to overwrite")
            raise typer.Exit(1)

        canvas = Image.new("RGBA", (cw, ch), bg)
        canvas.paste(src, ((cw - sw) // 2, (ch - sh) // 2), src)

        # Flatten onto the fill for formats that can't keep alpha (jpg).
        if path.suffix.lower() not in _ALPHA_FORMATS:
            flat = Image.new("RGB", canvas.size, bg[:3])
            flat.paste(canvas, mask=canvas.getchannel("A"))
            out, save_format = flat, "JPEG"
        else:
            out, save_format = canvas, None

        out.save(output_path, format=save_format)
        print(f"padded {sw}x{sh} -> {cw}x{ch} -> {output_path}")


if __name__ == "__main__":
    app = typer.Typer(rich_markup_mode=None, add_completion=False)
    app.command()(main)
    app()
