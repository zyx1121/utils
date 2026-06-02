#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "pillow"]
# ///
"""Image toolbox — convert / crop / colors / info."""
from __future__ import annotations

# Siblings shadow stdlib (json.py, uuid.py) — drop our dir off sys.path so deps resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from PIL import Image, ImageChops
from rich.console import Console

from _envelope import emit, fail  # noqa: E402

app = typer.Typer(
    rich_markup_mode=None,
    no_args_is_help=True,
    add_completion=False,
    help="Image toolbox — convert / crop / colors / info.",
)
console = Console(highlight=False)

# Above this longest-edge, quantize/Counter on the full raster is wasteful for a
# palette — downscale a thumbnail first; the dominant colors survive the shrink.
_COLOR_THUMB = 256


# ── shared helpers ───────────────────────────────────────────────
def _check_img(path: Path) -> Path:
    if not path.exists():
        fail(f"no such file: {path}", hint="check the path", code=2)
    if not path.is_file():
        fail(f"not a file: {path}", why="expected an image file, got a directory", code=2)
    return path


def _open(path: Path) -> Image.Image:
    try:
        return Image.open(path)
    except Exception as e:  # PIL raises UnidentifiedImageError, OSError, …
        fail(f"can't read image: {path}", why=str(e), hint="is it a real image file?", code=2)


def _out_path(src: Path, given: Optional[str], tag: str) -> Path:
    """Default output sits next to the source as <stem>.<tag><suffix> so the
    original is never clobbered — caller can always override with -o."""
    if given:
        return Path(given)
    return src.with_name(f"{src.stem}.{tag}{src.suffix}")


def _fmt_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{n}B"


def _hex(rgb: tuple[int, ...]) -> str:
    r, g, b = rgb[:3]
    return f"#{r:02x}{g:02x}{b:02x}"


def _trim_box(img: Image.Image) -> Optional[tuple[int, int, int, int]]:
    """Content bbox after stripping uniform border.

    RGBA/LA: trim by the alpha channel (getbbox on alpha drops transparent edge).
    Otherwise: difference the image against its top-left corner color and getbbox
    that — getbbox alone only finds the non-black/non-zero box, so a white margin
    needs the diff trick to register as 'empty'."""
    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")
        box = alpha.getbbox()
        if box is not None:
            return box
        # Fully transparent or fully opaque alpha → fall through to color trim.
    rgb = img.convert("RGB")
    corner = rgb.getpixel((0, 0))
    bg = Image.new("RGB", rgb.size, corner)
    diff = ImageChops.difference(rgb, bg)
    return diff.getbbox()


# ── convert ──────────────────────────────────────────────────────
class ImageFormat(str, Enum):
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"


def _convert_file(
    file_path: Path,
    from_format: ImageFormat,
    to_format: ImageFormat,
    force: bool,
    results: list[dict],
) -> None:
    if not str(file_path).lower().endswith(f".{from_format.value}"):
        results.append({"input": str(file_path), "status": "skipped", "reason": f"not a {from_format.value} file"})
        return
    if "_converted" in file_path.stem and not force:
        results.append({"input": str(file_path), "status": "skipped", "reason": "already converted"})
        return

    with _open(file_path) as img:
        output_path = file_path.with_name(f"{file_path.stem}_converted.{to_format.value}")
        if output_path.exists() and not force:
            results.append({"input": str(file_path), "status": "skipped", "reason": "output exists (use --force)"})
            return

        if from_format.value == "png" and to_format.value in ("jpg", "jpeg"):
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.getchannel("A"))
                img = background

        save_format = "JPEG" if to_format.value in ("jpg", "jpeg") else to_format.value
        img.save(output_path, format=save_format)
        results.append({"input": str(file_path), "output": str(output_path), "status": "converted"})


@app.command(help="Convert image(s) between png/jpg/jpeg/webp. Accepts a file or a directory.")
def convert(
    path: Path = typer.Argument(..., help="Image file or directory."),
    from_format: ImageFormat = typer.Option(..., "--from", help="Source format."),
    to_format: ImageFormat = typer.Option(..., "--to", help="Target format."),
    force: bool = typer.Option(False, "--force", help="Overwrite / re-convert even if a converted file exists."),
):
    if not path.exists():
        fail(f"no such path: {path}", hint="check the path", code=2)

    results: list[dict] = []
    if path.is_dir():
        for f in sorted(path.glob(f"*.{from_format.value}")):
            _convert_file(f, from_format, to_format, force, results)
    else:
        _convert_file(path, from_format, to_format, force, results)

    converted = [r for r in results if r["status"] == "converted"]

    def human(rows, _m):
        if not rows:
            console.print("[dim](nothing to convert)[/]")
            return
        for r in rows:
            if r["status"] == "converted":
                console.print(f"converted {r['input']} → [bold]{r['output']}[/]")
            else:
                console.print(f"[dim]skipped {r['input']}: {r['reason']}[/]")

    emit(
        results,
        {"from": from_format.value, "to": to_format.value, "converted": len(converted), "total": len(results)},
        human=human,
    )


# ── crop ─────────────────────────────────────────────────────────
@app.command(help="Crop an image: --trim strips a uniform border, --box L,T,R,B takes an exact pixel rect.")
def crop(
    file: Path = typer.Argument(..., help="Image path."),
    trim: bool = typer.Option(False, "--trim", "-t", help="Auto-crop a uniform border (transparency, or solid corner color)."),
    box: Optional[str] = typer.Option(None, "--box", help="Exact pixel rect L,T,R,B (left,top,right,bottom; right/bottom exclusive)."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output path (default: <stem>.cropped<suffix>)."),
):
    _check_img(file)
    if trim == bool(box):
        fail(
            "give exactly one of --trim or --box",
            why="--trim auto-detects the border; --box specifies the rect explicitly — they're mutually exclusive",
            hint="utils image crop x.png --trim   ·   utils image crop x.png --box 0,0,800,600",
            code=2,
        )

    img = _open(file)
    src_w, src_h = img.size

    if box:
        try:
            coords = tuple(int(p) for p in box.split(","))
        except ValueError:
            fail(f"bad --box: {box!r}", hint="use four integers: L,T,R,B e.g. 0,0,800,600", code=2)
        if len(coords) != 4:
            fail(f"--box needs 4 values, got {len(coords)}: {box!r}", hint="L,T,R,B e.g. 0,0,800,600", code=2)
        left, top, right, bottom = coords
        if right <= left or bottom <= top:
            fail(f"empty box {coords}", why="need right>left and bottom>top", code=2)
        if left < 0 or top < 0 or right > src_w or bottom > src_h:
            fail(f"box {coords} outside image", why=f"image is {src_w}x{src_h}", hint="clamp the rect to the image bounds", code=2)
        target = (left, top, right, bottom)
        mode = "box"
    else:
        target = _trim_box(img)
        if target is None:
            fail(
                "nothing to trim",
                why="the whole image is a single uniform color, so there's no content border to crop",
                hint="use --box for an explicit rect",
                code=2,
            )
        mode = "trim"

    cropped = img.crop(target)
    op = _out_path(file, out, "cropped")
    cropped.save(op)
    out_w, out_h = cropped.size

    emit(
        {
            "action": "crop",
            "mode": mode,
            "input": str(file),
            "output": str(op),
            "box": list(target),
            "from_size": [src_w, src_h],
            "to_size": [out_w, out_h],
        },
        human=lambda d, _m: console.print(
            f"cropped [{d['mode']}] {src_w}x{src_h} → [bold]{out_w}x{out_h}[/] "
            f"@ {tuple(d['box'])} → {op}"
        ),
    )


# ── colors ───────────────────────────────────────────────────────
@app.command(help="Top-N dominant colors as hex + share %. Large images are downscaled first.")
def colors(
    file: Path = typer.Argument(..., help="Image path."),
    num: int = typer.Option(5, "--num", "-n", help="How many top colors to return."),
):
    _check_img(file)
    if num < 1:
        fail(f"--num must be >= 1, got {num}", code=2)

    img = _open(file).convert("RGB")
    # Downscale big rasters: counting every pixel is wasteful and the dominant
    # palette is unchanged. thumbnail() keeps aspect, no-op when already small.
    work = img.copy()
    work.thumbnail((_COLOR_THUMB, _COLOR_THUMB))

    # getcolors is purpose-built (count, color) frequency; maxcolors high enough
    # for any 24-bit RGB so it never returns None. Beats Counter(getdata()) —
    # getdata() is deprecated in Pillow 14.
    pairs = work.getcolors(maxcolors=1 << 24) or []
    pairs.sort(key=lambda p: p[0], reverse=True)
    total = sum(c for c, _ in pairs)
    top = pairs[:num]
    data = [
        {"hex": _hex(rgb), "rgb": list(rgb), "ratio": round(c / total, 4), "percent": round(c / total * 100, 1)}
        for c, rgb in top
    ]

    def human(rows, m):
        for r in rows:
            bar = "█" * max(1, round(r["percent"] / 5))
            console.print(f"[on {r['hex']}]   [/] {r['hex']}  {r['percent']:>5.1f}%  [dim]{bar}[/]")
        console.print(f"[dim]{m['distinct']} distinct colors in {m['sampled']} sampled px[/]")

    emit(
        data,
        {"input": str(file), "distinct": len(pairs), "sampled": total, "requested": num},
        human=human,
    )


# ── info ─────────────────────────────────────────────────────────
@app.command(help="Dimensions, mode, format, and file size.")
def info(file: Path = typer.Argument(..., help="Image path.")):
    _check_img(file)
    size = file.stat().st_size
    img = _open(file)
    w, h = img.size
    data = {
        "file": str(file),
        "width": w,
        "height": h,
        "mode": img.mode,
        "format": img.format,
        "size_bytes": size,
    }
    emit(
        data,
        {"size": _fmt_size(size)},
        human=lambda d, m: console.print(
            f"[bold]{file.name}[/]  ·  {d['width']}×{d['height']}  ·  "
            f"{d['mode']}  ·  {d['format'] or '?'}  ·  {m['size']}"
        ),
    )


if __name__ == "__main__":
    app()
