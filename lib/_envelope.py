"""Output contract for utils scripts — JSON envelope + TTY-aware human form.

Every utils command emits exactly one envelope. The shape is fixed so agents
can pipe to jq and humans get pretty output for free.

Non-TTY (agent / pipe / redirect):
    {"success": true,  "data": ...,  "metadata": {...}}
    {"success": false, "error": {"message": "...", "why": "...", "hint": "..."}}

TTY (terminal):
    emit() either calls a script-supplied `human` renderer or pretty-prints
    the JSON. fail() prints a three-line Error / Why / Hint block to stderr.

Exit code is what distinguishes success from failure — agents that read JSON
can also branch on `success`, but the canonical signal stays Unix-native.
"""
from __future__ import annotations

import json as _json
import sys
from typing import Any, Callable, NoReturn, Optional
from urllib.parse import urlparse


def is_tty() -> bool:
    return sys.stdout.isatty()


def emit(
    data: Any,
    metadata: Optional[dict] = None,
    *,
    human: Optional[Callable[[Any, dict], None]] = None,
) -> None:
    """Emit a success envelope.

    On non-TTY stdout, prints the JSON envelope.
    On TTY, calls `human(data, metadata)` if given, else pretty-prints the
    envelope with indent=2.
    """
    meta = metadata or {}
    if is_tty() and human is not None:
        human(data, meta)
        return
    indent = 2 if is_tty() else None
    print(_json.dumps(
        {"success": True, "data": data, "metadata": meta},
        indent=indent,
        ensure_ascii=False,
    ))


def fail(
    message: str,
    why: Optional[str] = None,
    hint: Optional[str] = None,
    code: int = 1,
) -> NoReturn:
    """Emit a failure envelope and exit.

    TTY: writes Error / Why / Hint lines to stderr for human readability.
    Non-TTY: writes the JSON envelope to stdout so a piping agent only has
    to read one stream.
    """
    if is_tty():
        print(f"Error: {message}", file=sys.stderr)
        if why:
            print(f"Why:   {why}", file=sys.stderr)
        if hint:
            print(f"Hint:  {hint}", file=sys.stderr)
    else:
        print(_json.dumps({
            "success": False,
            "error": {"message": message, "why": why, "hint": hint},
        }, ensure_ascii=False))
    sys.exit(code)


def parse_host(target: str, default_port: int = 443) -> tuple[str, int]:
    """Accept a URL, a `host:port`, or a bare host. Return `(host, port)`.

    URLs are first-class because agents copy them straight out of the
    conversation — making the script reject `https://example.com/x` and demand
    a hostname is a needless round-trip.
    """
    if "://" in target:
        u = urlparse(target)
        if not u.hostname:
            raise ValueError(f"couldn't extract host from URL: {target!r}")
        return u.hostname, u.port or default_port
    if ":" in target and target.count(":") == 1:
        host, _, port_s = target.rpartition(":")
        try:
            return host, int(port_s)
        except ValueError as e:
            raise ValueError(f"port must be an integer in {target!r}: {e}") from e
    return target, default_port
