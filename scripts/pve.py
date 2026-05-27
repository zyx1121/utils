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
# Gateway runs Caddy natively under systemd (ex-docker). Override for other setups.
CADDY_RELOAD_CMD = os.environ.get("UTILS_PVE_CADDY_RELOAD", "sudo systemctl reload caddy")
VM_BRIDGE = os.environ.get("UTILS_PVE_BRIDGE", "vnet10")
# PVE firewall security group applied to every cloned VM for east-west isolation.
# Empty disables isolation entirely. The group + datacenter master switch are a
# one-time host setup (see SKILL.md); clone only references the group per-VM.
FW_GROUP = os.environ.get("UTILS_PVE_FW_GROUP", "spoke")

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


def _vm_ip(vmid: int) -> Optional[str]:
    """Extract the VM's IP from `qm config ... ipconfig0`. None if unset."""
    config_out = ssh_run(PVE_HOST, "qm", "config", str(vmid))
    for line in config_out.splitlines():
        if line.startswith("ipconfig0:"):
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
            if re.search(r'reverse_proxy\\s+' + re.escape(ip) + r'(:[0-9]+)?\\b', ''.join(block)):
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


# ── destroy ─────────────────────────────────────────────────────
@app.command(help="Destroy a VM permanently — cascades: port forwards, DNS, Caddy, SSH alias, known_hosts.")
def destroy(
    name: str = typer.Argument(..., help="VM name or VMID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    vm = find_vm(name)
    vm_ip = _vm_ip(vm["vmid"])

    forwards = _find_forwards_to_ip(vm_ip) if vm_ip else []
    ssh_forward_port = next((f["dport"] for f in forwards if f["target_port"] == 22), None)
    dns_records = _find_dns_records_by_ip(vm_ip) if vm_ip else []
    caddy_domains = _find_caddy_domains_by_ip(vm_ip) if vm_ip else []
    has_ssh_alias = _ssh_config_has_alias(vm["name"])

    plan_bits = [f"DESTROY VM {vm['name']!r} (VMID {vm['vmid']})"]
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
        ssh_run(PVE_HOST, "qm", "stop", str(vm["vmid"]))

    ssh_run(
        PVE_HOST, "qm", "destroy", str(vm["vmid"]),
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


@app.command(help="Manage Caddy reverse-proxy stanzas on the gateway.")
def caddy(
    domain: Optional[str] = typer.Argument(None, help="Public domain (required for add/remove)"),
    upstream: Optional[str] = typer.Argument(None, help="Upstream host:port (required for add)"),
    action: str = typer.Option("add", "--action", help="add | remove | list"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for remove"),
) -> None:
    if action == "list":
        out = ssh_run(
            GATEWAY_HOST, "sh", "-c",
            f"grep -E '^[A-Za-z0-9*].*[{{][[:space:]]*$' {shlex.quote(GATEWAY_CADDYFILE)} || true",
        )
        domains = []
        for line in out.splitlines():
            head = line.split("{", 1)[0].strip()
            if head:
                domains.extend(d.strip() for d in head.split(","))
        emit({"domains": domains, "caddyfile": GATEWAY_CADDYFILE})
        return

    if not domain:
        fail("domain required", hint="utils pve caddy <domain> ...")

    if action == "remove":
        if not yes and not typer.confirm(f"remove Caddy block for {domain!r}?"):
            fail("aborted", why="user did not confirm", hint="pass --yes to skip")
        if not _remove_caddy_domain(domain):
            emit({"domain": domain, "action": "skipped", "reason": "domain not in Caddyfile"})
            return
        _caddy_reload()
        emit({"domain": domain, "action": "removed"})
        return

    if action != "add":
        fail(f"unknown action {action!r}", hint="use add | remove | list")

    if not upstream:
        fail("upstream required for add", hint="utils pve caddy <domain> <host:port>")
    check_cmd = f"grep -qE '^{re.escape(domain)}\\\\b' {shlex.quote(GATEWAY_CADDYFILE)} && echo present || echo absent"
    present = ssh_run(GATEWAY_HOST, "sh", "-c", check_cmd).strip()
    if present == "present":
        emit({"domain": domain, "upstream": upstream, "action": "skipped", "reason": "domain already in Caddyfile"})
        return
    stanza = f"\n{domain} {{\n    reverse_proxy {upstream}\n}}\n"
    ssh_run(GATEWAY_HOST, "sh", "-c", f"printf %s {shlex.quote(stanza)} >> {shlex.quote(GATEWAY_CADDYFILE)}")
    _caddy_reload()
    emit({"domain": domain, "upstream": upstream, "action": "added"})


if __name__ == "__main__":
    app()
