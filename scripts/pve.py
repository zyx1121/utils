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

import base64
import json
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
# Gateway env file (CF_API_TOKEN_ZYX etc.) — loaded for `caddy validate` so {env.*}
# placeholders in tls dns blocks resolve; without it validate rejects the whole config.
GATEWAY_ENV = os.environ.get("UTILS_PVE_GATEWAY_ENV", "/home/user/gateway/.env")
# Gateway runs Caddy natively under systemd (ex-docker). Override for other setups.
CADDY_RELOAD_CMD = os.environ.get("UTILS_PVE_CADDY_RELOAD", "sudo systemctl reload caddy")
VM_BRIDGE = os.environ.get("UTILS_PVE_BRIDGE", "vnet10")
# PVE firewall security group applied to every cloned VM for east-west isolation.
# Empty disables isolation entirely. The group + datacenter master switch are a
# one-time host setup (see SKILL.md); clone only references the group per-VM.
FW_GROUP = os.environ.get("UTILS_PVE_FW_GROUP", "spoke")

app = typer.Typer(
    rich_markup_mode=None,
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


def _ssh_try(host: str, *parts: str) -> subprocess.CompletedProcess:
    """Run a command on `host` via SSH WITHOUT hard-failing — caller inspects returncode.

    Unlike ssh_run (which calls fail() and exits on non-zero), this returns the
    completed process so the caller can react — e.g. roll a Caddyfile back to its
    backup when a reload fails on a config that passed `caddy validate`."""
    remote = " ".join(shlex.quote(str(p)) for p in parts)
    return subprocess.run(["ssh", host, remote], capture_output=True, text=True, check=False)


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
                "type": "qm",
            })
        except ValueError:
            continue
    return vms


def parse_pct_list(output: str) -> list[dict]:
    """Parse `pct list` table. Header: VMID Status Lock Name (Lock may be empty)."""
    lines = output.strip().splitlines()
    cts = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            # Name is the last column; Lock between Status and Name may be absent.
            cts.append({"vmid": int(parts[0]), "name": parts[-1], "status": parts[1], "type": "lxc"})
        except ValueError:
            continue
    return cts


def list_guests() -> list[dict]:
    """All guests on the host — QEMU VMs (`qm`) + LXC containers (`pct`)."""
    return (parse_qm_list(ssh_run(PVE_HOST, "qm", "list"))
            + parse_pct_list(ssh_run(PVE_HOST, "pct", "list")))


def find_guest(name_or_id: str) -> dict:
    """Find a VM or LXC by name/VMID. Returns dict with `type` = qm | lxc."""
    for g in list_guests():
        if g["name"] == name_or_id or str(g["vmid"]) == name_or_id:
            return g
    fail(
        f"no VM or container named {name_or_id!r}",
        why="not in `qm list` or `pct list`",
        hint="run `utils pve list` to see all guests",
    )


def _vm_ip(vmid: int, gtype: str = "qm") -> Optional[str]:
    """Extract a guest's IP. VM: `qm config` ipconfig0; LXC: `pct config` net0. None if unset."""
    cli = "pct" if gtype == "lxc" else "qm"
    key = "net0:" if gtype == "lxc" else "ipconfig0:"
    config_out = ssh_run(PVE_HOST, cli, "config", str(vmid))
    for line in config_out.splitlines():
        if line.startswith(key):
            m = re.search(r"ip=([\d.]+)", line)
            if m:
                return m.group(1)
    return None


def _set_net0(vmid: int, *, bridge: Optional[str] = None, firewall: Optional[bool] = None) -> None:
    """Re-set net0 overriding bridge/firewall while preserving model=mac + other opts.

    qm clone assigns a fresh MAC, so we read the generated net0 back and patch it
    in place rather than reconstructing it (which would lose the MAC)."""
    cfg = ssh_run(PVE_HOST, "qm", "config", str(vmid))
    net0 = next((l.split(":", 1)[1].strip() for l in cfg.splitlines() if l.startswith("net0:")), None)
    if net0 is None:
        fail(f"VM {vmid} has no net0", hint="template must define a network interface")
    order: list[str] = []
    kv: dict[str, Optional[str]] = {}
    for part in net0.split(","):
        k, sep, v = part.partition("=")
        kv[k] = v if sep else None
        order.append(k)
    if bridge is not None:
        if "bridge" not in kv:
            order.append("bridge")
        kv["bridge"] = bridge
    if firewall is not None:
        if "firewall" not in kv:
            order.append("firewall")
        kv["firewall"] = "1" if firewall else "0"
    spec = ",".join(k if kv[k] is None else f"{k}={kv[k]}" for k in order)
    ssh_run(PVE_HOST, "qm", "set", str(vmid), "-net0", spec)


def _write_vm_firewall(vmid: int, group: str) -> None:
    """Write /etc/pve/firewall/<vmid>.fw applying `group` (egress isolation).

    policy_in ACCEPT keeps inbound open (SSH forward + reverse-proxy reach); the
    group's OUT rules are what actually fence the VM off from its peers."""
    fw = (
        "[OPTIONS]\nenable: 1\npolicy_in: ACCEPT\npolicy_out: ACCEPT\n\n"
        f"[RULES]\nGROUP {group}\n"
    )
    ssh_run(PVE_HOST, "sh", "-c",
            f"printf %s {shlex.quote(fw)} > {shlex.quote(f'/etc/pve/firewall/{vmid}.fw')}")


def _remove_vm_firewall(vmid: int) -> bool:
    """Delete /etc/pve/firewall/<vmid>.fw. Returns True if it existed."""
    out = ssh_run(PVE_HOST, "sh", "-c",
                  f"rm -f {shlex.quote(f'/etc/pve/firewall/{vmid}.fw')} && echo done")
    return out.strip() == "done"


# Persist the forward rules for reboot WITHOUT freezing daemon-managed state.
# A blanket `iptables-save` would capture pve-firewall's 150+ filter chains and
# the SDN SNAT into rules.v4, which then fight the daemons that rebuild them on
# boot. Every forward we manage lives in the nat table (which carries no firewall
# chains), so we refresh only the *nat block and leave the rest of rules.v4 — the
# host's static *filter security rules — untouched. The SDN SNAT (`-j SNAT
# --to-source`) is dropped since SDN re-adds it on boot.
_PERSIST_IPTABLES_SH = r"""
F=/etc/iptables/rules.v4
tmp=$(mktemp)
[ -f "$F" ] && awk '/^\*nat$/{n=1; next} n&&/^COMMIT$/{n=0; next} !n' "$F" > "$tmp"
iptables-save -t nat | grep -v 'j SNAT --to-source' >> "$tmp"
mv "$tmp" "$F"
"""


def _persist_iptables() -> None:
    """Persist the nat-table forwards to rules.v4 without capturing firewall/SDN chains."""
    ssh_run(PVE_HOST, "sh", "-c", _PERSIST_IPTABLES_SH)


def _find_forwards_to_ip(vm_ip: str) -> list[dict]:
    """Scan PVE iptables PREROUTING for DNAT rules targeting vm_ip.
    Returns [{"line": N, "dport": host_port, "target_port": vm_port}, ...]."""
    try:
        rules = ssh_run(PVE_HOST, "iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers")
    except SystemExit:
        return []
    matches: list[dict] = []
    for line in rules.splitlines():
        m = re.match(rf"^\s*(\d+)\s.*dpt:(\d+)\b.*to:{re.escape(vm_ip)}:(\d+)", line)
        if m:
            matches.append({
                "line": int(m.group(1)),
                "dport": int(m.group(2)),
                "target_port": int(m.group(3)),
            })
    return matches


def _pve_real_hostname() -> Optional[str]:
    """Resolve PVE_HOST alias to its real hostname via `ssh -G`. None on failure."""
    result = subprocess.run(
        ["ssh", "-G", PVE_HOST], capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("hostname "):
            return line.split(None, 1)[1].strip()
    return None


def _clean_known_hosts(targets: list[str]) -> list[str]:
    """ssh-keygen -R each target, return the ones that had entries to remove."""
    cleaned = []
    for t in targets:
        result = subprocess.run(
            ["ssh-keygen", "-R", t], capture_output=True, text=True, check=False,
        )
        # ssh-keygen prints "Host X found: line N" before removing
        if "found: line" in result.stdout:
            cleaned.append(t)
    return cleaned


def _caddy_reload() -> None:
    """Reload Caddy on the gateway (native systemd; CADDY_RELOAD_CMD)."""
    ssh_run(GATEWAY_HOST, "sh", "-c", CADDY_RELOAD_CMD)


def _dnsmasq_reload() -> None:
    """Reload dnsmasq on the gateway after editing the hosts file."""
    ssh_run(GATEWAY_HOST, "sudo", "systemctl", "reload", "dnsmasq")


def _run_remote_python(host: str, script: str, *args: str) -> str:
    """Run a Python script on a remote host via base64 to avoid quoting hell."""
    b64 = base64.b64encode(script.encode()).decode()
    quoted_args = " ".join(shlex.quote(a) for a in args)
    return ssh_run(
        host, "sh", "-c",
        f"echo {b64} | base64 -d | python3 - {quoted_args}",
    )


def _remove_dns_record(host: str) -> bool:
    """Remove a *.internal record from gateway dnsmasq hosts file by hostname.
    Returns True if the record was present and removed. Caller reloads dnsmasq."""
    check_cmd = (
        f"grep -qE '[[:space:]]{re.escape(host)}([[:space:]]|$)' "
        f"{shlex.quote(GATEWAY_DNS_HOSTS)} && echo present || echo absent"
    )
    if ssh_run(GATEWAY_HOST, "sh", "-c", check_cmd).strip() != "present":
        return False
    # chmod 644 after mv: mktemp creates 600, but dnsmasq (drops to its own
    # user) must be able to read the addn-hosts file. DNS records aren't secret.
    rewrite = (
        f"tmp=$(mktemp) && "
        f"grep -vE '[[:space:]]{re.escape(host)}([[:space:]]|$)' "
        f"{shlex.quote(GATEWAY_DNS_HOSTS)} > $tmp && "
        f"mv $tmp {shlex.quote(GATEWAY_DNS_HOSTS)} && "
        f"chmod 644 {shlex.quote(GATEWAY_DNS_HOSTS)}"
    )
    ssh_run(GATEWAY_HOST, "sh", "-c", rewrite)
    return True


def _find_dns_records_by_ip(vm_ip: str) -> list[dict]:
    """Records on gateway dnsmasq whose first column matches vm_ip."""
    try:
        out = ssh_run(GATEWAY_HOST, "cat", GATEWAY_DNS_HOSTS)
    except SystemExit:
        return []
    records: list[dict] = []
    for raw in out.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2 and parts[0] == vm_ip:
            records.append({"ip": parts[0], "host": parts[1]})
    return records


_CADDY_FIND_BY_IP_SCRIPT = """
import sys, re
path, ip = sys.argv[1], sys.argv[2]
with open(path) as f:
    lines = f.readlines()
domains = []
i = 0
n = len(lines)
while i < n:
    line = lines[i]
    stripped = line.lstrip()
    if '{' in stripped and not stripped.startswith('#'):
        head = stripped.split('{', 1)[0].strip()
        if head:
            doms = [d.strip() for d in head.split(',') if d.strip()]
            depth = line.count('{') - line.count('}')
            block = [line]
            j = i + 1
            while j < n and depth > 0:
                depth += lines[j].count('{') - lines[j].count('}')
                block.append(lines[j])
                j += 1
            if re.search(r'(?<![\\d.])' + re.escape(ip) + r'(:[0-9]+)?(?![\\d.])', ''.join(block)):
                domains.extend(doms)
            i = j
            continue
    i += 1
for d in domains:
    print(d)
"""


def _find_caddy_domains_by_ip(vm_ip: str) -> list[str]:
    """Caddy domain blocks whose reverse_proxy upstream resolves to vm_ip."""
    try:
        out = _run_remote_python(GATEWAY_HOST, _CADDY_FIND_BY_IP_SCRIPT, GATEWAY_CADDYFILE, vm_ip)
    except SystemExit:
        return []
    return [d.strip() for d in out.splitlines() if d.strip()]


def _remove_caddy_domain(domain: str) -> bool:
    """Remove a domain block from gateway Caddyfile. Returns True if removed.
    Caller reloads Caddy."""
    result = _run_remote_python(GATEWAY_HOST, _CADDY_REMOVE_SCRIPT, GATEWAY_CADDYFILE, domain).strip()
    return result == "removed"


def _ssh_config_path() -> Path:
    return Path("~/.ssh/config").expanduser()


def _ssh_config_has_alias(name: str) -> bool:
    config = _ssh_config_path()
    if not config.exists():
        return False
    for line in config.read_text().splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("host ") or stripped.startswith("#"):
            continue
        if name in stripped.split()[1:]:
            return True
    return False


def _remove_ssh_alias(name: str) -> dict:
    """Strip `name` from ~/.ssh/config.

    Standalone `Host <name>` block: drops the Host line and immediately-following
    indented continuation lines, stops at the first non-indented line so adjacent
    blocks and their preceding comments stay intact.

    Shared `Host a b c` line: removes just `name` from the list, leaves the
    block's option lines untouched.
    """
    config = _ssh_config_path()
    if not config.exists():
        return {"changed": False}

    lines = config.read_text().splitlines(keepends=True)
    out: list[str] = []
    removed_block = False
    edited_shared = False
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        is_host = stripped.lower().startswith("host ") and not stripped.startswith("#")
        if is_host:
            hosts = stripped.split()[1:]
            if name in hosts:
                if len(hosts) == 1:
                    i += 1
                    while i < n and lines[i][:1] in (" ", "\t"):
                        i += 1
                    removed_block = True
                    continue
                else:
                    remaining = [h for h in hosts if h != name]
                    indent = line[: len(line) - len(line.lstrip())]
                    nl = "\n" if line.endswith("\n") else ""
                    out.append(f"{indent}Host {' '.join(remaining)}{nl}")
                    edited_shared = True
                    i += 1
                    continue
        out.append(line)
        i += 1

    if removed_block or edited_shared:
        config.write_text("".join(out))
        return {"changed": True, "removed_block": removed_block, "edited_shared": edited_shared}
    return {"changed": False}


# ── list ────────────────────────────────────────────────────────
@app.command("list", help="List all guests on the PVE host — QEMU VMs + LXC containers.")
def list_vms() -> None:
    guests = list_guests()

    def human(data, _meta):
        t = Table(show_header=True, header_style="bold")
        t.add_column("VMID")
        t.add_column("Name")
        t.add_column("Type")
        t.add_column("Status")
        t.add_column("Mem")
        for v in data:
            style = "green" if v["status"] == "running" else "dim"
            mem = f"{v['mem_mb']}MB" if v.get("mem_mb") else "-"
            t.add_row(str(v["vmid"]), v["name"], v["type"], v["status"], mem, style=style)
        console.print(t)

    emit(guests, {"count": len(guests), "host": PVE_HOST}, human=human)


# ── status ──────────────────────────────────────────────────────
@app.command(help="Show config + status for a VM or container by name or VMID.")
def status(name: str = typer.Argument(..., help="VM/CT name or VMID")) -> None:
    vm = find_guest(name)
    cli = "pct" if vm["type"] == "lxc" else "qm"
    config_out = ssh_run(PVE_HOST, cli, "config", str(vm["vmid"]))
    info = {"vmid": vm["vmid"], "name": vm["name"], "type": vm["type"], "status": vm["status"]}
    keep = {"cores", "memory", "ostype", "ipconfig0", "ciuser",
            "nameserver", "searchdomain", "net0", "scsi0",
            "hostname", "rootfs", "onboot"}  # rootfs/hostname/onboot for LXC
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
@app.command(help="Start a VM or container.")
def start(name: str = typer.Argument(..., help="VM/CT name or VMID")) -> None:
    vm = find_guest(name)
    cli = "pct" if vm["type"] == "lxc" else "qm"
    ssh_run(PVE_HOST, cli, "start", str(vm["vmid"]))
    emit({"vmid": vm["vmid"], "name": vm["name"], "type": vm["type"], "action": "start"})


@app.command(help="Stop a VM or container.")
def stop(
    name: str = typer.Argument(..., help="VM/CT name or VMID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    vm = find_guest(name)
    cli = "pct" if vm["type"] == "lxc" else "qm"
    if not yes and not typer.confirm(f"stop {vm['type']} {vm['name']!r} (VMID {vm['vmid']})?"):
        fail("aborted", why="user did not confirm", hint="pass --yes to skip")
    ssh_run(PVE_HOST, cli, "stop", str(vm["vmid"]))
    emit({"vmid": vm["vmid"], "name": vm["name"], "type": vm["type"], "action": "stop"})


# ── destroy ─────────────────────────────────────────────────────
@app.command(help="Destroy a VM permanently — cascades: port forwards, DNS, Caddy, SSH alias, known_hosts.")
def destroy(
    name: str = typer.Argument(..., help="VM name or VMID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    vm = find_guest(name)
    cli = "pct" if vm["type"] == "lxc" else "qm"
    vm_ip = _vm_ip(vm["vmid"], vm["type"])

    forwards = _find_forwards_to_ip(vm_ip) if vm_ip else []
    ssh_forward_port = next((f["dport"] for f in forwards if f["target_port"] == 22), None)
    dns_records = _find_dns_records_by_ip(vm_ip) if vm_ip else []
    caddy_domains = _find_caddy_domains_by_ip(vm_ip) if vm_ip else []
    has_ssh_alias = _ssh_config_has_alias(vm["name"])

    plan_bits = [f"DESTROY {vm['type']} {vm['name']!r} (VMID {vm['vmid']})"]
    if vm_ip:
        plan_bits.append(f"IP {vm_ip}")
    if vm["status"] == "running":
        plan_bits.append("will stop first")
    plan_bits.append("disks + config purged, irreversible")
    console.print(f"[red]{' — '.join(plan_bits)}[/]")

    cascade: list[str] = []
    if forwards:
        cascade.append(f"{len(forwards)} port forward rule(s) → {vm_ip}")
    if dns_records:
        cascade.append(f"DNS: {', '.join(r['host'] for r in dns_records)}")
    if caddy_domains:
        cascade.append(f"Caddy: {', '.join(caddy_domains)}")
    if has_ssh_alias:
        cascade.append(f"SSH alias {vm['name']!r}")
    if cascade:
        console.print(f"[red]cascade cleanup: {'; '.join(cascade)}[/]")

    if not yes and not typer.confirm("proceed?"):
        fail("aborted", why="user did not confirm", hint="pass --yes to skip")

    if vm["status"] == "running":
        ssh_run(PVE_HOST, cli, "stop", str(vm["vmid"]))

    ssh_run(
        PVE_HOST, cli, "destroy", str(vm["vmid"]),
        "--purge", "--destroy-unreferenced-disks", "1",
    )

    forwards_removed: list[dict] = []
    for f in sorted(forwards, key=lambda x: x["line"], reverse=True):
        ssh_run(PVE_HOST, "iptables", "-t", "nat", "-D", "PREROUTING", str(f["line"]))
        forwards_removed.append({"dport": f["dport"], "target_port": f["target_port"]})
    if forwards:
        _persist_iptables()

    dns_removed: list[str] = []
    for r in dns_records:
        if _remove_dns_record(r["host"]):
            dns_removed.append(r["host"])
    if dns_removed:
        _dnsmasq_reload()

    caddy_removed: list[str] = []
    for domain in caddy_domains:
        if _remove_caddy_domain(domain):
            caddy_removed.append(domain)
    if caddy_removed:
        _caddy_reload()

    firewall_removed = _remove_vm_firewall(vm["vmid"])

    ssh_alias_result = _remove_ssh_alias(vm["name"]) if has_ssh_alias else {"changed": False}

    targets: list[str] = [vm["name"]]
    if vm_ip:
        targets.append(vm_ip)
    if ssh_forward_port:
        host = _pve_real_hostname()
        if host:
            targets.append(f"[{host}]:{ssh_forward_port}")
    cleaned = _clean_known_hosts(targets)

    emit({
        "vmid": vm["vmid"],
        "name": vm["name"],
        "ip": vm_ip,
        "action": "destroy",
        "forwards_removed": forwards_removed,
        "dns_removed": dns_removed,
        "caddy_removed": caddy_removed,
        "firewall_removed": firewall_removed,
        "ssh_alias_removed": ssh_alias_result.get("changed", False),
        "known_hosts_cleaned": cleaned,
    })


# ── ssh ─────────────────────────────────────────────────────────
@app.command(name="ssh", help="SSH to a VM — refuses if alias is missing.")
def ssh_cmd(
    name: str = typer.Argument(..., help="VM name (must match ~/.ssh/config Host alias)"),
    command: Optional[list[str]] = typer.Argument(None, help="Optional remote command"),
) -> None:
    if not _ssh_config_has_alias(name):
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
@app.command(help="Clone from template, set IP + auto-add 50<vmid>:22 SSH forward; prints SSH alias to add.")
def clone(
    name: str = typer.Argument(..., help="New VM name"),
    ip: Optional[str] = typer.Option(None, "--ip", help="Internal IP (default: <subnet>.<VMID>, derived from UTILS_PVE_GATEWAY_IP)"),
    template: int = typer.Option(PVE_TEMPLATE, "--template", help="Source template VMID"),
    vmid: Optional[int] = typer.Option(None, "--vmid", help="Target VMID (default: next free ≥100)"),
    cores: Optional[int] = typer.Option(None, "--cores", help="Override template cores"),
    ram: Optional[int] = typer.Option(None, "--ram", help="Override template RAM (MB)"),
    disk: Optional[int] = typer.Option(None, "--disk", help="Resize scsi0 to N GB (must be ≥ template size)"),
    no_forward: bool = typer.Option(False, "--no-forward", help="Skip the auto-added 50<vmid>:22 external SSH forward"),
    no_isolate: bool = typer.Option(False, "--no-isolate", help=f"Skip east-west isolation (firewall=1 + {FW_GROUP!r} group)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    existing = {v["vmid"] for v in parse_qm_list(ssh_run(PVE_HOST, "qm", "list"))}
    if vmid is not None:
        if vmid in existing:
            fail(f"VMID {vmid} already in use", hint="run `utils pve list` to see allocated IDs")
        new_vmid = vmid
    else:
        new_vmid = 100
        while new_vmid in existing:
            new_vmid += 1

    if ip is None:
        prefix_parts = GATEWAY_IP.split(".")
        if len(prefix_parts) != 4 or not (1 <= new_vmid <= 254):
            fail(
                f"can't auto-derive IP for VMID {new_vmid}",
                why=f"convention is <subnet>.<VMID> with VMID in 1-254 and a v4 subnet (GATEWAY_IP={GATEWAY_IP!r})",
                hint="pass --ip explicitly or pick a VMID in 100-254",
            )
        ip = f"{'.'.join(prefix_parts[:3])}.{new_vmid}"

    forward_port = 50000 + new_vmid
    add_forward = not no_forward and 1 <= forward_port <= 65535
    isolate = not no_isolate and bool(FW_GROUP)

    plan = f"clone template {template} → VMID {new_vmid} as {name!r}, IP {ip}/24, gw {GATEWAY_IP}, bridge {VM_BRIDGE}"
    if cores:
        plan += f", cores {cores}"
    if ram:
        plan += f", RAM {ram}MB"
    if disk:
        plan += f", disk {disk}GB"
    if add_forward:
        plan += f", SSH forward :{forward_port}→{ip}:22"
    if isolate:
        plan += f", isolated (firewall=1 + {FW_GROUP!r})"
    console.print(plan)
    if not yes and not typer.confirm("proceed?"):
        fail("aborted", why="user did not confirm", hint="pass --yes to skip")

    ssh_run(PVE_HOST, "qm", "clone", str(template), str(new_vmid), "--name", name, "--full")
    ssh_run(PVE_HOST, "qm", "set", str(new_vmid), "--ipconfig0", f"ip={ip}/24,gw={GATEWAY_IP}")
    if cores:
        ssh_run(PVE_HOST, "qm", "set", str(new_vmid), "--cores", str(cores))
    if ram:
        ssh_run(PVE_HOST, "qm", "set", str(new_vmid), "--memory", str(ram))
    if disk:
        ssh_run(PVE_HOST, "qm", "resize", str(new_vmid), "scsi0", f"{disk}G")
    # Bridge + isolation are baked in before first boot: the VM comes up on the
    # right network already fenced off from its peers, never momentarily open.
    _set_net0(new_vmid, bridge=VM_BRIDGE, firewall=isolate)
    if isolate:
        _write_vm_firewall(new_vmid, FW_GROUP)
    ssh_run(PVE_HOST, "qm", "start", str(new_vmid))

    if add_forward:
        ssh_run(
            PVE_HOST,
            "iptables", "-t", "nat", "-A", "PREROUTING",
            "-p", "tcp", "--dport", str(forward_port),
            "-j", "DNAT", "--to", f"{ip}:22",
        )
        _persist_iptables()

    emit({
        "vmid": new_vmid,
        "name": name,
        "ip": ip,
        "bridge": VM_BRIDGE,
        "isolated": isolate,
        "firewall_group": FW_GROUP if isolate else None,
        "cores": cores,
        "ram_mb": ram,
        "disk_gb": disk,
        "ssh_forward_port": forward_port if add_forward else None,
        "ssh_alias_block": f"Host {name}\n  Port {forward_port}" if add_forward else None,
        "ssh_alias_note": (
            f"add the ssh_alias_block to ~/.ssh/config, then add `{name}` to the shared "
            f"per-VM `Host a b c ...` block (HostName = PVE external IP, User, IdentityFile)"
        ) if add_forward else None,
        "next_steps": [
            *( ["edit ~/.ssh/config per ssh_alias_block + ssh_alias_note"] if add_forward else [] ),
            f"utils pve dns {name}.internal {ip}",
            f"ssh -o StrictHostKeyChecking=accept-new {name} echo ok   # smoke test",
        ],
    })


# ── create-ct ───────────────────────────────────────────────────
# Default template: prefer UTILS_PVE_CT_TEMPLATE env; fall back to the
# standard ubuntu-24.04 vztmpl that ships on every fresh Proxmox local storage.
_CT_TEMPLATE_DEFAULT = os.environ.get(
    "UTILS_PVE_CT_TEMPLATE",
    "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst",
)


@app.command("create-ct", help="Create a new LXC container from a vztmpl; wires 50<vmid>:22 forward + spoke isolation (mirror of clone but pct-native).")
def create_ct(
    name: str = typer.Argument(..., help="Hostname for the new container"),
    template: str = typer.Option(_CT_TEMPLATE_DEFAULT, "--template", envvar="UTILS_PVE_CT_TEMPLATE", help="vztmpl volid (default: ubuntu-24.04-standard)"),
    vmid: Optional[int] = typer.Option(None, "--vmid", help="Target VMID (default: next free ≥200)"),
    ip: Optional[str] = typer.Option(None, "--ip", help="Internal IP (default: <subnet>.<VMID>)"),
    cores: int = typer.Option(2, "--cores", help="Number of CPU cores"),
    ram: int = typer.Option(2048, "--ram", help="RAM in MB"),
    disk: int = typer.Option(8, "--disk", help="Root filesystem size in GB"),
    swap: int = typer.Option(4096, "--swap", help="Swap in MB (default: 4096)"),
    storage: str = typer.Option("local-lvm", "--storage", help="Storage pool for rootfs"),
    unprivileged: bool = typer.Option(True, "--unprivileged/--privileged", help="Run as unprivileged container (default: true)"),
    nesting: bool = typer.Option(False, "--nesting/--no-nesting", help="Enable nesting feature (default: false)"),
    no_forward: bool = typer.Option(False, "--no-forward", help="Skip the auto-added 50<vmid>:22 SSH forward"),
    no_isolate: bool = typer.Option(False, "--no-isolate", help=f"Skip east-west isolation (spoke firewall group {FW_GROUP!r})"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    # Collect all allocated VMIDs (both QEMU VMs + LXC containers).
    all_guests = list_guests()
    existing_ids = {g["vmid"] for g in all_guests}

    if vmid is not None:
        if vmid in existing_ids:
            fail(f"VMID {vmid} already in use", hint="run `utils pve list` to see allocated IDs")
        new_vmid = vmid
    else:
        # LXC lives in the 2xx segment (200-299).
        new_vmid = 200
        while new_vmid in existing_ids:
            new_vmid += 1

    if ip is None:
        prefix_parts = GATEWAY_IP.split(".")
        if len(prefix_parts) != 4 or not (1 <= new_vmid <= 254):
            fail(
                f"can't auto-derive IP for VMID {new_vmid}",
                why=f"convention is <subnet>.<VMID> with VMID in 1-254 (GATEWAY_IP={GATEWAY_IP!r})",
                hint="pass --ip explicitly or pick a VMID in 200-254",
            )
        ip = f"{'.'.join(prefix_parts[:3])}.{new_vmid}"

    forward_port = 50000 + new_vmid
    add_forward = not no_forward and 1 <= forward_port <= 65535
    isolate = not no_isolate and bool(FW_GROUP)
    unpriv_flag = 1 if unprivileged else 0

    plan = (
        f"create-ct VMID {new_vmid} as {name!r}, template {template}, "
        f"IP {ip}/24, gw {GATEWAY_IP}, bridge {VM_BRIDGE}, "
        f"cores {cores}, RAM {ram}MB, disk {disk}GB, swap {swap}MB, "
        f"{'unprivileged' if unprivileged else 'privileged'}"
    )
    if nesting:
        plan += ", nesting=1"
    if add_forward:
        plan += f", SSH forward :{forward_port}→{ip}:22"
    if isolate:
        plan += f", isolated (spoke firewall group {FW_GROUP!r})"
    console.print(plan)
    if not yes and not typer.confirm("proceed?"):
        fail("aborted", why="user did not confirm", hint="pass --yes to skip")

    # Build pct create argument list. net0 is set inline (no _set_net0 — that's qm-only).
    net0_spec = (
        f"name=eth0,bridge={VM_BRIDGE},ip={ip}/24,gw={GATEWAY_IP},"
        f"firewall={'1' if isolate else '0'}"
    )
    pct_create_args = [
        "pct", "create", str(new_vmid), template,
        "--hostname", name,
        "--rootfs", f"{storage}:{disk}",
        "--cores", str(cores),
        "--memory", str(ram),
        "--swap", str(swap),
        "--unprivileged", str(unpriv_flag),
        "--net0", net0_spec,
        "--onboot", "1",
    ]
    if nesting:
        pct_create_args += ["--features", "nesting=1"]

    ssh_run(PVE_HOST, *pct_create_args)

    # Write spoke firewall file before first start — container comes up already fenced.
    if isolate:
        _write_vm_firewall(new_vmid, FW_GROUP)

    ssh_run(PVE_HOST, "pct", "start", str(new_vmid))

    # swappiness is a host-level sysctl (not namespaced); set once on the PVE host,
    # all CTs inherit. --swap above gives the cgroup swap limit.

    if add_forward:
        ssh_run(
            PVE_HOST,
            "iptables", "-t", "nat", "-A", "PREROUTING",
            "-p", "tcp", "--dport", str(forward_port),
            "-j", "DNAT", "--to", f"{ip}:22",
        )
        _persist_iptables()

    emit({
        "vmid": new_vmid,
        "name": name,
        "type": "lxc",
        "ip": ip,
        "bridge": VM_BRIDGE,
        "template": template,
        "cores": cores,
        "ram_mb": ram,
        "disk_gb": disk,
        "swap_mb": swap,
        "unprivileged": unprivileged,
        "nesting": nesting,
        "isolated": isolate,
        "firewall_group": FW_GROUP if isolate else None,
        "ssh_forward_port": forward_port if add_forward else None,
        "ssh_alias_block": f"Host {name}\n  Port {forward_port}" if add_forward else None,
        "ssh_alias_note": (
            f"add the ssh_alias_block to ~/.ssh/config, then add `{name}` to the shared "
            f"per-VM `Host a b c ...` block (HostName = PVE external IP, User, IdentityFile)"
        ) if add_forward else None,
        "next_steps": [
            *( ["edit ~/.ssh/config per ssh_alias_block + ssh_alias_note"] if add_forward else [] ),
            f"utils pve dns {name}.internal {ip}",
            f"ssh -o StrictHostKeyChecking=accept-new {name} echo ok   # smoke test (sshd present in ubuntu-24.04-standard)",
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
        _persist_iptables()
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
    _persist_iptables()
    emit({"action": "add", "host_port": int(host_port), "vm_ip": vm_ip, "vm_port": int(vm_port)})


# ── dns ─────────────────────────────────────────────────────────
@app.command(help="Manage *.internal records in gateway dnsmasq.")
def dns(
    host: Optional[str] = typer.Argument(None, help="Hostname (required for add/remove)"),
    ip: Optional[str] = typer.Argument(None, help="IP (required for add)"),
    action: str = typer.Option("add", "--action", help="add | remove | list"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show planned change without applying (add only)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    if action == "list":
        out = ssh_run(GATEWAY_HOST, "cat", GATEWAY_DNS_HOSTS)
        records = []
        for line in out.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                records.append({"ip": parts[0], "host": parts[1]})
        emit({"records": records, "hosts_file": GATEWAY_DNS_HOSTS})
        return

    if not host:
        fail("host required", hint="utils pve dns <hostname> ...")

    if action == "remove":
        if not yes and not typer.confirm(f"remove DNS record for {host!r}?"):
            fail("aborted", why="user did not confirm", hint="pass --yes to skip")
        if not _remove_dns_record(host):
            emit({"host": host, "action": "skipped", "reason": "not in hosts file"})
            return
        _dnsmasq_reload()
        emit({"host": host, "action": "removed"})
        return

    if action != "add":
        fail(f"unknown action {action!r}", hint="use add | remove | list")

    # add (existing behavior)
    if not ip:
        fail("ip required for add", hint="utils pve dns <hostname> <ip>")
    check_cmd = f"grep -qE '\\\\b{re.escape(host)}\\\\b' {shlex.quote(GATEWAY_DNS_HOSTS)} && echo present || echo absent"
    present = ssh_run(GATEWAY_HOST, "sh", "-c", check_cmd).strip()
    if present == "present":
        emit({"host": host, "ip": ip, "action": "skipped", "reason": "already in hosts file"})
        return

    plan = f"append `{ip} {host}` to {GATEWAY_DNS_HOSTS} on {GATEWAY_HOST} + reload dnsmasq"
    if dry_run:
        emit({"host": host, "ip": ip, "action": "dry-run", "plan": plan})
        return
    console.print(plan)
    if not yes and not typer.confirm("proceed?"):
        fail("aborted", why="user did not confirm", hint="pass --yes to skip")

    ssh_run(GATEWAY_HOST, "sh", "-c",
            f"echo {shlex.quote(f'{ip} {host}')} >> {shlex.quote(GATEWAY_DNS_HOSTS)} && "
            f"chmod 644 {shlex.quote(GATEWAY_DNS_HOSTS)}")
    ssh_run(GATEWAY_HOST, "sudo", "systemctl", "reload", "dnsmasq")
    emit({"host": host, "ip": ip, "action": "added"})


# ── caddy ───────────────────────────────────────────────────────
_CADDY_REMOVE_SCRIPT = """
import sys
path, domain = sys.argv[1], sys.argv[2]
with open(path) as f:
    lines = f.readlines()
out, skip, depth, removed = [], False, 0, False
for line in lines:
    stripped = line.lstrip()
    head = stripped.split('{', 1)[0].strip() if '{' in stripped else ''
    domains = [d.strip() for d in head.split(',')] if head else []
    if not skip and domain in domains and '{' in line:
        skip = True
        removed = True
        depth = line.count('{') - line.count('}')
        continue
    if skip:
        depth += line.count('{') - line.count('}')
        if depth <= 0:
            skip = False
        continue
    out.append(line)
while out and out[-1].strip() == '':
    out.pop()
if out:
    out.append('\\n')
with open(path, 'w') as f:
    f.writelines(out)
print('removed' if removed else 'not_found')
"""


# Shared brace-depth block walker — the single source of truth for "what is a
# top-level domain block", so list / upsert agree with find-by-ip / remove (which
# already walk this way). Skips the global `{ ... }` options block (empty head)
# and column-0 comments. Prepended to the list + upsert remote scripts.
_CADDY_WALK_PRELUDE = """
import sys, os, re, json, subprocess

def parse_blocks(lines):
    out = []
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].lstrip()
        if '{' in stripped and not stripped.startswith('#'):
            head = stripped.split('{', 1)[0].strip()
            if head:
                heads = [d.strip() for d in head.split(',') if d.strip()]
                depth = lines[i].count('{') - lines[i].count('}')
                j = i + 1
                while j < n and depth > 0:
                    depth += lines[j].count('{') - lines[j].count('}')
                    j += 1
                out.append((heads, i, j))
                i = j
                continue
        i += 1
    return out
"""

_CADDY_LIST_SCRIPT = _CADDY_WALK_PRELUDE + """
with open(sys.argv[1]) as f:
    lines = f.readlines()
out = []
for heads, s, e in parse_blocks(lines):
    block = ''.join(lines[s:e])
    out.append({
        'domains': heads,
        'upstreams': re.findall(r'reverse_proxy\\s+(\\S+)', block),
        'tls': bool(re.search(r'(?m)^\\s*tls\\s+', block)),
        'routed': ('handle' in block) or ('@' in block),
    })
print(json.dumps(out))
"""

# One remote round-trip does read -> splice -> fmt -> validate -> atomic swap, so
# there is no time-of-check/time-of-use window between separate ssh calls. The spec
# is a single JSON argv (base64'd by _run_remote_python), so domains/paths/bodies are
# never interpolated into a shell. Always prints ONE json line and exits 0 — status
# is in the payload, not the exit code (so ssh_run does not hard-fail on rejections).
_CADDY_UPSERT_SCRIPT = _CADDY_WALK_PRELUDE + """
def caddy_bin():
    import shutil
    for p in ('/usr/bin/caddy', '/usr/local/bin/caddy'):
        if os.path.exists(p):
            return p
    return shutil.which('caddy')

def render(domains, head_body):
    body = head_body.replace('\\r\\n', '\\n').split('\\n')
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    inner = '\\n'.join(('\\t' + ln.rstrip()) if ln.strip() else '' for ln in body)
    return ', '.join(domains) + ' {\\n' + inner + '\\n}\\n'

spec = json.loads(sys.argv[1])
path = spec['path']
domains = spec['domains']
on_exists = spec.get('on_exists', 'update')
dry_run = bool(spec.get('dry_run', False))
allow_shrink = bool(spec.get('allow_shrink', False))
new_block = render(domains, spec['head_body'])

# Load the gateway env file (e.g. CF_API_TOKEN_ZYX) so `caddy validate` can resolve
# {env.*} placeholders in tls dns blocks — without it the cloudflare DNS provider
# sees an empty token and rejects the whole config.
caddy_env = dict(os.environ)
_envf = spec.get('env_file')
if _envf and os.path.exists(_envf):
    for _ln in open(_envf):
        _ln = _ln.strip()
        if _ln and not _ln.startswith('#') and '=' in _ln:
            _k, _v = _ln.split('=', 1)
            caddy_env[_k.strip()] = _v.strip().strip('"').strip("'")

with open(path) as f:
    lines = f.readlines()
want = set(domains)
matches = [(h, s, e) for h, s, e in parse_blocks(lines) if want & set(h)]
if len(matches) > 1:
    print(json.dumps({'status': 'multi-block', 'blocks': [m[0] for m in matches]})); sys.exit(0)
match = matches[0] if matches else None

if match is not None:
    heads, s, e = match
    if on_exists == 'skip':
        print(json.dumps({'status': 'exists', 'head': heads})); sys.exit(0)
    if on_exists == 'fail':
        print(json.dumps({'status': 'error', 'head': heads})); sys.exit(0)
    dropped = sorted(set(heads) - want)
    if dropped and not dry_run and not allow_shrink:
        print(json.dumps({'status': 'would-shrink', 'head': heads, 'dropped': dropped})); sys.exit(0)
    new_lines = lines[:s] + [new_block] + lines[e:]
    action, shrunk = 'update', (dropped or None)
else:
    body = lines[:]
    while body and body[-1].strip() == '':
        body.pop()
    new_lines = body + (['\\n'] if body else []) + [new_block]
    action, shrunk = 'add', None

new_text = ''.join(new_lines)
tmp = os.path.join(os.path.dirname(os.path.abspath(path)), '.caddy.utils.tmp.%d' % os.getpid())
with open(tmp, 'w') as f:
    f.write(new_text)
os.chmod(tmp, 0o644)

cb = caddy_bin()
validated = False
if cb:
    subprocess.run([cb, 'fmt', '--overwrite', tmp], capture_output=True, text=True)
    vr = subprocess.run([cb, 'validate', '--config', tmp, '--adapter', 'caddyfile'],
                        capture_output=True, text=True, env=caddy_env)
    if vr.returncode != 0:
        os.remove(tmp)
        print(json.dumps({'status': 'invalid', 'error': (vr.stderr or vr.stdout).strip()[-2000:]}))
        sys.exit(0)
    validated = True
    with open(tmp) as f:
        new_text = f.read()

with open(path) as f:
    cur = f.read()
# Compare against a fmt'd copy of the live file so a true no-op is detected even when
# the live file carries pre-existing non-canonical formatting (else we'd reformat the
# whole file + reload for nothing).
cur_cmp = cur
if cb:
    ctmp = tmp + '.cur'
    with open(ctmp, 'w') as f:
        f.write(cur)
    subprocess.run([cb, 'fmt', '--overwrite', ctmp], capture_output=True, text=True)
    with open(ctmp) as f:
        cur_cmp = f.read()
    os.remove(ctmp)
if new_text == cur_cmp:
    os.remove(tmp)
    print(json.dumps({'status': 'unchanged', 'head': domains})); sys.exit(0)

if dry_run:
    import difflib
    diff = ''.join(difflib.unified_diff(cur.splitlines(True), new_text.splitlines(True),
                                         'live/Caddyfile', 'proposed/Caddyfile'))
    os.remove(tmp)
    print(json.dumps({'status': 'dry-run', 'action': action, 'validated': validated,
                      'head': domains, 'shrunk_from': shrunk, 'diff': diff[:6000]}))
    sys.exit(0)

bak = path + '.utils.bak'
try:
    with open(bak, 'w') as fb:
        fb.write(cur)
except Exception:
    bak = None
os.replace(tmp, path)
print(json.dumps({'status': 'written', 'action': action, 'validated': validated,
                  'head': domains, 'shrunk_from': shrunk, 'backup': bak}))
"""

_CADDY_RESTORE_SCRIPT = """
import sys, os
path, bak = sys.argv[1], sys.argv[2]
if os.path.exists(bak):
    os.replace(bak, path)
    print('restored')
else:
    print('no_backup')
"""


def _caddy_list_blocks() -> list[dict]:
    """Top-level Caddy blocks with per-block detail (domains / upstreams / tls / routed)."""
    out = _run_remote_python(GATEWAY_HOST, _CADDY_LIST_SCRIPT, GATEWAY_CADDYFILE)
    try:
        return json.loads(out.strip() or "[]")
    except json.JSONDecodeError:
        return []


def _caddy_upsert(domains: list[str], head_body: str, on_exists: str,
                  dry_run: bool, allow_shrink: bool = False) -> dict:
    """Render + validate + atomically swap a domain block on the gateway. Returns the
    status payload; does NOT reload (caller reloads so it can roll back on failure)."""
    spec = {"path": GATEWAY_CADDYFILE, "domains": domains, "head_body": head_body,
            "on_exists": on_exists, "dry_run": dry_run, "allow_shrink": allow_shrink,
            "env_file": GATEWAY_ENV}
    out = _run_remote_python(GATEWAY_HOST, _CADDY_UPSERT_SCRIPT, json.dumps(spec))
    last = (out.strip().splitlines() or [""])[-1]
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        fail("could not parse caddy upsert result", why=out[:500],
             hint="run `ssh gateway` and inspect the Caddyfile by hand")


def _caddy_reload_or_restore(backup: Optional[str]) -> None:
    """Reload Caddy; if reload fails (e.g. a config that passed `caddy validate` but
    references an unreadable cert path), restore the backup, reload last-good, then fail."""
    r = _ssh_try(GATEWAY_HOST, "sh", "-c", CADDY_RELOAD_CMD)
    if r.returncode == 0:
        # Reload is good — the transient backup is no longer needed. Remove it so it
        # doesn't linger as an untracked file in the gateway's git checkout.
        if backup:
            _ssh_try(GATEWAY_HOST, "rm", "-f", backup)
        return
    restored = False
    if backup:
        _run_remote_python(GATEWAY_HOST, _CADDY_RESTORE_SCRIPT, GATEWAY_CADDYFILE, backup)
        _ssh_try(GATEWAY_HOST, "sh", "-c", CADDY_RELOAD_CMD)
        restored = True
    fail("caddy reload failed" + (" — restored backup" if restored else ""),
         why=(r.stderr or "").strip()[-500:] or "reload returned non-zero",
         hint="likely an unreadable --tls cert path; see `ssh gateway journalctl -u caddy`")


def _caddy_fail_if_bad(res: dict, heads: list[str]) -> None:
    """Map the terminal-error upsert statuses to a clean fail(). Applied to every
    upsert result (incl. the post-confirm shrink re-run) so none slips through."""
    status = res.get("status")
    if status == "invalid":
        fail("caddy validate rejected the block",
             why=res.get("error", "").strip()[-800:],
             hint="fix the directives / --body; the live Caddyfile was not touched")
    if status == "error":
        fail(f"domain already in Caddyfile: {', '.join(res.get('head', heads))}",
             hint="--on-exists update to replace it, or remove it first")
    if status == "multi-block":
        blocks = res.get("blocks", [])
        fail(f"{', '.join(heads)} spans {len(blocks)} separate Caddy blocks",
             why="; ".join(", ".join(b) for b in blocks),
             hint="these hostnames live in different stanzas — remove them first, or target one block's hostnames")


@app.command(help="Manage Caddy reverse-proxy stanzas on the gateway.")
def caddy(
    domain: Optional[str] = typer.Argument(
        None, help="Public domain head. Comma-join for one multi-host block: 'a.tw,*.a.tw'. Required for add/remove."),
    upstream: Optional[str] = typer.Argument(
        None, help="Upstream host:port (simple form). Mutually exclusive with --body."),
    action: str = typer.Option("add", "--action", help="add | remove | list"),
    tls: Optional[str] = typer.Option(
        None, "--tls", help="TLS for the simple form: two paths 'CERT KEY', or 'internal'. Not valid with --body."),
    body: Optional[str] = typer.Option(
        None, "--body", help="Escape hatch: verbatim block body (matchers / handle / headers / anything). '-' reads stdin. Excludes upstream + --tls."),
    on_exists: str = typer.Option(
        "update", "--on-exists", help="When the domain block already exists: update (replace, default) | skip | fail."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Render + validate on a scratch copy and show the diff; write nothing."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for remove / for replacing or shrinking an existing block."),
) -> None:
    if action == "list":
        blocks = _caddy_list_blocks()
        domains = [d for b in blocks for d in b.get("domains", [])]
        emit({"domains": domains, "blocks": blocks, "caddyfile": GATEWAY_CADDYFILE})
        return

    if not domain:
        fail("domain required", hint="utils pve caddy <domain> ...")
    heads = [d.strip() for d in domain.split(",") if d.strip()]
    for h in heads:
        if not re.fullmatch(r"[A-Za-z0-9*._-]+", h):
            fail(f"invalid domain token {h!r}",
                 why="whitespace / braces / shell metacharacters are not allowed in a domain head",
                 hint="comma-join hostnames with no spaces: 'a.tw,*.a.tw'")

    if action == "remove":
        if not yes and not typer.confirm(f"remove Caddy block for {domain!r}?"):
            fail("aborted", why="user did not confirm", hint="pass --yes to skip")
        # Match by any single head token — the remove script deletes the whole block
        # once one of its hostnames matches, so a comma-joined arg works via heads[0].
        if not _remove_caddy_domain(heads[0]):
            emit({"domain": domain, "action": "skipped", "reason": "domain not in Caddyfile"})
            return
        _caddy_reload()
        emit({"domain": domain, "action": "removed"})
        return

    if action != "add":
        fail(f"unknown action {action!r}", hint="use add | remove | list")
    if on_exists not in ("update", "skip", "fail"):
        fail(f"invalid --on-exists {on_exists!r}", hint="update | skip | fail")

    # Resolve the block body: simple form (upstream [+ --tls]) XOR escape hatch (--body).
    body_from_stdin = False
    if body is not None:
        if upstream:
            fail("give an upstream OR --body, not both", hint="--body is the escape hatch for a full block body")
        if tls:
            fail("--tls is only for the simple form", hint="put the `tls` directive inside --body yourself")
        if body == "-":
            if _sys.stdin.isatty():
                fail("--body - expects piped input", hint="echo '...' | utils pve caddy <domain> --body -")
            raw = _sys.stdin.read()
            body_from_stdin = True
        else:
            raw = body
        if not raw.strip():
            fail("--body is empty", hint="pass block-body text, or pipe it via `--body -`")
        head_body = raw
    else:
        if not upstream:
            fail("upstream required for add", hint="utils pve caddy <domain> <host:port>  (or --body for a full block)")
        # The simple form splices `reverse_proxy <upstream>` verbatim — keep it to a single
        # host:port token so it can't smuggle braces/newlines that mint a second site block
        # (caddy validate would accept the resulting valid-but-unintended config).
        if not re.fullmatch(r"[A-Za-z0-9_.:/%\[\]-]+", upstream):
            fail(f"invalid upstream {upstream!r}",
                 why="want a single host:port token — no whitespace / braces / newlines",
                 hint="use --body for anything richer than one reverse_proxy upstream")
        tls_line = ""
        if tls:
            toks = tls.split()
            if toks == ["internal"]:
                tls_line = "tls internal\n"
            elif len(toks) == 2 and all(t.startswith("/") for t in toks):
                tls_line = f"tls {toks[0]} {toks[1]}\n"
            else:
                fail("invalid --tls",
                     why="want the literal 'internal' or two absolute paths 'CERT KEY'",
                     hint='--tls "/etc/caddy/certs/x/fullchain.pem /etc/caddy/certs/x/privkey.pem"')
        head_body = f"{tls_line}reverse_proxy {upstream}"

    res = _caddy_upsert(heads, head_body, on_exists, dry_run)
    _caddy_fail_if_bad(res, heads)
    status = res.get("status")

    if status == "exists":
        emit({"domains": heads, "action": "skipped", "reason": "already present (--on-exists skip)"})
        return
    if status == "would-shrink":
        dropped = res.get("dropped", [])
        if body_from_stdin and not yes:
            fail("update would drop domains from a multi-host block",
                 why=f"replacing it drops {', '.join(dropped)}, and `--body -` consumed stdin so there's no TTY to confirm",
                 hint="pass --yes, or include every hostname in the domain arg")
        if not yes and not typer.confirm(
            f"{', '.join(heads)} matches an existing block also serving {', '.join(dropped)} — "
            f"replacing it will DROP {', '.join(dropped)}. Continue?"):
            fail("aborted", why="update would drop domains from a multi-host block",
                 hint="include every hostname in the domain arg, or pass --yes")
        res = _caddy_upsert(heads, head_body, on_exists, dry_run, allow_shrink=True)
        _caddy_fail_if_bad(res, heads)
        status = res.get("status")
    if status == "dry-run":
        emit({"domains": heads, "action": res.get("action"), "validated": res.get("validated"),
              "shrunk_from": res.get("shrunk_from")},
             metadata={"dry_run": True, "diff": res.get("diff", "")})
        return
    if status == "unchanged":
        emit({"domains": heads, "action": "unchanged", "reason": "block already matches"})
        return
    if status != "written":
        fail(f"unexpected caddy upsert status {status!r}", why=json.dumps(res)[:500])

    _caddy_reload_or_restore(res.get("backup"))
    emit({"domains": heads, "action": res.get("action"), "validated": res.get("validated"),
          "backup": res.get("backup"), "shrunk_from": res.get("shrunk_from")})


if __name__ == "__main__":
    app()
