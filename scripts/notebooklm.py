#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "notebooklm-py==0.7.3",
# ]
# ///
"""
Generate a Google NotebookLM Slide Deck from sources and download it (pptx/pdf).

UNOFFICIAL / undocumented API. This wraps `notebooklm-py` (teng-lin/notebooklm-py,
pinned ==0.7.3), which drives NotebookLM's internal `batchexecute` RPCs
(CREATE_ARTIFACT / LIST_ARTIFACTS) the same way the web UI does — there is no
public API for this. Using it steps outside Google's NotebookLM ToS for
programmatic access, and Google can change the backend at any time without
notice, which will break this script until `notebooklm-py` (or this wrapper)
catches up. Treat output as best-effort, not a stable integration.

Auth: a Playwright `storage_state.json` (Google session cookies), never a
password. This script never logs in and never touches credentials directly —
produce the file once with the upstream CLI's own login flow:

    uvx --from notebooklm-py==0.7.3 --with playwright notebooklm login
    (first run also needs: uvx --from notebooklm-py==0.7.3 playwright install chromium)

That writes ~/.notebooklm/profiles/default/storage_state.json (notebooklm-py's
own convention — NOTEBOOKLM_HOME / --profile override it same as upstream).
Point --storage-state elsewhere if you keep it somewhere else. The file is a
live session credential: treat it like a password, never commit it.

Two ways to pick a notebook:
  --notebook-id <id>                          use an existing notebook
  --title "..." --source-url URL [--source-url URL ...]   create a new one

--source-url also works alongside --notebook-id, to add sources to an
existing notebook before generating.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Drop our dir off sys.path so stdlib resolves cleanly (siblings shadow json/uuid)
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

# Add ../lib for shared output helpers
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import asyncio
from enum import Enum
from pathlib import Path
from typing import Optional

import typer

from _envelope import emit, fail  # noqa: E402


class SlideFormat(str, Enum):
    DETAILED = "detailed"
    PRESENTER = "presenter"


class OutputFormat(str, Enum):
    PPTX = "pptx"
    PDF = "pdf"


def _human(data: dict, _meta: dict) -> None:
    print(f"notebook:  {data['notebook_id']}" + (f"  ({data['notebook_title']})" if data['notebook_title'] else ""))
    print(f"artifact:  {data['artifact_id']}")
    print(f"format:    {data['slide_format']} -> {data['output_format']}")
    print(f"file:      {data['file']}")


async def _amain(
    notebook_id: Optional[str],
    title: Optional[str],
    source_urls: list[str],
    slide_format: SlideFormat,
    output_format: OutputFormat,
    out: Path,
    instructions: Optional[str],
    storage_state: Optional[Path],
    profile: Optional[str],
    timeout: float,
) -> dict:
    from notebooklm import NotebookLMClient
    from notebooklm.exceptions import (
        ArtifactDownloadError,
        ArtifactNotReadyError,
        AuthExtractionError,
        NotebookLMError,
    )
    from notebooklm.rpc import SlideDeckFormat

    fmt = SlideDeckFormat.PRESENTER_SLIDES if slide_format is SlideFormat.PRESENTER else SlideDeckFormat.DETAILED_DECK

    try:
        async with NotebookLMClient.from_storage(
            path=str(storage_state) if storage_state else None,
            profile=profile,
        ) as client:
            if notebook_id:
                nb_id = notebook_id
            else:
                nb = await client.notebooks.create(title)
                nb_id = nb.id

            for url in source_urls:
                await client.sources.add_url(nb_id, url, wait=True, wait_timeout=180.0)

            status = await client.artifacts.generate_slide_deck(
                nb_id,
                instructions=instructions,
                slide_format=fmt,
            )
            if status.is_failed:
                fail(
                    "NotebookLM rejected the slide deck generation request",
                    why=status.error or f"error_code={status.error_code}",
                    hint="check the notebook has at least one ready source; NotebookLM "
                    "also rate-limits/gates generation per account",
                )

            final = await client.artifacts.wait_for_completion(
                nb_id, status.task_id, timeout=timeout
            )
            if not final.is_complete:
                fail(
                    f"slide deck did not finish generating (status={final.status})",
                    why=final.error or "generation still running or was removed server-side",
                    hint=f"retry with --timeout higher than {timeout:.0f}s, or check "
                    "the notebook in the NotebookLM web UI",
                )

            out.parent.mkdir(parents=True, exist_ok=True)
            saved = await client.artifacts.download_slide_deck(
                nb_id, str(out), artifact_id=final.task_id, output_format=output_format.value
            )

            return {
                "notebook_id": nb_id,
                "artifact_id": final.task_id,
                "notebook_title": title,
                "slide_format": slide_format.value,
                "output_format": output_format.value,
                "file": saved,
            }

    except AuthExtractionError as e:
        fail(
            "couldn't extract auth tokens from the NotebookLM homepage",
            why=str(e),
            hint="the storage_state cookies are probably expired — re-run "
            "`notebooklm login` to refresh them, or Google changed the page "
            "structure notebooklm-py scrapes (unofficial API, can break any time)",
        )
    except (ArtifactNotReadyError, ArtifactDownloadError) as e:
        fail(
            "slide deck generated but download failed",
            why=str(e),
            hint="Google may have changed the download URL shape again — this is "
            "the exact kind of drift the unofficial API is exposed to; check "
            "for a newer notebooklm-py release",
        )
    except NotebookLMError as e:
        fail(
            "NotebookLM request failed",
            why=str(e),
            hint="unofficial reverse-engineered API — could be an expired "
            "session (re-run `notebooklm login`), a rate limit, or a backend "
            "change upstream hasn't caught up with yet",
        )
    except FileNotFoundError as e:
        fail(
            "no storage_state.json found",
            why=str(e),
            hint="produce one with `uvx --from notebooklm-py==0.7.3 notebooklm login` "
            "(needs `playwright install chromium` first), or pass --storage-state",
        )


def main(
    notebook_id: Optional[str] = typer.Option(
        None, "--notebook-id", help="Existing notebook ID to generate into. Omit to create a new notebook (requires --title and at least one --source-url)."
    ),
    title: Optional[str] = typer.Option(
        None, "--title", help="Title for a new notebook. Required when --notebook-id is omitted."
    ),
    source_url: list[str] = typer.Option(
        [], "--source-url", help="Source URL to add (repeatable). Required to build a new notebook; optional extra sources when --notebook-id is given."
    ),
    slide_format: SlideFormat = typer.Option(
        SlideFormat.DETAILED, "--format", help="Slide deck style: detailed (full deck) or presenter (presenter-notes style)."
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.PPTX, "--output", help="Downloaded file format."
    ),
    out: Path = typer.Option(..., "--out", help="Where to save the downloaded file."),
    instructions: Optional[str] = typer.Option(
        None, "--instructions", help="Extra generation instructions (tone, focus, audience, etc)."
    ),
    storage_state: Optional[Path] = typer.Option(
        None, "--storage-state", help="Path to a Playwright storage_state.json. Default: notebooklm-py's own convention, ~/.notebooklm/profiles/<profile>/storage_state.json."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="notebooklm-py auth profile name (see NOTEBOOKLM_PROFILE). Ignored if --storage-state is set."
    ),
    timeout: float = typer.Option(
        600.0, "--timeout", help="Max seconds to wait for generation to finish before giving up."
    ),
) -> None:
    """
    Generate a NotebookLM Slide Deck artifact and download it as pptx or pdf.

    UNOFFICIAL, reverse-engineered API (see module docstring for the ToS /
    breakage caveat). Needs a storage_state.json from `notebooklm login` first
    — this script never handles a password.
    """
    if not notebook_id and not title:
        fail(
            "need either --notebook-id or --title",
            why="no target notebook was specified",
            hint="pass --notebook-id to use an existing notebook, or --title "
            "(with at least one --source-url) to create a new one",
        )
    if not notebook_id and not source_url:
        fail(
            "creating a new notebook needs at least one --source-url",
            why="a fresh notebook has no sources to generate a slide deck from",
            hint="pass --source-url (repeatable), or use --notebook-id against "
            "a notebook that already has sources",
        )

    result = asyncio.run(
        _amain(
            notebook_id,
            title,
            source_url,
            slide_format,
            output_format,
            out.expanduser(),
            instructions,
            storage_state.expanduser() if storage_state else None,
            profile,
            timeout,
        )
    )
    emit(result, {"unofficial_api": True}, human=_human)


if __name__ == "__main__":
    app = typer.Typer(rich_markup_mode=None, add_completion=False)
    app.command()(main)
    app()
