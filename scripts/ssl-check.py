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

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich/etc resolve those from stdlib.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import socket
import ssl
from datetime import datetime, timezone

import typer
from rich import print


def format_dn(parts) -> str:
    """Flatten certificate distinguished-name tuples into a readable string."""
    return ", ".join(f"{k}={v}" for tup in parts for k, v in tup)


def parse_cert_time(value: str) -> datetime:
    return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)


def main(
    host: str = typer.Argument(help="Hostname to check, e.g. example.com"),
    port: int = typer.Option(443, "--port", help="TCP port"),
) -> None:
    """
    Connect to a host over TLS and print the server certificate details.
    """

    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
    except (socket.gaierror, socket.timeout, OSError, ssl.SSLError) as e:
        print(f"Couldn't reach {host}:{port} — {e}")
        raise typer.Exit(1)

    subject = format_dn(cert.get("subject", ()))
    issuer = format_dn(cert.get("issuer", ()))
    not_before = parse_cert_time(cert["notBefore"])
    not_after = parse_cert_time(cert["notAfter"])
    days_remaining = (not_after - datetime.now(timezone.utc)).days

    print(f"host:           {host}:{port}")
    print(f"subject:        {subject}")
    print(f"issuer:         {issuer}")
    print(f"not_before:     {not_before.isoformat()}")
    print(f"not_after:      {not_after.isoformat()}")
    print(f"days_remaining: {days_remaining}")
    if days_remaining < 0:
        print("status:         expired — renew before someone notices")
    elif days_remaining < 14:
        print("status:         expires soon, time to rotate")
    else:
        print("status:         valid")


if __name__ == "__main__":
    typer.run(main)
