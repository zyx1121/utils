#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich"]
# ///
"""PVE / gateway atom operations via SSH aliases.

Wraps the `ssh pve` / `ssh gateway` conventions in a single dispatcher so
agents don't have to learn the qm / iptables / dnsmasq / Caddy command
surfaces directly. Real infrastructure (host IPs, port, subnet) stays in
the user's ~/.ssh/config — this script references aliases only.

Env knobs (all optional, sensible defaults):
    UTILS_PVE_HOST            SSH alias of PVE host (default: pve)
    UTILS_PVE_GATEWAY         SSH alias of edge gateway (default: gateway)
    UTILS_PVE_TEMPLATE        Default clone source VMID (default: 9000)
    UTILS_PVE_GATEWAY_IP      VM subnet gateway IP (default: 10.10.10.1)
    UTILS_PVE_GATEWAY_DNS     Path to dnsmasq hosts file on gateway
    UTILS_PVE_GATEWAY_CADDY   Path to Caddyfile on gateway
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# Some siblings in this directory shadow stdlib modules (json.py, uuid.py).
# Drop our directory off sys.path so typer/rich resolve those from stdlib.
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

# Add ../lib for shared output helpers (envelope, fail).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from _envelope import emit, fail  # noqa: E402

PVE_HOST = os.environ.get("UTILS_PVE_HOST", "pve")
GATEWAY_HOST = os.environ.get("UTILS_PVE_GATEWAY", "gateway")
PVE_TEMPLATE = int(os.environ.get("UTILS_PVE_TEMPLATE", "9000"))
GATEWAY_IP = os.environ.get("UTILS_PVE_GATEWAY_IP", "10.10.10.1")
GATEWAY_DNS_HOSTS = os.environ.get("UTILS_PVE_GATEWAY_DNS", "/home/user/gateway/dns/hosts")
GATEWAY_CADDYFILE = os.environ.get("UTILS_PVE_GATEWAY_CADDY", "/home/user/gateway/Caddyfile")

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="PVE / gateway atoms — list / status / start / stop / ssh / clone / forward / dns / caddy via SSH aliases.",
)
console = Console()


def ssh_run(host: str, *parts: str, capture: bool = True) -> str:
    """Run a command on `host` via SSH alias. Parts are quoted for safety."""
    remote = " ".join(shlex.quote(str(p)) for p in parts)
    result = subprocess.run(
        ["ssh", host, remote],
        capture_output=capture, text=True, check=False,
    )
    if result.returncode != 0:
        fail(
            f"ssh {host} failed",
            why=(result.stderr.strip() if capture else "non-zero exit") or "non-zero exit",
            hint=f"verify `ssh {host}` works in your terminal first",
        )
    return result.stdout if capture else ""


def parse_qm_list(output: str) -> list[dict]:
    """Parse `qm list` table. Header: VMID NAME STATUS MEM(MB) BOOTDISK(GB) PID."""
    lines = output.strip().splitlines()
    if len(lines) <= 1:
        return []
    vms = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            vms.append({
                "vmid": int(parts[0]),
                "name": parts[1],
                "status": parts[2],
                "mem_mb": int(parts[3]),
            })
        except ValueError:
            continue
    return vms


def find_vm(name_or_id: str) -> dict:
    vms = parse_qm_list(ssh_run(PVE_HOST, "qm", "list"))
    for vm in vms:
        if vm["name"] == name_or_id or str(vm["vmid"]) == name_or_id:
            return vm
    fail(
        f"no VM named {name_or_id!r}",
        why="not in `qm list`",
        hint="run `utils pve list` to see all VMs",
    )


# ── list ────────────────────────────────────────────────────────
@app.command("list", help="List all VMs on the PVE host.")
def list_vms() -> None:
    vms = parse_qm_list(ssh_run(PVE_HOST, "qm", "list"))

    def human(data, _meta):
        t = Table(show_header=True, header_style="bold")
        t.add_column("VMID")
        t.add_column("Name")
        t.add_column("Status")
        t.add_column("Mem")
        for v in data:
            style = "green" if v["status"] == "running" else "dim"
            t.add_row(str(v["vmid"]), v["name"], v["status"], f"{v['mem_mb']}MB", style=style)
        console.print(t)

    emit(vms, {"count": len(vms), "host": PVE_HOST}, human=human)


# ── status ──────────────────────────────────────────────────────
@app.command(help="Show config + status for a VM by name or VMID.")
def status(name: str = typer.Argument(..., help="VM name or VMID")) -> None:
    vm = find_vm(name)
    config_out = ssh_run(PVE_HOST, "qm", "config", str(vm["vmid"]))
    info = {"vmid": vm["vmid"], "name": vm["name"], "status": vm["status"]}
    keep = {"cores", "memory", "ostype", "ipconfig0", "ciuser",
            "nameserver", "searchdomain", "net0", "scsi0"}
    for line in config_out.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if k in keep:
            info[k] = v

    def human(data, _meta):
        for k, v in data.items():
            console.print(f"  [bold]{k}[/]: {v}")

    emit(info, human=human)


# ── start / stop ────────────────────────────────────────────────
@app.command(help="Start a VM.")
def start(name: str = typer.Argument(..., help="VM name or VMID")) -> None:
    vm = find_vm(name)
    ssh_run(PVE_HOST, "qm", "start", str(vm["vmid"]))
    emit({"vmid": vm["vmid"], "name": vm["name"], "action": "start"})


@app.command(help="Stop a VM (graceful shutdown).")
def stop(
    name: str = typer.Argument(..., help="VM name or VMID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    vm = find_vm(name)
    if not yes and not typer.confirm(f"stop VM {vm['name']!r} (VMID {vm['vmid']})?"):
        fail("aborted", why="user did not confirm", hint="pass --yes to skip")
    ssh_run(PVE_HOST, "qm", "stop", str(vm["vmid"]))
    emit({"vmid": vm["vmid"], "name": vm["name"], "action": "stop"})


# ── ssh ─────────────────────────────────────────────────────────
@app.command(name="ssh", help="SSH to a VM — refuses if alias is missing.")
def ssh_cmd(
    name: str = typer.Argument(..., help="VM name (must match ~/.ssh/config Host alias)"),
    command: Optional[list[str]] = typer.Argument(None, help="Optional remote command"),
) -> None:
    ssh_config = Path("~/.ssh/config").expanduser()
    has_alias = False
    if ssh_config.exists():
        for line in ssh_config.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped.lower().startswith("host "):
                continue
            hosts = stripped.split(None, 1)[1].split()
            if name in hosts:
                has_alias = True
                break
    if not has_alias:
        fail(
            f"no SSH alias {name!r} in ~/.ssh/config",
            why="aliases are the source of truth for VM connectivity",
            hint=f"add a Host entry for {name}, or use `utils pve clone` which prints the alias to add",
        )

    args = ["ssh", name]
    if command:
        args.extend(command)
    result = subprocess.run(args)
    raise typer.Exit(result.returncode)


# ── clone ───────────────────────────────────────────────────────
@app.command(help="Clone from template, set IP, start; prints SSH alias to add.")
def clone(
    name: str = typer.Argument(..., help="New VM name"),
    ip: str = typer.Option(..., "--ip", help="Internal IP (e.g. 10.10.10.42)"),
    template: int = typer.Option(PVE_TEMPLATE, "--template", help="Source template VMID"),
    ram: Optional[int] = typer.Option(None, "--ram", help="Override template RAM (MB)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    existing = {v["vmid"] for v in parse_qm_list(ssh_run(PVE_HOST, "qm", "list"))}
    new_vmid = 100
    while new_vmid in existing:
        new_vmid += 1

    plan = f"clone template {template} → VMID {new_vmid} as {name!r}, IP {ip}/24, gw {GATEWAY_IP}"
    if ram:
        plan += f", RAM {ram}MB"
    console.print(plan)
    if not yes and not typer.confirm("proceed?"):
        fail("aborted", why="user did not confirm", hint="pass --yes to skip")

    ssh_run(PVE_HOST, "qm", "clone", str(template), str(new_vmid), "--name", name, "--full")
    ssh_run(PVE_HOST, "qm", "set", str(new_vmid), "--ipconfig0", f"ip={ip}/24,gw={GATEWAY_IP}")
    if ram:
        ssh_run(PVE_HOST, "qm", "set", str(new_vmid), "--memory", str(ram))
    ssh_run(PVE_HOST, "qm", "start", str(new_vmid))

    emit({
        "vmid": new_vmid,
        "name": name,
        "ip": ip,
        "ssh_alias_block": f"Host {name}\n    HostName {ip}\n    User user",
        "next_steps": [
            f"append the ssh_alias_block above to ~/.ssh/config",
            f"utils pve dns {name}.internal {ip}",
            f"utils pve ssh {name} echo ok   # smoke test",
        ],
    })


# ── forward ─────────────────────────────────────────────────────
@app.command(help="Manage PVE iptables PREROUTING port forwards.")
def forward(
    spec: Optional[str] = typer.Argument(None, help="HOST_PORT:VM_IP:VM_PORT"),
    action: str = typer.Option("add", "--action", help="add | list | del"),
    line: Optional[int] = typer.Option(None, "--line", help="Line number for --action del"),
) -> None:
    if action == "list":
        out = ssh_run(PVE_HOST, "iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers")
        emit({"rules": out.splitlines()})
        return

    if action == "del":
        if line is None:
            fail("--line required for del", hint="run `utils pve forward --action list` to find the line number")
        ssh_run(PVE_HOST, "iptables", "-t", "nat", "-D", "PREROUTING", str(line))
        ssh_run(PVE_HOST, "sh", "-c", "iptables-save > /etc/iptables/rules.v4")
        emit({"action": "del", "line": line})
        return

    if action != "add":
        fail(f"unknown action {action!r}", hint="use add | list | del")

    if not spec:
        fail("spec required for add", hint="format: HOST_PORT:VM_IP:VM_PORT (e.g. 8443:10.10.10.42:443)")
    m = re.match(r"^(\d+):([\d.]+):(\d+)$", spec)
    if not m:
        fail(f"bad spec {spec!r}", why="expected HOST_PORT:VM_IP:VM_PORT", hint="e.g. 8443:10.10.10.42:443")
    host_port, vm_ip, vm_port = m.group(1), m.group(2), m.group(3)
    ssh_run(
        PVE_HOST,
        "iptables", "-t", "nat", "-A", "PREROUTING",
        "-p", "tcp", "--dport", host_port,
        "-j", "DNAT", "--to", f"{vm_ip}:{vm_port}",
    )
    ssh_run(PVE_HOST, "sh", "-c", "iptables-save > /etc/iptables/rules.v4")
    emit({"action": "add", "host_port": int(host_port), "vm_ip": vm_ip, "vm_port": int(vm_port)})


# ── dns ─────────────────────────────────────────────────────────
@app.command(help="Add a *.internal record to gateway dnsmasq.")
def dns(
    host: str = typer.Argument(..., help="Hostname (e.g. parser.internal)"),
    ip: str = typer.Argument(..., help="IP"),
) -> None:
    # Append only if not already present; reload dnsmasq.
    check_cmd = f"grep -qE '\\\\b{re.escape(host)}\\\\b' {shlex.quote(GATEWAY_DNS_HOSTS)} && echo present || echo absent"
    present = ssh_run(GATEWAY_HOST, "sh", "-c", check_cmd).strip()
    if present == "present":
        emit({"host": host, "ip": ip, "action": "skipped", "reason": "already in hosts file"})
        return
    ssh_run(GATEWAY_HOST, "sh", "-c", f"echo {shlex.quote(f'{ip} {host}')} >> {shlex.quote(GATEWAY_DNS_HOSTS)}")
    ssh_run(GATEWAY_HOST, "sudo", "systemctl", "reload", "dnsmasq")
    emit({"host": host, "ip": ip, "action": "added"})


# ── caddy ───────────────────────────────────────────────────────
@app.command(help="Add a Caddy reverse-proxy stanza on the gateway.")
def caddy(
    domain: str = typer.Argument(..., help="Public domain (e.g. parser.zyx.tw)"),
    upstream: str = typer.Argument(..., help="Upstream host:port (e.g. 10.10.10.42:8080)"),
) -> None:
    check_cmd = f"grep -qE '^{re.escape(domain)}\\\\b' {shlex.quote(GATEWAY_CADDYFILE)} && echo present || echo absent"
    present = ssh_run(GATEWAY_HOST, "sh", "-c", check_cmd).strip()
    if present == "present":
        emit({"domain": domain, "upstream": upstream, "action": "skipped", "reason": "domain already in Caddyfile"})
        return
    stanza = f"\n{domain} {{\n    reverse_proxy {upstream}\n}}\n"
    ssh_run(GATEWAY_HOST, "sh", "-c", f"printf %s {shlex.quote(stanza)} >> {shlex.quote(GATEWAY_CADDYFILE)}")
    ssh_run(GATEWAY_HOST, "sudo", "caddy", "reload", "--config", GATEWAY_CADDYFILE)
    emit({"domain": domain, "upstream": upstream, "action": "added"})


if __name__ == "__main__":
    app()
