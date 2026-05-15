---
name: keynote
description: Compose Keynote presentations with the `utils keynote` building blocks — atomic AppleScript ops for slide decks. Use when the user wants to draft / edit / export a Keynote presentation, convert PPTX to .key, build from an outline, or work with a personal template. Triggers on "keynote", "簡報", "投影片", "slide deck", "presentation", "做投影片". Workflow shape — open or new → list-masters → add-slide / set-title / set-body → preview → export.
---

# keynote — slide-deck workflows over `utils keynote`

The plugin ships a `keynote` script with 13 atomic AppleScript ops against Keynote.app. This skill composes them into full slide-deck workflows.

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

# Edit
utils keynote set-title      --slide N <text>
utils keynote set-body       --slide N <text>
utils keynote set-shape-text --slide N --shape M <text>   # non-default placeholders
utils keynote list-shapes    --slide N                    # discover shape indices

# Content
utils keynote add-image --slide N --image PATH [--x N --y N --w N --h N]

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

### Edit existing

```bash
utils keynote open ~/Documents/deck.key
utils keynote list-slides             # current titles
utils keynote set-title --slide 3 "Revised claim"
utils keynote set-body  --slide 3 "Updated\nbullets"
utils keynote save
```

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

## Known limits

- No `format-text` (font / size / color), `set-bullets`, or paragraph-indent levels — Keynote's AppleScript dictionary is sparse here. Adjust those in Keynote.app, or render to image and use `add-image`.
- `add-slide` only appends at end. Reorder via Keynote.app GUI.
- **`save <path>` is export-only, not save-as.** Keynote's `save front document in POSIX file <path>` writes a copy at `<path>` but does NOT change `file of front document` — the doc remains bound to its original file, and subsequent autosaves keep writing there. To start from a template safely, use `open <src> --save-to <dst>` (filesystem-copy then open, so the doc is bound to `<dst>` from the start).
- **Can't rename slide layouts (master slides).** The `name` property is `access="r"` in Keynote's AppleScript dictionary; every rename attempt errors with -10006. To clean up imported PPT layout names (e.g. `8_標題投影片_1` → `Title`): open in Keynote.app, **View → Edit Master Slides**, right-click a master → **Rename Slide**. The only programmatic path is editing the `.iwa` protobufs inside the `.key` Zip via `keynote-parser` (heavy, not exposed by `utils keynote`).
