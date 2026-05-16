---
name: keynote
description: Compose Keynote presentations with the `utils keynote` building blocks — atomic AppleScript ops for slide decks. Use when the user wants to draft / edit / export a Keynote presentation, convert PPTX to .key, build from an outline, or work with a personal template. Triggers on "keynote", "簡報", "投影片", "slide deck", "presentation", "做投影片". Workflow shape — open or new → list-masters → add-slide / set-title / set-body → preview → export.
---

# keynote — slide-deck workflows over `utils keynote`

The plugin ships a `keynote` script with ~21 atomic AppleScript ops against Keynote.app. This skill composes them into full slide-deck workflows.

## Building blocks

```bash
utils keynote --help                  # full subcommand list

# Doc
utils keynote new [path] [--theme NAME]
utils keynote open <path> [--save-to NEW] [--force]   # accepts .key or .pptx
utils keynote info
utils keynote save [path]             # path = EXPORT a copy, not rebind
utils keynote close [--discard]
utils keynote preview                 # → /tmp/keynote-preview.pdf

# Layouts & slides
utils keynote list-masters
utils keynote list-slides
utils keynote add-slide --master N|name [--title TXT] [--body TXT]
utils keynote delete-slide --slide N

# Read
utils keynote get-slide      --slide N                    # JSON: {slide, title, body, notes} — newlines normalized
utils keynote list-shapes    --slide N                    # discover shape indices + current text

# Edit
utils keynote set-title      --slide N <text>
utils keynote set-body       --slide N <text>
utils keynote set-notes      --slide N <text>             # presenter notes (speaker view only)
utils keynote set-shape-text --slide N --shape M <text>   # non-default placeholders
utils keynote set-position   --slide N --shape M [--x X --y Y] [--w W] [--h H]  # nudge existing shape
utils keynote delete-shape   --slide N --shape M          # remove a placeholder/shape (use list-shapes to find index)

# Content
utils keynote add-image --slide N --image PATH [--x N --y N --w N --h N]
utils keynote add-table --slide N --rows R --cols C [--data CSV] [--x N --y N --w N --h N]
utils keynote set-cell  --slide N --row R --col C <text> [--table M]    # M defaults to 1
utils keynote get-cell  --slide N --row R --col C        [--table M]
utils keynote insert-row --slide N --at R [--table M]                   # push existing rows down
utils keynote insert-col --slide N --at C [--table M]                   # push existing cols right
utils keynote delete-row --slide N --row R [--table M]
utils keynote delete-col --slide N --col C [--table M]

# Export
utils keynote export --pdf PATH       # or --pptx PATH
```

Use `\n` for line breaks in titles/bodies. First call launches Keynote.app.

## Workflows

### Draft from outline

```bash
utils keynote new
utils keynote list-masters            # see what the theme offers
utils keynote add-slide --master "Title"           --title "Project X"
utils keynote add-slide --master "Title & Bullets" --title "Background" --body "Item one\nItem two"
utils keynote add-slide --master "Big Fact"        --title "92% accuracy"
utils keynote preview                 # visual sanity check
utils keynote save ~/Desktop/project-x.key
```

### Use the user's template

If the user has a `.key` or `.pptx` template (often under `~/Downloads/` or `~/Documents/`):

```bash
# --save-to filesystem-copies the template, then opens the copy. Autosave
# locks to the copy from the very first edit — the template is never touched.
utils keynote open <template path> --save-to ~/Desktop/<deck>.key

utils keynote list-masters
# Layout names from custom templates are often opaque (e.g. "8_標題投影片_1").
# Ask the user which layout maps to title / content / section — names alone
# don't tell you. Once mapped, prefer master names over indices (more stable).
utils keynote add-slide --master "<name>" --title "..." --body "..."
utils keynote save                        # writes to ~/Desktop/<deck>.key
```

For pptx-only templates: same flow — `--save-to` accepts a `.key` destination.

**Do not** use `open <template>` followed by `save <new-path>` as a substitute. Keynote's `save in <path>` is export-only: it writes a copy but does NOT rebind the document, so every autosave between the `open` and the manual `save` lands on the original template (memory: `feedback_keynote_autosave_persists`).

### Body patterns

Three shapes a body can take — pick by content:

- **Nested bullets** (default) — paragraphs of text with hierarchy. `set-body` lays the lines down at L0; **bullet level (L1, L2…) must be set in Keynote.app GUI** with Tab — AppleScript can't write paragraph levels (see Known limits).
- **ASCII tree** — for file / directory layouts. Plain text with `├── └── │` characters; Keynote's body renders them aligned with the master's monospace style. Use `set-body` with the tree as-is.
- **Comparison table** — for N items compared across M dimensions; see Tables below.

### Tables

```bash
# Seed a whole grid in one call (CSV-style: rows split by \n, cols by ,):
utils keynote add-table --slide 3 --rows 3 --cols 3 \
  --data "Name,Role,Year\nLoki,SWE,2026\nAlpha,PM,2025" \
  --x 100 --y 200

# Edit cells afterwards (--table defaults to 1; row/col are 1-based):
utils keynote set-cell --slide 3 --row 2 --col 2 "Lead SWE"
```

`--data` has no CSV quoting — if a cell needs an embedded comma or line break (`\n`), drop `--data` and fill that cell with `set-cell` instead. Table styling (cell fonts, header band, alignment, row banding) follows the slide theme's table style; Keynote's AppleScript dictionary doesn't expose those, so format in Keynote.app. Convention for comparison tables: first column centered (item name), other columns left-aligned (descriptions), header row distinct.

### Review / edit existing

```bash
utils keynote open ~/Documents/deck.key
utils keynote list-slides             # current titles
utils keynote get-slide --slide 3     # JSON: title + body + notes (newlines preserved)
utils keynote set-title --slide 3 "Revised claim"
utils keynote set-body  --slide 3 "Updated\nbullets"
utils keynote save
```

For a full review pass, loop `get-slide --slide N` over `list-slides` to read every slide's body and notes without dropping to raw AppleScript.

### Export

```bash
utils keynote export --pdf  ~/Desktop/deck.pdf     # review / share
utils keynote export --pptx ~/Desktop/deck.pptx    # non-Keynote audience
```

## Patterns

- **`list-masters` before `add-slide`** when the theme is unfamiliar — custom templates rarely have self-describing layout names.
- **Use `open --save-to <new-path>` when starting from a template.** Keynote autosaves continuously and `save in <path>` is export-only (doc stays bound to the source). `--save-to` filesystem-copies first, then opens the copy — autosave locks to the new path from edit zero. `close --discard` does NOT roll back autosave, so this has to be right up front.
- **`preview` after batch edits** — catches layout drift before the user opens the file.
- **Prefer master names over indices** when the deck might re-theme; names usually survive, indices don't.
- **`set-title` / `set-body` only touch the layout's default placeholders.** For multi-placeholder layouts (two-column bullets, image+text, etc.), use `list-shapes --slide N` to see all `iWork item` indices, then `set-shape-text --slide N --shape M <text>`.
- **Strip empty placeholders before exporting** when a slide uses `add-image` to replace bullet placeholders. The placeholder's outline still renders in PDF/PPTX export. `list-shapes` to find the empty body shape index, then `delete-shape` to remove it.
- **Draft talk tracks alongside slides with `set-notes`.** Presenter notes live in Keynote's presenter view — invisible to the audience but visible to you during the slideshow. Especially useful when the slide visual is a code block or diagram and the actual explanation has to live somewhere readable.

## Known limits

- No `format-text` (font / size / color), `set-bullets`, or paragraph-indent levels — Keynote's AppleScript dictionary is sparse here. Adjust those in Keynote.app, or render to image and use `add-image`.
- **Tables: structure + cell values only, no styling.** `add-table`, `set-cell`, `get-cell`, `insert-row`, `insert-col`, `delete-row`, `delete-col` cover row/column count, position/size, and text per cell. Cell fonts, alignment, header-row styling, merged cells, and column widths all need Keynote.app GUI — pick a theme with a table style you like before generating.
- `add-slide` only appends at end. Reorder via Keynote.app GUI.
- **`save <path>` is export-only, not save-as.** Keynote's `save front document in POSIX file <path>` writes a copy at `<path>` but does NOT change `file of front document` — the doc remains bound to its original file, and subsequent autosaves keep writing there. To start from a template safely, use `open <src> --save-to <dst>` (filesystem-copy then open, so the doc is bound to `<dst>` from the start).
- **Can't rename slide layouts (master slides).** The `name` property is `access="r"` in Keynote's AppleScript dictionary; every rename attempt errors with -10006. To clean up imported PPT layout names (e.g. `8_標題投影片_1` → `Title`): open in Keynote.app, **View → Edit Master Slides**, right-click a master → **Rename Slide**. The only programmatic path is editing the `.iwa` protobufs inside the `.key` Zip via `keynote-parser` (heavy, not exposed by `utils keynote`).
