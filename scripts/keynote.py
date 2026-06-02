#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich"]
# ///
"""Atomic Keynote operations via AppleScript.

Building blocks for working with Keynote presentations — open, list, edit,
export. Skills compose these into full slide-deck workflows.
"""
from __future__ import annotations

# Siblings in this directory shadow stdlib modules (json.py, uuid.py). Drop
# our dir off sys.path so typer/rich resolve those from stdlib instead.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
# Add ../lib for shared output helpers (envelope, fail).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from _envelope import emit, fail  # noqa: E402

app = typer.Typer(
    rich_markup_mode=None,
    no_args_is_help=True,
    add_completion=False,
    help="Atomic Keynote ops — open / list / add slide / set text / export / …",
)
console = Console()
warn = Console(stderr=True, style="yellow")


def run_as(script: str) -> str:
    """Run AppleScript, return stdout, emit a failure envelope + exit on error."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or "AppleScript failed", code=2)
    return result.stdout.rstrip("\n")


def escape_as(s: str) -> str:
    """Escape a string for safe AppleScript literal use."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def prepare_text(s: str) -> str:
    """Build an AppleScript string-concat expression, with `linefeed` between
    lines. Output is meant to be wrapped in "..." by the caller — e.g.
    multi-line ``World\\nLine 2`` becomes ``World" & linefeed & "Line 2`` which,
    once wrapped, reads as ``"World" & linefeed & "Line 2"``. Split first, then
    escape each piece — otherwise backslash escaping breaks the substitution.

    Why `linefeed` (\\n) over `return` (\\r): Keynote's default body placeholder
    renders a stray backslash character before `return`-separated breaks on some
    layouts (e.g. two-column L5). `linefeed` works identically on regular shapes
    and doesn't leak the artifact. It's the safe default."""
    # Accept both literal `\n` (two chars from a shell arg) and real newlines.
    s = s.replace("\\n", "\n")
    return '" & linefeed & "'.join(escape_as(p) for p in s.split("\n"))


def absolute(p: Path) -> str:
    return str(p.expanduser().resolve())


# ── new ──────────────────────────────────────────────────────────
@app.command(help="Create a new blank Keynote presentation.")
def new(
    path: Optional[Path] = typer.Argument(None, help="Save path (.key). Omit to keep unsaved."),
    theme: Optional[str] = typer.Option(None, "--theme", "-t", help='Theme name (e.g. "Black"). Default theme if omitted.'),
):
    save_clause = f'save newDoc in POSIX file "{escape_as(absolute(path))}"' if path else ""
    theme_clause = f'set document theme of newDoc to theme "{escape_as(theme)}"' if theme else ""
    script = f'''
tell application "Keynote"
    activate
    set newDoc to make new document
    {theme_clause}
    {save_clause}
    return name of newDoc
end tell
'''
    name = run_as(script)
    abs_path = absolute(path) if path else None
    emit(
        {"action": "new", "name": name, "path": abs_path},
        human=lambda d, _m: console.print(
            f"created: [bold]{d['name']}[/]" + (f" → {d['path']}" if d["path"] else "")
        ),
    )


# ── open ─────────────────────────────────────────────────────────
@app.command(
    name="open",
    help=(
        "Open a Keynote (.key) or PowerPoint (.pptx) file. "
        "Use --save-to when starting from a template — Keynote autosaves "
        "continuously and `save in <path>` is export-only (it does NOT "
        "rebind the document), so without --save-to every edit writes back "
        "to the original file."
    ),
)
def open_cmd(
    path: Path = typer.Argument(..., help="Path to file"),
    save_to: Optional[Path] = typer.Option(
        None,
        "--save-to",
        help=(
            "Filesystem-copy the source to this path first, then open the copy. "
            "Use this when starting from a template — autosave will lock to "
            "the new path instead of the template. Parent dirs are created."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite --save-to destination if it already exists.",
    ),
):
    abs_src = absolute(path)
    if not Path(abs_src).exists():
        fail(f"file not found: {abs_src}", code=2)

    copied_to = None
    warning = None
    if save_to is not None:
        abs_dst = absolute(save_to)
        dst = Path(abs_dst)
        if dst.exists() and not force:
            fail(
                f"destination already exists: {abs_dst}",
                hint="re-run with --force to overwrite",
                code=2,
            )
        dst.parent.mkdir(parents=True, exist_ok=True)
        # .key on modern macOS is a single Zip file, but legacy / iCloud copies
        # are sometimes folder bundles — handle both shapes.
        if Path(abs_src).is_dir():
            if dst.exists():
                shutil.rmtree(abs_dst)
            shutil.copytree(abs_src, abs_dst)
        else:
            shutil.copy2(abs_src, abs_dst)
        open_path = abs_dst
        copied_to = abs_dst
    else:
        open_path = abs_src
        warning = (
            f"opened in place — autosave writes back to {abs_src}. "
            f"If this is a template, use `open --save-to <new-path>` "
            f"to lock autosave to a copy instead."
        )

    script = f'''
tell application "Keynote"
    activate
    open POSIX file "{escape_as(open_path)}"
    delay 1
    tell front document
        return name & "\t" & (count of slides)
    end tell
end tell
'''
    raw = run_as(script)
    name, count = raw.split("\t")

    def human(d, _m):
        if d["copied_to"]:
            console.print(f"copied: {d['source']} → {d['copied_to']}")
        console.print(f"opened: [bold]{d['name']}[/] ([cyan]{d['slides']}[/] slides)")
        if d["warning"]:
            warn.print(f"keynote (warn): {d['warning']}")

    emit(
        {
            "action": "open",
            "name": name,
            "slides": int(count),
            "path": open_path,
            "source": abs_src,
            "copied_to": copied_to,
            "warning": warning,
        },
        human=human,
    )


# ── info ─────────────────────────────────────────────────────────
@app.command(help="Show info about the front Keynote document.")
def info():
    script = '''
tell application "Keynote"
    if (count of documents) is 0 then return ""
    tell front document
        set docName to name
        try
            set docPath to POSIX path of (file of it as alias)
        on error
            set docPath to ""
        end try
        set slideCount to count of slides
        return docName & "\t" & docPath & "\t" & slideCount
    end tell
end tell
'''
    raw = run_as(script)
    if not raw:
        fail("no document open")
    name, path, count = raw.split("\t")

    def human(d, _m):
        console.print(f"name:   [bold]{d['name']}[/]")
        console.print(f"path:   {d['path'] or '[dim](unsaved)[/]'}")
        console.print(f"slides: [cyan]{d['slides']}[/]")

    emit(
        {"name": name, "path": path or None, "slides": int(count)},
        human=human,
    )


# ── list-masters ─────────────────────────────────────────────────
@app.command(name="list-masters", help="List slide layouts (master slides) of the front document's theme.")
def list_masters():
    script = '''
tell application "Keynote"
    set theLayouts to slide layouts of front document
    set output to ""
    repeat with i from 1 to count of theLayouts
        set output to output & i & "\t" & (name of item i of theLayouts) & "<<<EOL>>>"
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    layouts = []
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        if "\t" in line:
            idx, name = line.split("\t", 1)
            layouts.append({"index": int(idx.strip()), "name": name.strip()})

    def human(rows, _m):
        table = Table(title="Slide layouts", show_header=True)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("name", style="bold")
        for row in rows:
            table.add_row(str(row["index"]), row["name"])
        console.print(table)

    emit(layouts, {"count": len(layouts)}, human=human)


# ── add-slide ────────────────────────────────────────────────────
@app.command(name="add-slide", help="Add a new slide; optionally pick a layout, set title/body.")
def add_slide(
    master: Optional[str] = typer.Option(None, "--master", "-m", help="Layout name or index (1-based)"),
    title: Optional[str] = typer.Option(None, "--title", help="Title text"),
    body: Optional[str] = typer.Option(None, "--body", help="Body text. Use \\n for line breaks."),
):
    if master and master.isdigit():
        base_clause = f"set base layout of newSlide to slide layout {master}"
    elif master:
        base_clause = f'set base layout of newSlide to slide layout "{escape_as(master)}"'
    else:
        base_clause = ""

    title_clause = (
        f'set object text of default title item of newSlide to "{prepare_text(title)}"'
        if title else ""
    )
    body_clause = (
        f'set object text of default body item of newSlide to "{prepare_text(body)}"'
        if body else ""
    )

    script = f'''
tell application "Keynote"
    tell front document
        set newSlide to make new slide at end of slides
        {base_clause}
        {title_clause}
        {body_clause}
        return slide number of newSlide
    end tell
end tell
'''
    num = run_as(script)
    emit(
        {"action": "add-slide", "slide": int(num), "master": master,
         "title": title, "body": body},
        human=lambda d, _m: console.print(f"added slide [cyan]{d['slide']}[/]"),
    )


# ── set-title ────────────────────────────────────────────────────
@app.command(name="set-title", help="Set the default title text of a slide.")
def set_title(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    text: str = typer.Argument(..., help="Title text. Use \\n for line breaks."),
):
    script = f'''
tell application "Keynote"
    tell front document
        set object text of default title item of slide {slide} to "{prepare_text(text)}"
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "set-title", "slide": slide},
        human=lambda d, _m: console.print(f"slide [cyan]{d['slide']}[/] title set"),
    )


# ── set-body ─────────────────────────────────────────────────────
@app.command(name="set-body", help="Set the default body text of a slide.")
def set_body(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    text: str = typer.Argument(..., help="Body text. Use \\n for line breaks."),
):
    script = f'''
tell application "Keynote"
    tell front document
        set object text of default body item of slide {slide} to "{prepare_text(text)}"
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "set-body", "slide": slide},
        human=lambda d, _m: console.print(f"slide [cyan]{d['slide']}[/] body set"),
    )


# ── set-notes ────────────────────────────────────────────────────
@app.command(name="set-notes", help="Set the presenter notes (speaker notes) of a slide. Notes show in Keynote's presenter view during a slideshow but stay invisible to the audience — useful for drafting talk tracks alongside the slide. Batch many slides in one pass with --json instead of looping this command (one AppleScript round-trip, no per-call process startup).")
def set_notes(
    text: Optional[str] = typer.Argument(None, help="Notes text. Use \\n for line breaks. Omit when using --json."),
    slide: Optional[int] = typer.Option(None, "--slide", "-s", help="Slide number (1-based). Required unless --json is given."),
    json_map: Optional[str] = typer.Option(
        None, "--json",
        help='Batch mode: a JSON object mapping slide number -> notes, e.g. \'{"1":"intro","2":"demo"}\'. Pass "-" to read it from stdin. Sets every slide in a single AppleScript pass.',
    ),
):
    if json_map is not None:
        if slide is not None or text is not None:
            fail("--json is batch mode — don't also pass --slide / text", code=2)
        import json as _j

        raw = _sys.stdin.read() if json_map == "-" else json_map
        try:
            mapping = _j.loads(raw)
        except _j.JSONDecodeError as e:
            fail(f"--json isn't valid JSON: {e}", hint='expected an object like {"1":"notes","2":"more"}', code=2)
        if not isinstance(mapping, dict) or not mapping:
            fail("--json must be a non-empty object mapping slide number -> notes", code=2)
        try:
            slides = sorted(int(k) for k in mapping)
        except (TypeError, ValueError):
            fail("--json keys must be slide numbers", code=2)
        stmts = "\n        ".join(
            f'set presenter notes of slide {int(k)} to "{prepare_text(str(v))}"'
            for k, v in mapping.items()
        )
        script = f'''
tell application "Keynote"
    tell front document
        {stmts}
    end tell
end tell
'''
        run_as(script)
        emit(
            {"action": "set-notes", "slides": slides},
            human=lambda d, _m: console.print(
                f"notes set on slides [cyan]{', '.join(map(str, d['slides']))}[/]"
            ),
        )
        return

    if slide is None or text is None:
        fail("need --slide N and the notes text (or --json for batch mode)", code=2)
    script = f'''
tell application "Keynote"
    tell front document
        set presenter notes of slide {slide} to "{prepare_text(text)}"
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "set-notes", "slide": slide},
        human=lambda d, _m: console.print(f"slide [cyan]{d['slide']}[/] notes set"),
    )


# ── get-slide ────────────────────────────────────────────────────
@app.command(
    name="get-slide",
    help=(
        "Read title / default body / presenter notes of a slide. "
        "Outputs JSON with keys: slide, title, body, notes. CR / CRLF are "
        "normalized to LF so the values are clean to embed in agent prompts."
    ),
)
def get_slide(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            set t to ""
            try
                set t to (object text of default title item) as text
            end try
            set b to ""
            try
                set b to (object text of default body item) as text
            end try
            set n to ""
            try
                set n to (presenter notes) as text
            end try
            return t & "<<<F>>>" & b & "<<<F>>>" & n
        end tell
    end tell
end tell
'''
    raw = run_as(script)
    parts = raw.split("<<<F>>>", 2)
    while len(parts) < 3:
        parts.append("")
    title, body, notes = (p.replace("\r\n", "\n").replace("\r", "\n") for p in parts)
    payload = {"slide": slide, "title": title, "body": body, "notes": notes}

    def human(d, _m):
        import json as _j
        print(_j.dumps(d, ensure_ascii=False, indent=2))

    emit(payload, human=human)


# ── list-shapes ──────────────────────────────────────────────────
@app.command(name="list-shapes", help="List all shapes (iWork items) on a slide, with kind and current text. Use to find indices for set-shape-text on layouts beyond default title/body.")
def list_shapes(slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)")):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            set theItems to iWork items
            set output to ""
            repeat with i from 1 to count of theItems
                set itemKind to (class of item i of theItems) as string
                set itemText to ""
                try
                    set itemText to (object text of item i of theItems) as string
                end try
                set output to output & i & "\t" & itemKind & "\t" & itemText & "<<<EOL>>>"
            end repeat
            return output
        end tell
    end tell
end tell
'''
    raw = run_as(script)
    shapes = []
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        parts = line.split("\t", 2)
        if len(parts) >= 2:
            idx, kind = parts[0], parts[1]
            text = parts[2] if len(parts) == 3 else ""
            shapes.append({"index": int(idx), "kind": kind, "text": text})

    def human(rows, _m):
        table = Table(title=f"Shapes on slide {slide}", show_header=True)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("kind", style="dim")
        table.add_column("text", style="bold")
        for row in rows:
            shown = row["text"].replace("\r", " ↩ ").replace("\n", " ↩ ") or "[dim](empty)[/]"
            table.add_row(str(row["index"]), row["kind"], shown)
        console.print(table)

    emit(shapes, {"count": len(shapes), "slide": slide}, human=human)


# ── set-shape-text ───────────────────────────────────────────────
@app.command(name="set-shape-text", help="Set text on an arbitrary shape by index. Use list-shapes first to find which index you want (e.g. right column of a two-column layout).")
def set_shape_text(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number"),
    shape: int = typer.Option(..., "--shape", "-i", help="Shape index from list-shapes"),
    text: str = typer.Argument(..., help="Text. Use \\n for line breaks."),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            set object text of iWork item {shape} to "{prepare_text(text)}"
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "set-shape-text", "slide": slide, "shape": shape},
        human=lambda d, _m: console.print(
            f"slide [cyan]{d['slide']}[/] shape [cyan]{d['shape']}[/] text set"
        ),
    )


# ── set-position ─────────────────────────────────────────────────
@app.command(
    name="set-position",
    help=(
        "Reposition / resize an existing shape on a slide. Use list-shapes to "
        "find the index. Position is the top-left corner in points; width and "
        "height in points. Pass --x and --y together (or neither). Useful when "
        "the layout master positions a body or image off where you want it."
    ),
)
def set_position(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    shape: int = typer.Option(..., "--shape", "-i", help="Shape index from list-shapes"),
    x: Optional[int] = typer.Option(None, "--x", help="Left position in points"),
    y: Optional[int] = typer.Option(None, "--y", help="Top position in points"),
    width: Optional[int] = typer.Option(None, "--w", help="Width in points"),
    height: Optional[int] = typer.Option(None, "--h", help="Height in points"),
):
    if (x is None) != (y is None):
        fail("pass --x and --y together (or neither)", code=2)
    if x is None and width is None and height is None:
        fail("nothing to do — pass at least --x/--y, --w, or --h", code=2)

    parts = []
    if x is not None:
        parts.append(f"set position of iWork item {shape} to {{{x}, {y}}}")
    if width is not None:
        parts.append(f"set width of iWork item {shape} to {width}")
    if height is not None:
        parts.append(f"set height of iWork item {shape} to {height}")
    body = "\n            ".join(parts)
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            {body}
        end tell
    end tell
end tell
'''
    run_as(script)

    def human(d, _m):
        bits = []
        if d["x"] is not None:
            bits.append(f"pos=({d['x']},{d['y']})")
        if d["width"] is not None:
            bits.append(f"w={d['width']}")
        if d["height"] is not None:
            bits.append(f"h={d['height']}")
        console.print(
            f"slide [cyan]{d['slide']}[/] shape [cyan]{d['shape']}[/] {' '.join(bits)}"
        )

    emit(
        {"action": "set-position", "slide": slide, "shape": shape,
         "x": x, "y": y, "width": width, "height": height},
        human=human,
    )


# ── delete-shape ─────────────────────────────────────────────────
@app.command(name="delete-shape", help="Delete a shape from a slide by index. Use list-shapes first to find the index — useful for stripping empty placeholders (e.g. body placeholder on slides where you'll add-image directly) that would otherwise leave a faint outline in the export.")
def delete_shape(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    shape: int = typer.Option(..., "--shape", "-i", help="Shape index from list-shapes"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            delete iWork item {shape}
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "delete-shape", "slide": slide, "shape": shape},
        human=lambda d, _m: console.print(
            f"slide [cyan]{d['slide']}[/] shape [cyan]{d['shape']}[/] deleted"
        ),
    )


# ── list-slides ──────────────────────────────────────────────────
@app.command(name="list-slides", help="List slides of the front document with titles.")
def list_slides():
    script = '''
tell application "Keynote"
    tell front document
        set output to ""
        repeat with i from 1 to count of slides
            tell slide i
                set t to "(no title)"
                try
                    set tt to object text of default title item
                    if tt is not missing value and tt as string is not "" then set t to tt as string
                end try
                set output to output & i & "\t" & t & "<<<EOL>>>"
            end tell
        end repeat
        return output
    end tell
end tell
'''
    raw = run_as(script)
    slides = []
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        if "\t" in line:
            idx, t = line.split("\t", 1)
            slides.append({"index": int(idx), "title": t})

    def human(rows, _m):
        table = Table(title="Slides", show_header=True)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("title", style="bold")
        for row in rows:
            table.add_row(str(row["index"]), row["title"].replace("\r", " ").replace("\n", " "))
        console.print(table)

    emit(slides, {"count": len(slides)}, human=human)


# ── delete-slide ─────────────────────────────────────────────────
@app.command(name="delete-slide", help="Delete a slide.")
def delete_slide(slide: int = typer.Option(..., "--slide", "-s", help="Slide number to delete")):
    script = f'''
tell application "Keynote"
    tell front document
        delete slide {slide}
        return count of slides
    end tell
end tell
'''
    remaining = run_as(script)
    emit(
        {"action": "delete-slide", "slide": slide, "remaining": int(remaining)},
        human=lambda d, _m: console.print(
            f"deleted slide [cyan]{d['slide']}[/] (remaining: [cyan]{d['remaining']}[/])"
        ),
    )


# ── save ─────────────────────────────────────────────────────────
@app.command(
    help=(
        "Save the front document. With a path, writes a COPY there (Keynote's "
        "`save in <path>` is export-only — the doc remains bound to its "
        "original file, so subsequent autosaves still write to the original). "
        "To start from a template and have autosave follow a new path, use "
        "`open <template> --save-to <new-path>` instead."
    )
)
def save(
    path: Optional[Path] = typer.Argument(
        None,
        help=(
            "Path to write a copy to. Omit to save the doc in place at its "
            "current location. NOTE: passing a path does NOT rebind the doc."
        ),
    ),
):
    if path:
        abs_path = absolute(path)
        script = f'''
tell application "Keynote"
    save front document in POSIX file "{escape_as(abs_path)}"
end tell
'''
        run_as(script)
        # `save in <path>` writes a copy but does not change the doc's `file`
        # binding — so we trust the user-supplied path for the report, not
        # `file of front document` (which still points at the original).
        emit(
            {"action": "save", "copy": True, "path": abs_path},
            human=lambda d, _m: console.print(f"saved copy: {d['path']}"),
        )
    else:
        script = '''
tell application "Keynote"
    save front document
    return POSIX path of (file of front document as alias)
end tell
'''
        saved = run_as(script)
        emit(
            {"action": "save", "copy": False, "path": saved},
            human=lambda d, _m: console.print(f"saved: {d['path']}"),
        )


# ── export ───────────────────────────────────────────────────────
@app.command(help="Export the front document as PDF or PPTX.")
def export(
    pdf: Optional[Path] = typer.Option(None, "--pdf", help="Export to this PDF path"),
    pptx: Optional[Path] = typer.Option(None, "--pptx", help="Export to this PPTX path"),
):
    if not pdf and not pptx:
        fail("must specify --pdf or --pptx", code=2)
    if pdf and pptx:
        fail("pick one of --pdf or --pptx", code=2)
    if pdf:
        target = absolute(pdf)
        fmt = "PDF"
    else:
        target = absolute(pptx)
        fmt = "Microsoft PowerPoint"
    script = f'''
tell application "Keynote"
    export front document to POSIX file "{escape_as(target)}" as {fmt}
end tell
'''
    run_as(script)
    emit(
        {"action": "export", "format": fmt, "path": target},
        human=lambda d, _m: console.print(f"exported [{d['format']}]: {d['path']}"),
    )


# ── add-image ────────────────────────────────────────────────────
@app.command(name="add-image", help="Add an image to a slide.")
def add_image(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number"),
    image_path: Path = typer.Option(..., "--image", "-i", help="Path to image file"),
    x: int = typer.Option(100, "--x", help="Left position in points"),
    y: int = typer.Option(100, "--y", help="Top position in points"),
    width: Optional[int] = typer.Option(None, "--w", help="Width in points (omit for natural)"),
    height: Optional[int] = typer.Option(None, "--h", help="Height in points (omit for natural)"),
):
    abs_img = absolute(image_path)
    if not Path(abs_img).exists():
        fail(f"image not found: {abs_img}", code=2)
    size_clause = f", width:{width}, height:{height}" if (width and height) else ""
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            make new image with properties {{file:POSIX file "{escape_as(abs_img)}", position:{{{x}, {y}}}{size_clause}}}
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "add-image", "slide": slide, "image": abs_img},
        human=lambda d, _m: console.print(
            f"added image to slide [cyan]{d['slide']}[/]: {d['image']}"
        ),
    )


# ── add-table ────────────────────────────────────────────────────
@app.command(
    name="add-table",
    help=(
        "Add a table to a slide. Optionally seed cells with --data "
        '(rows split by \\n, cols by comma — e.g. "a,b,c\\nd,e,f"). '
        "No CSV quoting: for cells containing commas, omit --data and "
        "use set-cell afterwards."
    ),
)
def add_table(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    rows: int = typer.Option(..., "--rows", "-r", help="Number of rows"),
    cols: int = typer.Option(..., "--cols", "-c", help="Number of columns"),
    data: Optional[str] = typer.Option(
        None,
        "--data",
        help='CSV-style seed data, e.g. "Header1,Header2\\nVal1,Val2". Cells extra to rows×cols are ignored.',
    ),
    x: Optional[int] = typer.Option(None, "--x", help="Left position in points"),
    y: Optional[int] = typer.Option(None, "--y", help="Top position in points"),
    width: Optional[int] = typer.Option(None, "--w", help="Width in points"),
    height: Optional[int] = typer.Option(None, "--h", help="Height in points"),
):
    if rows < 1 or cols < 1:
        fail("--rows and --cols must be >= 1", code=2)

    parts = [
        f"make new table with properties {{row count:{rows}, column count:{cols}}}",
        # Keynote needs a beat after `make new table` before cells are
        # addressable — otherwise cell-set raises -1719 ("Invalid index").
        "delay 0.3",
        "set tableIdx to count of tables",
    ]
    if x is not None and y is not None:
        parts.append(f"set position of table tableIdx to {{{x}, {y}}}")
    if width is not None:
        parts.append(f"set width of table tableIdx to {width}")
    if height is not None:
        parts.append(f"set height of table tableIdx to {height}")

    if data:
        normalized = data.replace("\\n", "\n")
        grid = [row.split(",") for row in normalized.split("\n")]
        for r_idx, row_cells in enumerate(grid, start=1):
            if r_idx > rows:
                break
            for c_idx, cell_text in enumerate(row_cells, start=1):
                if c_idx > cols:
                    break
                escaped = escape_as(cell_text)
                parts.append(
                    f'set value of cell {c_idx} of row {r_idx} of table tableIdx to "{escaped}"'
                )

    parts.append("return tableIdx as string")
    body = "\n        ".join(parts)
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            {body}
        end tell
    end tell
end tell
'''
    table_index = run_as(script)
    emit(
        {"action": "add-table", "slide": slide, "table": int(table_index),
         "rows": rows, "cols": cols},
        human=lambda d, _m: console.print(
            f"added table [cyan]{d['table']}[/] to slide [cyan]{d['slide']}[/] "
            f"([cyan]{d['rows']}[/]×[cyan]{d['cols']}[/])"
        ),
    )


# ── set-cell ─────────────────────────────────────────────────────
@app.command(
    name="set-cell",
    help=(
        "Set the value of one cell in a table. Use \\n for line breaks "
        "within the cell. Default --table is 1 (slides usually have one)."
    ),
)
def set_cell(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    row: int = typer.Option(..., "--row", "-r", help="Row (1-based)"),
    col: int = typer.Option(..., "--col", "-c", help="Column (1-based)"),
    text: str = typer.Argument(..., help="Cell text. Use \\n for line breaks."),
    table: int = typer.Option(1, "--table", "-t", help="Table index on the slide (1-based, default 1)"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            set value of cell {col} of row {row} of table {table} to "{prepare_text(text)}"
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "set-cell", "slide": slide, "table": table, "row": row, "col": col},
        human=lambda d, _m: console.print(
            f"slide [cyan]{d['slide']}[/] table [cyan]{d['table']}[/] "
            f"cell ([cyan]{d['row']}[/],[cyan]{d['col']}[/]) set"
        ),
    )


# ── get-cell ─────────────────────────────────────────────────────
@app.command(
    name="get-cell",
    help=(
        "Read the value of one cell in a table. Default --table is 1 (slides "
        "usually have one)."
    ),
)
def get_cell(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    row: int = typer.Option(..., "--row", "-r", help="Row (1-based)"),
    col: int = typer.Option(..., "--col", "-c", help="Column (1-based)"),
    table: int = typer.Option(1, "--table", "-t", help="Table index on the slide (1-based, default 1)"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            return (value of cell {col} of row {row} of table {table}) as text
        end tell
    end tell
end tell
'''
    val = run_as(script)
    emit(
        {"slide": slide, "table": table, "row": row, "col": col, "value": val},
        human=lambda d, _m: print(d["value"]),
    )


# ── insert-row / insert-col ──────────────────────────────────────
@app.command(
    name="insert-row",
    help=(
        "Insert a new empty row into a table. The new row appears at position "
        "--at; existing rows at and below shift down. Use --at = rowCount + 1 "
        "to append at the end."
    ),
)
def insert_row(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    at: int = typer.Option(..., "--at", help="Row position for the new row (1-based)"),
    table: int = typer.Option(1, "--table", "-t", help="Table index on the slide"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            tell table {table}
                set rowCount to row count
                if {at} < 1 or {at} > rowCount + 1 then error "--at out of range (1.." & (rowCount + 1) & ")"
                if {at} > rowCount then
                    make new row at after row rowCount
                else
                    make new row at before row {at}
                end if
            end tell
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "insert-row", "slide": slide, "table": table, "at": at},
        human=lambda d, _m: console.print(
            f"slide [cyan]{d['slide']}[/] table [cyan]{d['table']}[/] inserted row at [cyan]{d['at']}[/]"
        ),
    )


@app.command(
    name="insert-col",
    help=(
        "Insert a new empty column into a table. The new column appears at "
        "position --at; existing columns at and right of --at shift right. "
        "Use --at = colCount + 1 to append at the end."
    ),
)
def insert_col(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    at: int = typer.Option(..., "--at", help="Column position for the new column (1-based)"),
    table: int = typer.Option(1, "--table", "-t", help="Table index on the slide"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            tell table {table}
                set colCount to column count
                if {at} < 1 or {at} > colCount + 1 then error "--at out of range (1.." & (colCount + 1) & ")"
                if {at} > colCount then
                    make new column at after column colCount
                else
                    make new column at before column {at}
                end if
            end tell
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "insert-col", "slide": slide, "table": table, "at": at},
        human=lambda d, _m: console.print(
            f"slide [cyan]{d['slide']}[/] table [cyan]{d['table']}[/] inserted column at [cyan]{d['at']}[/]"
        ),
    )


# ── delete-row / delete-col ──────────────────────────────────────
@app.command(name="delete-row", help="Delete a row from a table.")
def delete_row(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    row: int = typer.Option(..., "--row", "-r", help="Row to delete (1-based)"),
    table: int = typer.Option(1, "--table", "-t", help="Table index on the slide"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            tell table {table}
                delete row {row}
            end tell
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "delete-row", "slide": slide, "table": table, "row": row},
        human=lambda d, _m: console.print(
            f"slide [cyan]{d['slide']}[/] table [cyan]{d['table']}[/] deleted row [cyan]{d['row']}[/]"
        ),
    )


@app.command(name="delete-col", help="Delete a column from a table.")
def delete_col(
    slide: int = typer.Option(..., "--slide", "-s", help="Slide number (1-based)"),
    col: int = typer.Option(..., "--col", "-c", help="Column to delete (1-based)"),
    table: int = typer.Option(1, "--table", "-t", help="Table index on the slide"),
):
    script = f'''
tell application "Keynote"
    tell front document
        tell slide {slide}
            tell table {table}
                delete column {col}
            end tell
        end tell
    end tell
end tell
'''
    run_as(script)
    emit(
        {"action": "delete-col", "slide": slide, "table": table, "col": col},
        human=lambda d, _m: console.print(
            f"slide [cyan]{d['slide']}[/] table [cyan]{d['table']}[/] deleted column [cyan]{d['col']}[/]"
        ),
    )


# ── preview ──────────────────────────────────────────────────────
@app.command(help="Export to /tmp/keynote-preview.pdf for visual inspection.")
def preview():
    out = "/tmp/keynote-preview.pdf"
    script = f'''
tell application "Keynote"
    export front document to POSIX file "{out}" as PDF
end tell
'''
    run_as(script)
    emit(
        {"action": "preview", "path": out},
        human=lambda d, _m: console.print(f"preview: {d['path']}"),
    )


# ── close ────────────────────────────────────────────────────────
@app.command(help="Close the front document (saves first by default).")
def close(
    discard: bool = typer.Option(False, "--discard", help="Close without saving"),
):
    saving = "no" if discard else "yes"
    script = f'''
tell application "Keynote"
    close front document saving {saving}
end tell
'''
    run_as(script)
    emit(
        {"action": "close", "discarded": discard},
        human=lambda d, _m: console.print("closed"),
    )


if __name__ == "__main__":
    app()
