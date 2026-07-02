#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
# ]
# ///
"""Scaffold a new macOS menubar app from the macos-cli-dev house template."""
from __future__ import annotations

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import datetime
import re
import shutil
import subprocess
from pathlib import Path

import typer
from rich import print

TEMPLATE = Path.home() / ".kilo" / "skills" / "macos-cli-dev" / "template"

# 不會是文字、不該做 token 替換的副檔名。
BINARY_SUFFIXES = {".icns", ".png", ".pdf", ".tiff", ".gif", ".jpg", ".jpeg"}


def slug(name: str) -> str:
    """app 名 → bundle-id 後綴：留英數，全小寫。"""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def substitute(root: Path, tokens: dict[str, str]) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix in BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = text
        for key, val in tokens.items():
            new = new.replace(key, val)
        if new != text:
            path.write_text(new, encoding="utf-8")


def rename_paths(root: Path, app: str) -> None:
    """把含 __APP__ 的路徑名換成真名（深到淺，先檔後夾）。"""
    for path in sorted(root.rglob("*__APP__*"), key=lambda p: len(p.parts), reverse=True):
        path.rename(path.with_name(path.name.replace("__APP__", app)))


def new(
    name: str = typer.Argument(help="App 名（也是 SwiftPM target / 顯示名，如 Cappuccino）"),
    bundle_id: str = typer.Option("", "--bundle-id", help="預設 tw.zyx.<lower>"),
    symbol: str = typer.Option("sparkle", "--symbol", help="選單列 SF Symbol fallback"),
    category: str = typer.Option("public.app-category.utilities", "--category", help="LSApplicationCategoryType"),
    tagline: str = typer.Option("", "--tagline", help="README 一行 tagline"),
    into: Path = typer.Option(Path.cwd(), "--dir", help="建在哪個母目錄下（預設 cwd）"),
    no_icon: bool = typer.Option(False, "--no-icon", help="跳過 icon 產生"),
    no_git: bool = typer.Option(False, "--no-git", help="跳過 git init"),
) -> None:
    """從 macos-cli-dev house template 開一個新的 macOS 選單列 app。"""
    if not TEMPLATE.is_dir():
        print(f"[red]✗ 找不到模板：{TEMPLATE}[/red]")
        raise typer.Exit(1)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
        print("[red]✗ app 名只能英數、字母開頭（會當 SwiftPM target 名）[/red]")
        raise typer.Exit(1)

    target = (into / name).resolve()
    if target.exists():
        print(f"[red]✗ 已存在：{target}[/red]")
        raise typer.Exit(1)

    tokens = {
        "__APP__": name,
        "__APP_LOWER__": slug(name),
        "__BUNDLE_ID__": bundle_id or f"tw.zyx.{slug(name)}",
        "__YEAR__": str(datetime.date.today().year),
        "__CATEGORY__": category,
        "__SF_SYMBOL__": symbol,
        "__TAGLINE__": tagline or f"{name} — a tiny macOS menubar app.",
    }

    shutil.copytree(TEMPLATE, target)
    rename_paths(target, name)
    substitute(target, tokens)
    print(f"[green]✓[/green] scaffolded [bold]{target}[/bold]  (bundle id [cyan]{tokens['__BUNDLE_ID__']}[/cyan])")

    if not no_icon:
        try:
            subprocess.run(["./scripts/generate-icon.py"], cwd=target, check=True,
                            capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            detail = e.stderr.strip() if e.stderr else "(no stderr captured)"
            print(f"[yellow]! icon 產生失敗（之後跑 `make icon`）：{detail}[/yellow]")
        except FileNotFoundError as e:
            print(f"[yellow]! icon 產生失敗（之後跑 `make icon`）：{e}[/yellow]")

    if not no_git:
        def _git(*args: str) -> None:
            # capture_output=True is load-bearing beyond "clean errors": without it
            # this subprocess inherits our stdout/stderr file descriptors. Run under
            # the MCP executor, those descriptors are the same pipes it reads to
            # EOF — an uncaptured child surviving past a `kill()` (or in this repo's
            # case, just running normally but still holding the fd open a beat
            # longer than expected) can leave the read side hanging. Every
            # subprocess.run() in a manifested atom must capture its own output.
            try:
                subprocess.run(["git", *args], cwd=target, check=True,
                                capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                detail = e.stderr.strip() if e.stderr else "(no stderr captured)"
                print(f"[red]✗ git {' '.join(args)} failed: {detail}[/red]")
                raise typer.Exit(1)

        _git("init", "-q")
        _git("add", "-A")
        _git("commit", "-q", "-m", f"init: scaffold {name} from macos-cli-dev template")
        print("[green]✓[/green] git init + first commit")

    print(f"\n下一步：\n  cd {target}\n  make run        # build + sign + 開\n"
          "  # 要穩定 TCC / 發版：cp Makefile.local.example Makefile.local 後填")


if __name__ == "__main__":
    app = typer.Typer(rich_markup_mode=None, add_completion=False)

    # no-op group callback —— 讓 typer 把 new 當「子命令」(utils mac-app new ...)，
    # 而非單一命令(否則 "new" 會被當成 name 引數)。也替未來子命令留位。
    @app.callback()
    def _root() -> None:
        """macOS app scaffolding (macos-cli-dev house template)."""

    app.command("new")(new)
    app()
