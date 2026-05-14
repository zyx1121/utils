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

import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Atomic Keynote ops — open / list / add slide / set text / export / …",
)
console = Console()
err = Console(stderr=True, style="red")


def run_as(script: str) -> str:
    """Run AppleScript, return stdout, raise typer.Exit on error."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        err.print(f"keynote: {result.stderr.strip() or 'AppleScript failed'}")
        raise typer.Exit(2)
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
    console.print(f"created: [bold]{name}[/]" + (f" → {absolute(path)}" if path else ""))


# ── open ─────────────────────────────────────────────────────────
@app.command(name="open", help="Open a Keynote (.key) or PowerPoint (.pptx) file.")
def open_cmd(path: Path = typer.Argument(..., help="Path to file")):
    abs_path = absolute(path)
    if not Path(abs_path).exists():
        err.print(f"keynote: file not found: {abs_path}")
        raise typer.Exit(2)
    script = f'''
tell application "Keynote"
    activate
    open POSIX file "{escape_as(abs_path)}"
    delay 1
    tell front document
        return name & "\t" & (count of slides)
    end tell
end tell
'''
    raw = run_as(script)
    name, count = raw.split("\t")
    console.print(f"opened: [bold]{name}[/] ([cyan]{count}[/] slides)")


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
        err.print("keynote: no document open")
        raise typer.Exit(1)
    name, path, count = raw.split("\t")
    console.print(f"name:   [bold]{name}[/]")
    console.print(f"path:   {path or '[dim](unsaved)[/]'}")
    console.print(f"slides: [cyan]{count}[/]")


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
    table = Table(title="Slide layouts", show_header=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("name", style="bold")
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        if "\t" in line:
            idx, name = line.split("\t", 1)
            table.add_row(idx.strip(), name.strip())
    console.print(table)


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
    console.print(f"added slide [cyan]{num}[/]")


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
    console.print(f"slide [cyan]{slide}[/] title set")


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
    console.print(f"slide [cyan]{slide}[/] body set")


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
    table = Table(title=f"Shapes on slide {slide}", show_header=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("kind", style="dim")
    table.add_column("text", style="bold")
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        parts = line.split("\t", 2)
        if len(parts) >= 2:
            idx, kind = parts[0], parts[1]
            text = parts[2] if len(parts) == 3 else ""
            shown = text.replace("\r", " ↩ ").replace("\n", " ↩ ") or "[dim](empty)[/]"
            table.add_row(idx, kind, shown)
    console.print(table)


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
    console.print(f"slide [cyan]{slide}[/] shape [cyan]{shape}[/] text set")


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
    table = Table(title="Slides", show_header=True)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("title", style="bold")
    for line in raw.split("<<<EOL>>>"):
        line = line.strip()
        if "\t" in line:
            idx, t = line.split("\t", 1)
            table.add_row(idx, t.replace("\r", " ").replace("\n", " "))
    console.print(table)


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
    console.print(f"deleted slide [cyan]{slide}[/] (remaining: [cyan]{remaining}[/])")


# ── save ─────────────────────────────────────────────────────────
@app.command(help="Save the front document. Optionally save to a new path.")
def save(path: Optional[Path] = typer.Argument(None, help="Save path (omit to save in place)")):
    if path:
        abs_path = absolute(path)
        script = f'''
tell application "Keynote"
    save front document in POSIX file "{escape_as(abs_path)}"
end tell
'''
        run_as(script)
        # Trust the user-specified path: Keynote may still track iCloud for
        # untitled docs even after `save in`, so its `file` property is
        # unreliable for reporting.
        console.print(f"saved: {abs_path}")
    else:
        script = '''
tell application "Keynote"
    save front document
    return POSIX path of (file of front document as alias)
end tell
'''
        saved = run_as(script)
        console.print(f"saved: {saved}")


# ── export ───────────────────────────────────────────────────────
@app.command(help="Export the front document as PDF or PPTX.")
def export(
    pdf: Optional[Path] = typer.Option(None, "--pdf", help="Export to this PDF path"),
    pptx: Optional[Path] = typer.Option(None, "--pptx", help="Export to this PPTX path"),
):
    if not pdf and not pptx:
        err.print("keynote: must specify --pdf or --pptx")
        raise typer.Exit(2)
    if pdf and pptx:
        err.print("keynote: pick one of --pdf or --pptx")
        raise typer.Exit(2)
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
    console.print(f"exported [{fmt}]: {target}")


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
        err.print(f"keynote: image not found: {abs_img}")
        raise typer.Exit(2)
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
    console.print(f"added image to slide [cyan]{slide}[/]: {abs_img}")


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
    console.print(f"preview: {out}")


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
    console.print("closed")


if __name__ == "__main__":
    app()
