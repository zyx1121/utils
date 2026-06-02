#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "pikepdf", "pymupdf"]
# ///
"""PDF toolbox — info / text / comments / compress / decrypt / merge / split / rotate."""
from __future__ import annotations

# Siblings shadow stdlib (json.py, uuid.py) — drop our dir off sys.path so deps resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import json
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional

import pikepdf
import pymupdf
import typer
from rich.console import Console

from _envelope import emit, fail  # noqa: E402

app = typer.Typer(
    rich_markup_mode=None,
    no_args_is_help=True,
    add_completion=False,
    help="PDF toolbox — info / text / comments / compress / decrypt / merge / split / rotate.",
)
console = Console(highlight=False)

# Annotation subtypes that mark up existing page text (carry quadpoints) vs.
# standalone notes (a sticky / typed comment that has no underlying text span).
MARKUP_TYPES = {"Highlight", "Underline", "StrikeOut", "Squiggly"}


# ── shared helpers ───────────────────────────────────────────────
def _check_pdf(path: Path) -> Path:
    if not path.exists():
        fail(f"no such file: {path}", hint="check the path", code=2)
    if path.suffix.lower() != ".pdf":
        fail(f"not a .pdf: {path}", why=f"suffix is {path.suffix!r}", code=2)
    return path


def _out_path(src: Path, given: Optional[str], tag: str) -> Path:
    """Default output sits next to the source as <stem>.<tag>.pdf so the original
    is never clobbered — caller can always override with -o."""
    if given:
        return Path(given)
    return src.with_name(f"{src.stem}.{tag}{src.suffix}")


def _parse_pages(spec: Optional[str], total: int) -> list[int]:
    """'1-3,5' (1-based, inclusive) → [0,1,2,4] (0-based). None / 'all' → every page."""
    if not spec or spec.strip().lower() == "all":
        return list(range(total))
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = (int(x) for x in part.split("-", 1))
                out.extend(range(a - 1, b))
            else:
                out.append(int(part) - 1)
        except ValueError:
            fail(f"bad page spec: {part!r}", hint="use forms like 1-3,5,7", code=2)
    bad = sorted({p + 1 for p in out if p < 0 or p >= total})
    if bad:
        fail(f"page(s) out of range: {bad}", why=f"document has {total} page(s)", code=2)
    seen: set[int] = set()
    return [p for p in out if not (p in seen or seen.add(p))]


def _fmt_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{n}B"


def _size(p: Path) -> int:
    return p.stat().st_size


def _markup_text(page, annot) -> str:
    """Text a markup annotation covers, via quadpoints — far more accurate than the
    annot's bounding rect (which over-spans on multi-line marks). Note-type annots
    have no quadpoints and return ''."""
    try:
        verts = annot.vertices
        if not verts:
            return ""
        parts = []
        for i in range(0, len(verts), 4):
            quad = verts[i:i + 4]
            if len(quad) == 4:
                parts.append(page.get_textbox(pymupdf.Quad(quad).rect).replace("\n", " "))
        return " ".join(t.strip() for t in parts if t.strip())
    except Exception:
        return ""


# ── info ─────────────────────────────────────────────────────────
@app.command(help="Page count, encryption status, metadata, file size.")
def info(file: Path = typer.Argument(..., help="PDF path.")):
    _check_pdf(file)
    size = _size(file)
    try:
        pdf = pikepdf.open(file)
    except pikepdf.PasswordError:
        emit(
            {"file": str(file), "encrypted": True, "readable": False, "size_bytes": size},
            {"size": _fmt_size(size)},
            human=lambda d, m: console.print(
                f"[bold]{file.name}[/] — [yellow]encrypted[/] (need password to read), {m['size']}\n"
                f"[dim]→ utils pdf decrypt {file} --password …[/]"),
        )
        return
    meta = {k.lstrip("/"): str(v) for k, v in dict(pdf.docinfo).items()} if pdf.docinfo else {}
    data = {
        "file": str(file),
        "pages": len(pdf.pages),
        "encrypted": pdf.is_encrypted,
        "pdf_version": pdf.pdf_version,
        "size_bytes": size,
        "metadata": meta,
    }

    def human(d, _m):
        console.print(f"[bold]{file.name}[/]  ·  {d['pages']} pages  ·  {_fmt_size(d['size_bytes'])}  ·  PDF {d['pdf_version']}  ·  {'encrypted' if d['encrypted'] else 'unencrypted'}")
        for k in ("Title", "Author", "Creator", "Producer", "CreationDate", "ModDate"):
            if k in d["metadata"]:
                console.print(f"  [dim]{k}:[/] {d['metadata'][k]}")

    emit(data, {"size": _fmt_size(size)}, human=human)


# ── text ─────────────────────────────────────────────────────────
@app.command(help="Extract plain text. --pages limits the range; -o writes a .txt instead of stdout.")
def text(
    file: Path = typer.Argument(..., help="PDF path."),
    pages: Optional[str] = typer.Option(None, "--pages", "-p", help="Page range, e.g. 1-3,5 (default: all)."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write text to this file instead of stdout."),
):
    _check_pdf(file)
    doc = pymupdf.open(file)
    idx = _parse_pages(pages, doc.page_count)
    chunks = [doc[i].get_text() for i in idx]
    body = "\n".join(chunks)
    if out:
        op = Path(out)
        op.write_text(body, encoding="utf-8")
        emit(
            {"action": "text", "input": str(file), "output": str(op), "pages": len(idx), "chars": len(body)},
            human=lambda d, _m: console.print(f"wrote {d['chars']} chars from {d['pages']} page(s) → [bold]{op}[/]"),
        )
        return
    emit(
        {"text": body, "pages": len(idx), "chars": len(body)},
        {"input": str(file)},
        human=lambda d, _m: console.print(d["text"]),
    )


# ── comments ─────────────────────────────────────────────────────
@app.command(help="Extract annotations / highlights / comments. Marked text is approximate — verify visually.")
def comments(
    file: Path = typer.Argument(..., help="PDF path."),
    pages: Optional[str] = typer.Option(None, "--pages", "-p", help="Page range, e.g. 1-3 (default: all)."),
    fields: Optional[str] = typer.Option(None, "--fields", "-f", help="Comma-separated keys to keep: page,type,author,content,marked_text — shrinks output."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write JSON to this file and emit only a summary (default: full list to stdout)."),
):
    _check_pdf(file)
    doc = pymupdf.open(file)
    idx = _parse_pages(pages, doc.page_count)
    rows = []
    for pno in idx:
        page = doc[pno]
        for a in page.annots() or []:
            subtype = a.type[1] if isinstance(a.type, (list, tuple)) else str(a.type)
            rows.append({
                "page": pno + 1,
                "type": subtype,
                "author": a.info.get("title") or None,
                "content": a.info.get("content") or None,
                "marked_text": _markup_text(page, a) if subtype in MARKUP_TYPES else None,
            })

    def human(d, m):
        if not d:
            console.print("[dim](no annotations)[/]")
            return
        for r in d:
            who = f" [dim]{r.get('author')}[/]" if r.get("author") else ""
            loc = f"[cyan]p{r['page']}[/] " if r.get("page") else ""
            typ = f"[yellow]{r['type']}[/]" if r.get("type") else ""
            console.print(f"{loc}{typ}{who}".strip())
            if r.get("marked_text"):
                console.print(f"  [dim]on:[/] {r['marked_text']}")
            if r.get("content"):
                for ln in r["content"].replace("\r", "\n").split("\n"):
                    if ln.strip():
                        console.print(f"  [bold]» {ln}[/]")
        if m.get("note"):
            console.print(f"\n[dim]{m['note']}[/]")

    note = "marked_text is extracted via quadpoints and may be imprecise; the reviewer's `content` is authoritative — verify against the visual markup."
    if fields:
        keep = [k.strip() for k in fields.split(",") if k.strip()]
        rows = [{k: r.get(k) for k in keep} for r in rows]
    meta = {"input": str(file), "count": len(rows), "note": note}

    if out:
        op = Path(out)
        op.write_text(json.dumps({"data": rows, "metadata": meta}, ensure_ascii=False, indent=2), encoding="utf-8")
        emit(
            {"action": "comments", "input": str(file), "output": str(op), "count": len(rows)},
            human=lambda d, _m: console.print(f"wrote {d['count']} annotation(s) → [bold]{op}[/]"),
        )
        return

    emit(rows, meta, human=human)


# ── compress ─────────────────────────────────────────────────────
class Level(str, Enum):
    screen = "screen"
    ebook = "ebook"
    printer = "printer"
    prepress = "prepress"


@app.command(help="Shrink via Ghostscript. --level screen|ebook|printer|prepress (default ebook).")
def compress(
    file: Path = typer.Argument(..., help="PDF path."),
    level: Level = typer.Option(Level.ebook, "--level", "-l", help="screen=smallest/72dpi … prepress=largest/300dpi+color."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output path (default: <name>.compressed.pdf)."),
):
    _check_pdf(file)
    gs = shutil.which("gs")
    if not gs:
        fail(
            "Ghostscript (gs) not found",
            why="gs is the only tool that meaningfully recompresses PDF images; a pure-Python pass would barely shrink and mislead",
            hint="brew install ghostscript",
        )
    op = _out_path(file, out, "compressed")
    before = _size(file)
    proc = subprocess.run(
        [gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4", f"-dPDFSETTINGS=/{level.value}",
         "-dNOPAUSE", "-dBATCH", "-dQUIET", f"-sOutputFile={op}", str(file)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not op.exists():
        fail("ghostscript failed", why=(proc.stderr or "").strip()[:300] or "non-zero exit", code=2)
    after = _size(op)
    ratio = after / before if before else 1.0
    emit(
        {"action": "compress", "input": str(file), "output": str(op), "level": level.value,
         "before_bytes": before, "after_bytes": after, "ratio": round(ratio, 3)},
        human=lambda d, _m: console.print(
            f"compressed [{d['level']}]: {_fmt_size(d['before_bytes'])} → [bold]{_fmt_size(d['after_bytes'])}[/] "
            f"({(1-d['ratio'])*100:.0f}% smaller) → {op}"),
    )


# ── decrypt ──────────────────────────────────────────────────────
@app.command(help="Remove password / encryption. --password for the open password if any.")
def decrypt(
    file: Path = typer.Argument(..., help="PDF path."),
    password: str = typer.Option("", "--password", "-P", help="Open password (omit if none)."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output path (default: <name>.decrypted.pdf)."),
):
    _check_pdf(file)
    try:
        pdf = pikepdf.open(file, password=password)
    except pikepdf.PasswordError:
        fail(
            "wrong or missing password",
            why="the file is encrypted and the supplied password didn't open it",
            hint="pass the open password with --password",
            code=2,
        )
    if not pdf.is_encrypted:
        fail(f"{file.name} is not encrypted", why="nothing to decrypt", hint="use it as-is", code=2)
    op = _out_path(file, out, "decrypted")
    pdf.save(op)  # saving without encryption params strips it
    emit(
        {"action": "decrypt", "input": str(file), "output": str(op)},
        human=lambda d, _m: console.print(f"decrypted → [bold]{op}[/]"),
    )


# ── merge ────────────────────────────────────────────────────────
@app.command(help="Concatenate PDFs in order. -o is required.")
def merge(
    inputs: list[Path] = typer.Argument(..., help="Input PDFs, in merge order."),
    out: str = typer.Option(..., "--out", "-o", help="Output path."),
):
    if len(inputs) < 2:
        fail("need at least 2 input PDFs", hint="utils pdf merge a.pdf b.pdf -o out.pdf", code=2)
    for f in inputs:
        _check_pdf(f)
    dst = pikepdf.Pdf.new()
    pages = 0
    for f in inputs:
        src = pikepdf.open(f)
        dst.pages.extend(src.pages)
        pages += len(src.pages)
    op = Path(out)
    dst.save(op)
    emit(
        {"action": "merge", "inputs": [str(f) for f in inputs], "output": str(op), "pages": pages},
        human=lambda d, _m: console.print(f"merged {len(d['inputs'])} files ({d['pages']} pages) → [bold]{op}[/]"),
    )


# ── split ────────────────────────────────────────────────────────
@app.command(help="Extract a page range into a new PDF. --pages is required, e.g. 1-3,5.")
def split(
    file: Path = typer.Argument(..., help="PDF path."),
    pages: str = typer.Option(..., "--pages", "-p", help="Pages to keep, e.g. 1-3,5 (1-based)."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output path (default: <name>.pages-<spec>.pdf)."),
):
    _check_pdf(file)
    src = pikepdf.open(file)
    idx = _parse_pages(pages, len(src.pages))
    dst = pikepdf.Pdf.new()
    for i in idx:
        dst.pages.append(src.pages[i])
    op = _out_path(file, out, f"pages-{pages.replace(',', '_')}")
    dst.save(op)
    emit(
        {"action": "split", "input": str(file), "output": str(op), "pages": [i + 1 for i in idx]},
        human=lambda d, _m: console.print(f"kept pages {pages} ({len(d['pages'])} of {len(src.pages)}) → [bold]{op}[/]"),
    )


# ── rotate ───────────────────────────────────────────────────────
@app.command(help="Rotate pages by a multiple of 90°. --pages selects which (default all).")
def rotate(
    file: Path = typer.Argument(..., help="PDF path."),
    deg: int = typer.Option(..., "--deg", "-d", help="Degrees clockwise: 90, 180, or 270 (negatives ok)."),
    pages: Optional[str] = typer.Option(None, "--pages", "-p", help="Pages to rotate, e.g. 1-3 (default: all)."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output path (default: <name>.rotated.pdf)."),
):
    _check_pdf(file)
    if deg % 90 != 0:
        fail(f"deg must be a multiple of 90, got {deg}", hint="try 90, 180, or 270", code=2)
    pdf = pikepdf.open(file)
    idx = _parse_pages(pages, len(pdf.pages))
    for i in idx:
        pdf.pages[i].rotate(deg, relative=True)
    op = _out_path(file, out, "rotated")
    pdf.save(op)
    emit(
        {"action": "rotate", "input": str(file), "output": str(op), "deg": deg, "pages": [i + 1 for i in idx]},
        human=lambda d, _m: console.print(f"rotated {len(d['pages'])} page(s) by {deg}° → [bold]{op}[/]"),
    )


# ── render ───────────────────────────────────────────────────────
@app.command(help="Render pages to PNG (e.g. to feed a vision model — sees layout/tables that text extraction loses).")
def render(
    file: Path = typer.Argument(..., help="PDF path."),
    pages: Optional[str] = typer.Option(None, "--pages", "-p", help="Pages to render, e.g. 1-3 (default: all)."),
    dpi: int = typer.Option(150, "--dpi", help="Resolution; 150 is a good default, 300 for fine detail."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output path for a single page; multi-page writes <name>.p<N>.png next to the source."),
):
    _check_pdf(file)
    doc = pymupdf.open(file)
    idx = _parse_pages(pages, doc.page_count)
    outs = []
    for i in idx:
        pix = doc[i].get_pixmap(dpi=dpi)
        op = Path(out) if (out and len(idx) == 1) else file.with_name(f"{file.stem}.p{i + 1}.png")
        pix.save(op)
        outs.append(str(op))
    emit(
        {"action": "render", "input": str(file), "outputs": outs, "pages": [i + 1 for i in idx], "dpi": dpi},
        human=lambda d, _m: console.print(
            f"rendered {len(d['outputs'])} page(s) @ {dpi}dpi → [bold]{outs[0] if len(outs) == 1 else file.stem + '.p*.png'}[/]"),
    )


if __name__ == "__main__":
    app()
