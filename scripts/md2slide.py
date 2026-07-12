#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "markdown-it-py", "linkify-it-py", "pygments", "pyyaml"]
# ///
"""Markdown -> slide deck toolbox — init / build. Self-contained HTML +
Chrome print-to-PDF. A marp-compatible subset: front-matter theme/header/
footer/paginate/style, `---` slide breaks, `![w:NNN]` image sizing,
`<!-- _class -->` / `<!-- _paginate -->` local directives, other HTML
comments as speaker notes (stripped from render)."""
from __future__ import annotations

# Siblings shadow stdlib (json.py, uuid.py) — drop our dir off sys.path so deps resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import base64
import mimetypes
import os
import re
import subprocess
import tempfile
from html import escape as _esc
from pathlib import Path
from typing import Optional

import typer
import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token
from pygments import highlight as _pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound
from rich.console import Console

from _envelope import emit, fail  # noqa: E402

app = typer.Typer(
    rich_markup_mode=None,
    no_args_is_help=True,
    add_completion=False,
    help="Markdown -> slide deck toolbox — init (scaffold) / build (HTML + PDF).",
)
console = Console(highlight=False)

SLIDE_W = 1280
SLIDE_H = 720

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

# ── theme: marp-default basics (white bg, heading hierarchy, code/blockquote)
# merged with the mediatek deck's centering/font override. header/footer text
# is never hardcoded here — it flows in via --header-text / --footer-text,
# set per-build from front-matter.
DEFAULT_THEME_CSS = """
section {
  display: flex;
  flex-direction: column;
  justify-content: safe center;
  align-items: stretch;
  padding: 60px 90px;
  background: #fff;
  color: #1a1a1a;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Helvetica Neue", sans-serif;
  font-size: 26px;
  line-height: 1.5;
}

section h1 { font-size: 2.2em; margin: 0.3em 0; text-align: center; color: var(--accent, #3297FC); }
section h2 { font-size: 1.7em; margin: 0.3em 0; text-align: center; color: var(--accent, #3297FC); }
section h3 { font-size: 1.35em; margin: 0.3em 0; text-align: center; }
section h4, section h5, section h6 { font-size: 1.1em; margin: 0.3em 0; text-align: center; }
section p { text-align: center; margin: 0.4em 0; }

section img { display: block; margin-inline: auto; max-width: 100%; }
section table { margin-inline: auto; border-collapse: collapse; font-size: 0.85em; }
section table th, section table td { border: 1px solid #ccc; padding: 0.3em 0.9em; }

section code {
  font-family: ui-monospace, "SF Mono", Menlo, "PingFang TC", monospace;
  background: #f3f3f3;
  border-radius: 3px;
  padding: 0.1em 0.35em;
  font-size: 0.82em;
}
section pre {
  background: #f3f3f3;
  border-radius: 6px;
  padding: 0.6em 0.9em;
  text-align: left;
  overflow: hidden;
  /* size on <pre>, not <pre><code>: the block's line-box strut must match
     the text size, or each line inherits the section's 26px strut and the
     block renders tiny text with huge line gaps */
  font-size: 0.82em;
  line-height: 1.35;
}
section pre code {
  background: none;
  padding: 0;
  font-size: 1em;
}

section blockquote {
  margin: 0.5em 0;
  padding: 0.2em 1em;
  border-left: 4px solid var(--accent, #888);
  color: #555;
  font-style: italic;
}

.md2slide-header, .md2slide-footer, .md2slide-pageno {
  position: absolute;
  font-size: 18px;
  font-weight: 400;
  color: #888;
}
.md2slide-header { top: 21px; left: 30px; }
.md2slide-header::after { content: var(--header-text, ""); }
.md2slide-footer { bottom: 21px; left: 30px; }
.md2slide-footer::after { content: var(--footer-text, ""); }
.md2slide-pageno { bottom: 21px; right: 30px; }
.md2slide-pageno::after { content: counter(slide); }
""".strip() + "\n"

# Structural mechanics (pagination, one section per printed page) — always
# applied ahead of the theme so a theme can still override cosmetics.
_STRUCTURE_CSS = f"""
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
@page {{ size: {SLIDE_W}px {SLIDE_H}px; margin: 0; }}
body {{ counter-reset: slide 0; }}
section {{
  position: relative;
  overflow: hidden;
  width: {SLIDE_W}px;
  height: {SLIDE_H}px;
  break-after: page;
  page-break-after: always;
  break-inside: avoid;
  counter-increment: slide;
}}
section:last-of-type {{ break-after: auto; page-break-after: auto; }}
""".strip() + "\n"

SCAFFOLD_SLIDES_MD = """---
theme: ./theme.css
header: NYCU WinLab
paginate: true
---

# Deck Title

A one-line subtitle for the whole deck

---

## A slide with code

A short line before the snippet:

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

---

## A slide with an image

![w:600](assets/demo.svg)

- put real assets under `assets/`
- reference them with paths relative to this file
""".lstrip()


# ── front-matter ─────────────────────────────────────────────────
_FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        fail("bad front-matter YAML", why=str(e), hint="check the `---` block at the top of the file", code=2)
    if not isinstance(meta, dict):
        fail("front-matter must be a YAML mapping", why=f"got {type(meta).__name__}", code=2)
    return meta, text[m.end():]


def _load_theme(md_file: Path, theme_ref: Optional[str]) -> str:
    if not theme_ref:
        return DEFAULT_THEME_CSS
    theme_path = (md_file.parent / str(theme_ref)).resolve()
    if not theme_path.exists():
        fail(
            f"theme not found: {theme_ref}",
            why=f"resolved to {theme_path}",
            hint="check the `theme:` path in front-matter — it's relative to the markdown file",
            code=2,
        )
    return theme_path.read_text(encoding="utf-8")


def _css_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ── marp-style local directives (`_class` / `_paginate`) & speaker notes ──
_COMMENT_RE = re.compile(r"^<!--([\s\S]*)-->$")
_RECOGNIZED_DIRECTIVES = {"_class", "_paginate"}


def _parse_comment_directives(inner: str) -> dict:
    try:
        parsed = yaml.safe_load(inner)
    except yaml.YAMLError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {k: v for k, v in parsed.items() if k in _RECOGNIZED_DIRECTIVES}


_RAW_IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc=")([^"]*)(")', re.IGNORECASE)


def _raw_html_rule(self, tokens, idx, options, env):  # noqa: ANN001
    """html_block/html_inline pass-through: strip any full HTML comment
    (directive or speaker note — never renders), and inline any raw `<img
    src="...">` the same way `_image_rule` does markdown-syntax images —
    stage-1.md's `<div><img .../></div>` blocks go through this path, not
    the `image` token rule."""
    content = tokens[idx].content or ""
    if _COMMENT_RE.match(content.strip()):
        return ""
    if "<img" in content.lower():
        md_dir = env.get("md_dir") if isinstance(env, dict) else None
        content = _RAW_IMG_SRC_RE.sub(
            lambda m: m.group(1) + _inline_image_src(m.group(2), md_dir) + m.group(3), content
        )
    return content


def _extract_directives(tokens: list[Token]) -> tuple[list[Token], list[str], Optional[bool]]:
    """Pull local `_class`/`_paginate` directive comments out of a slide's
    top-level token list. Every HTML comment — directive or plain speaker
    note — is dropped from the kept list; comments never render."""
    kept: list[Token] = []
    classes: list[str] = []
    paginate_override: Optional[bool] = None
    for tok in tokens:
        if tok.type in ("html_block", "html_inline"):
            m = _COMMENT_RE.match((tok.content or "").strip())
            if m:
                directives = _parse_comment_directives(m.group(1))
                if directives.get("_class"):
                    classes.extend(str(directives["_class"]).split())
                if "_paginate" in directives:
                    paginate_override = bool(directives["_paginate"])
                continue
        kept.append(tok)
    return kept, classes, paginate_override


def _split_slides(tokens: list[Token]) -> list[list[Token]]:
    """Cut a full token stream into per-slide groups at top-level `hr`
    (level 0) — walking the parsed token tree instead of regexing the
    source text means an `hr` inside a code fence or blockquote never
    misfires as a slide break."""
    slides: list[list[Token]] = []
    current: list[Token] = []
    for tok in tokens:
        if tok.type == "hr" and tok.level == 0:
            slides.append(current)
            current = []
        else:
            current.append(tok)
    slides.append(current)
    return [s for s in slides if s]


# ── image sizing: marp `![w:880]` / `![h:400]` alt-prefix syntax ──────────
_SIZE_PREFIX_RE = re.compile(r"^(?:(?:[wh]:\d+)\s*)+")
_SIZE_TOKEN_RE = re.compile(r"(?P<dim>[wh]):(?P<num>\d+)")


def _inline_image_src(src: str, md_dir: Optional[Path]) -> str:
    """Rewrite a local image src to a `data:` URI so the built HTML is truly
    self-contained: portable to any --out directory, and off this machine
    entirely. Remote/already-inlined sources pass through untouched; a src
    that doesn't resolve to a real file is left as-is (already broken in the
    source, nothing to embed)."""
    if not src or src.startswith(("data:", "http://", "https://", "//")):
        return src
    if md_dir is None:
        return src
    path = (md_dir / src).resolve()
    if not path.is_file():
        return src
    mime, _enc = mimetypes.guess_type(path.name)
    if mime is None or not mime.startswith("image/"):
        return src
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _image_rule(self, tokens, idx, options, env):  # noqa: ANN001
    token = tokens[idx]
    raw_alt = token.content or ""
    m = _SIZE_PREFIX_RE.match(raw_alt)
    width = height = None
    remaining = raw_alt
    if m:
        for tok in _SIZE_TOKEN_RE.finditer(m.group(0)):
            if tok.group("dim") == "w":
                width = tok.group("num")
            else:
                height = tok.group("num")
        remaining = raw_alt[m.end():].strip()
    token.attrSet("alt", remaining)
    styles = []
    if width:
        styles.append(f"width:{width}px")
    if height:
        styles.append(f"height:{height}px")
    if styles:
        token.attrSet("style", ";".join(styles))
    md_dir = env.get("md_dir") if isinstance(env, dict) else None
    token.attrSet("src", _inline_image_src(token.attrGet("src") or "", md_dir))
    return self.renderToken(tokens, idx, options, env)


# ── code fences: pygments highlighting ─────────────────────────────────
_PYGMENTS_FORMATTER = HtmlFormatter(nowrap=True, cssclass="hl")


def _highlight_code(code: str, lang: str, _attrs: str) -> str:
    lang = (lang or "").strip()
    lexer = None
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripall=False)
        except ClassNotFound:
            lexer = None
    if lexer is None:
        # No (valid) language tag: render as plain text instead of guessing.
        # pygments.guess_lexer() is unreliable on short/CJK-heavy snippets —
        # it can pick an unrelated language lexer and tag unmatched text
        # (e.g. Chinese prose) as a Pygments "Error" token, which the
        # default style renders with a red border. Slide code fences here
        # are mostly chat prompts, not real source, so no highlighting is
        # the correct default.
        lexer = TextLexer(stripall=False)
    body = _pygments_highlight(code, lexer, _PYGMENTS_FORMATTER)
    lang_cls = f" language-{lang}" if lang else ""
    return f'<pre class="hl{lang_cls}"><code>{body}</code></pre>\n'


def _make_md() -> MarkdownIt:
    # breaks=True matches marp-core: a manual line break in the markdown
    # source becomes <br> instead of collapsing to a space, so decks ported
    # from marp keep their line-level layout.
    md = MarkdownIt("gfm-like", {"html": True, "typographer": False, "breaks": True, "highlight": _highlight_code})
    # fuzzy links off: bare filenames like CLAUDE.md match the .md TLD and
    # turn into hyperlinks; only explicit http(s):// URLs should linkify
    md.linkify.set({"fuzzy_link": False})
    md.add_render_rule("image", _image_rule)
    md.add_render_rule("html_block", _raw_html_rule)
    md.add_render_rule("html_inline", _raw_html_rule)
    return md


# ── HTML assembly ────────────────────────────────────────────────
def _render_section(inner_html: str, classes: list[str], paginate: bool) -> str:
    cls = " ".join(["slide", *classes])
    parts = [f'<section class="{_esc(cls, quote=True)}">']
    parts.append('<div class="md2slide-header"></div>')
    parts.append('<div class="md2slide-footer"></div>')
    if paginate:
        parts.append('<div class="md2slide-pageno"></div>')
    parts.append(f'<div class="md2slide-body">{inner_html}</div>')
    parts.append("</section>")
    return "\n".join(parts)


def _assemble_html(
    *,
    title: str,
    theme_css: str,
    extra_style: str,
    sections: list[str],
    header_text: str,
    footer_text: str,
    accent: str,
) -> str:
    pygments_css = _PYGMENTS_FORMATTER.get_style_defs(".hl")
    var_parts = [
        f"--header-text: {_css_string(header_text)};",
        f"--footer-text: {_css_string(footer_text)};",
    ]
    if accent:
        var_parts.append(f"--accent: {accent};")
    root_vars = ":root { " + " ".join(var_parts) + " }"
    style = "\n\n".join(x for x in [_STRUCTURE_CSS, pygments_css, theme_css, extra_style, root_vars] if x.strip())
    body = "\n".join(sections)
    return (
        "<!doctype html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{_esc(title)}</title>\n<style>\n{style}\n</style>\n</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


# ── Chrome print-to-PDF ─────────────────────────────────────────────
def _find_chrome() -> str:
    env_path = os.environ.get("CHROME_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    import shutil as _shutil
    found = _shutil.which("google-chrome") or _shutil.which("chromium")
    if found:
        return found
    fail(
        "Chrome not found",
        why="md2slide needs headless Chrome to print HTML to PDF",
        hint="install Google Chrome, or set CHROME_PATH to a Chromium/Chrome binary",
        code=2,
    )


def _print_to_pdf(chrome: str, html_path: Path, pdf_path: Path) -> None:
    url = html_path.resolve().as_uri()
    proc = subprocess.run(
        [
            chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            "--virtual-time-budget=15000", f"--print-to-pdf={pdf_path}", url,
        ],
        capture_output=True, text=True, timeout=90,
    )
    if proc.returncode != 0 or not pdf_path.exists():
        fail("chrome print-to-pdf failed", why=(proc.stderr or "").strip()[:300] or "non-zero exit", code=2)


# ── init ─────────────────────────────────────────────────────────
@app.command(help="Scaffold a new deck: slides.md + theme.css + empty assets/.")
def init(
    dir: Path = typer.Argument(..., help="Target directory (created if missing)."),
    force: bool = typer.Option(False, "--force", help="Overwrite slides.md/theme.css if they already exist."),
):
    slides_path = dir / "slides.md"
    theme_path = dir / "theme.css"
    assets_path = dir / "assets"

    if not force:
        existing = [p for p in (slides_path, theme_path) if p.exists()]
        if existing:
            fail(
                f"already exists: {', '.join(str(p) for p in existing)}",
                hint="use --force to overwrite",
                code=2,
            )

    dir.mkdir(parents=True, exist_ok=True)
    assets_path.mkdir(exist_ok=True)
    slides_path.write_text(SCAFFOLD_SLIDES_MD, encoding="utf-8")
    theme_path.write_text(DEFAULT_THEME_CSS, encoding="utf-8")

    data = {
        "action": "init",
        "dir": str(dir),
        "slides": str(slides_path),
        "theme": str(theme_path),
        "assets": str(assets_path),
    }

    def human(d, _m):
        console.print(f"scaffolded [bold]{d['dir']}[/]")
        console.print(f"  {Path(d['slides']).name}")
        console.print(f"  {Path(d['theme']).name}")
        console.print(f"  {Path(d['assets']).name}/")
        console.print(f"\nnext: uv run scripts/md2slide.py build {d['slides']}")

    emit(data, human=human)


# ── build ────────────────────────────────────────────────────────
@app.command(help="Render <md> into self-contained HTML (+ Chrome print-to-PDF). Defaults to writing both next to the source.")
def build(
    md: Path = typer.Argument(..., help="Source markdown file."),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output directory (default: alongside the source)."),
    pdf_only: bool = typer.Option(False, "--pdf-only", help="Emit only the PDF; no .html is kept."),
    html_only: bool = typer.Option(False, "--html-only", help="Emit only the HTML; skip the Chrome PDF pass."),
):
    if pdf_only and html_only:
        fail("give at most one of --pdf-only / --html-only", hint="omit both to get both outputs", code=2)
    if not md.exists():
        fail(f"no such file: {md}", hint="check the path", code=2)

    text = md.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    theme_css = _load_theme(md, meta.get("theme"))
    header_text = str(meta.get("header") or "")
    footer_text = str(meta.get("footer") or "")
    accent = str(meta.get("accent") or "")
    global_paginate = bool(meta.get("paginate", False))
    extra_style = str(meta.get("style") or "")

    mdit = _make_md()
    tokens = mdit.parse(body)
    slide_groups = _split_slides(tokens)
    if not slide_groups:
        fail("no slides found", why="document has no content after front-matter", hint="add at least one heading or paragraph", code=2)

    render_env = {"md_dir": md.parent}
    sections = []
    for group in slide_groups:
        kept, classes, pg_override = _extract_directives(group)
        paginate = global_paginate if pg_override is None else pg_override
        inner_html = mdit.renderer.render(kept, mdit.options, render_env)
        sections.append(_render_section(inner_html, classes, paginate))

    full_html = _assemble_html(
        title=md.stem,
        theme_css=theme_css,
        extra_style=extra_style,
        sections=sections,
        header_text=header_text,
        footer_text=footer_text,
        accent=accent,
    )

    out_dir = Path(out) if out else md.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{md.stem}.html"
    pdf_path = out_dir / f"{md.stem}.pdf"

    wrote_html = False
    if not pdf_only:
        html_path.write_text(full_html, encoding="utf-8")
        wrote_html = True

    wrote_pdf = False
    tmp_html: Optional[Path] = None
    if not html_only:
        if wrote_html:
            render_html_path = html_path
        else:
            fd, tmp_name = tempfile.mkstemp(suffix=".html", prefix=f".{md.stem}.", dir=out_dir)
            os.close(fd)
            tmp_html = Path(tmp_name)
            tmp_html.write_text(full_html, encoding="utf-8")
            render_html_path = tmp_html
        chrome = _find_chrome()
        _print_to_pdf(chrome, render_html_path, pdf_path)
        wrote_pdf = True
        if tmp_html:
            tmp_html.unlink(missing_ok=True)

    data = {
        "action": "build",
        "input": str(md),
        "html": str(html_path) if wrote_html else None,
        "pdf": str(pdf_path) if wrote_pdf else None,
        "slides": len(sections),
    }

    def human(d, _m):
        outs = " · ".join(x for x in [d["html"], d["pdf"]] if x)
        console.print(f"built {d['slides']} slide(s) from {md.name} → [bold]{outs}[/]")

    emit(data, human=human)


if __name__ == "__main__":
    app()
