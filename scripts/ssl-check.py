#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
# ]
# ///
"""Connect to a host over TLS and print the server certificate details."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so stdlib resolves correctly.
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

# Add ../lib for shared output helpers.
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import socket
import ssl
from datetime import datetime, timezone

import typer

from _envelope import emit, fail, parse_host  # noqa: E402


def format_dn(parts) -> str:
    """Flatten certificate distinguished-name tuples into a readable string."""
    return ", ".join(f"{k}={v}" for tup in parts for k, v in tup)


def parse_cert_time(value: str) -> datetime:
    return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)


def _human(data: dict, _meta: dict) -> None:
    rows = [
        ("host", f"{data['host']}:{data['port']}"),
        ("subject", data["subject"]),
        ("issuer", data["issuer"]),
        ("not_before", data["not_before"]),
        ("not_after", data["not_after"]),
        ("days_remaining", str(data["days_remaining"])),
        ("status", data["status"]),
    ]
    for label, value in rows:
        print(f"{label:16} {value}")


def main(
    target: str = typer.Argument(help="Hostname, host:port, or full URL (https://example.com)"),
    port: int = typer.Option(443, "--port", help="TCP port — used when target is a bare hostname"),
) -> None:
    """
    Connect to a host over TLS and print the server certificate details.
    Accepts a URL straight from your conversation — no need to strip it down.
    """

    try:
        host, resolved_port = parse_host(target, default_port=port)
    except ValueError as e:
        fail(
            f"couldn't parse target: {target}",
            why=str(e),
            hint="pass a hostname (example.com), host:port (example.com:8443), or a URL",
        )

    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, resolved_port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
    except socket.gaierror as e:
        fail(
            f"can't resolve {host}",
            why=f"DNS lookup failed: {e}",
            hint="check the hostname spelling and your network",
        )
    except (socket.timeout, TimeoutError) as e:
        fail(
            f"timed out connecting to {host}:{resolved_port}",
            why=str(e),
            hint="host may be down or blocking the port; try a different --port",
        )
    except ssl.SSLError as e:
        fail(
            f"TLS handshake failed with {host}:{resolved_port}",
            why=str(e),
            hint="server may not speak TLS on this port; for plain HTTP use a browser instead",
        )
    except OSError as e:
        fail(
            f"socket error connecting to {host}:{resolved_port}",
            why=str(e),
            hint="check firewall and network reachability",
        )

    subject = format_dn(cert.get("subject", ()))
    issuer = format_dn(cert.get("issuer", ()))
    not_before = parse_cert_time(cert["notBefore"])
    not_after = parse_cert_time(cert["notAfter"])
    days_remaining = (not_after - datetime.now(timezone.utc)).days

    if days_remaining < 0:
        status = "expired"
    elif days_remaining < 14:
        status = "expiring"
    else:
        status = "valid"

    data = {
        "host": host,
        "port": resolved_port,
        "subject": subject,
        "issuer": issuer,
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
        "days_remaining": days_remaining,
        "status": status,
    }
    emit(data, {"target": target}, human=_human)


if __name__ == "__main__":
    typer.run(main)
