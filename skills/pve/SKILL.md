---
name: pve
description: Use when user asks about VMs, virtual machines, PVE, Proxmox, port forwarding, the edge reverse proxy (Caddy / gateway / winlab-gateway), HTTPS certs for *.winlab.tw / *.zyx.tw, internal DNS / dnsmasq, *.internal hostnames, or wants to create/start/stop/list VMs or add a route. Triggers on "VM", "虛擬機", "PVE", "port forward", "開機", "關機", "建 VM", "gateway", "反代", "加路由", "新 subdomain", "Caddy", "internal DNS".
---

# PVE — via `utils pve`

Atomic operations against the PVE host and the edge gateway through SSH aliases. The `utils pve` dispatcher wraps `qm` / `iptables` / `dnsmasq` / `Caddy` so agents don't have to memorise remote command surfaces.

> **Real infrastructure (host IPs, SSH port, VMID range, subnet, VM list) lives in `~/.claude/DEVICES.md` (private dotfiles).** This skill documents the command shape only. SSH aliases (`pve`, `gateway`, plus one per VM) are the source of truth — `utils pve` refuses to operate without them.

## Read commands

```bash
utils pve list                     # all VMs + status (table on TTY, JSON in pipes)
utils pve status <name>            # config + state for one VM
utils pve ssh <name> [cmd]         # SSH via alias; refuses if alias missing
```

`utils pve list` and `status` accept either VM name or VMID. `ssh` requires the name to match a `Host` entry in `~/.ssh/config` — alias missing is treated as a real error, not a UX bug.

## Write commands

```bash
utils pve start <name>
utils pve stop <name> [-y]
utils pve destroy <name> [-y]                  # cascades: VM + forwards/DNS/Caddy/SSH alias/known_hosts
utils pve clone <name> [--ip 10.10.10.42] [--vmid 113] [--cores 4] [--ram 4096] [--disk 100] [--no-forward] [--no-isolate]
utils pve forward 8443:10.10.10.42:443         # add
utils pve forward --action list
utils pve forward --action del --line 3
utils pve dns parser.internal 10.10.10.42 [--dry-run] [-y]   # add (default action)
utils pve dns parser.internal --action remove [-y]
utils pve dns --action list
utils pve caddy parser.zyx.tw 10.10.10.42:8080               # add (default action)
utils pve caddy parser.zyx.tw --action remove [-y]
utils pve caddy --action list
```

`stop`, `destroy`, `clone`, `dns`, and `caddy --action remove` are confirmation-gated unless `--yes` is passed. `dns` add also supports `--dry-run` to preview the planned append + reload. `forward del` and `caddy add` run immediately — double-check before invoking.

## Decision rules

- **Never bypass the dispatcher with hardcoded IP/port.** If `ssh <name>` fails, the alias is missing — fix the alias, don't write a raw `ssh -p ... user@<ip>` workaround.
- **Defaults come from env vars** (`UTILS_PVE_HOST`, `UTILS_PVE_GATEWAY`, `UTILS_PVE_TEMPLATE`, `UTILS_PVE_GATEWAY_IP`, `UTILS_PVE_GATEWAY_DNS`, `UTILS_PVE_GATEWAY_CADDY`, `UTILS_PVE_BRIDGE`, `UTILS_PVE_FW_GROUP`). Loki's conventions are the fallback; other operators set their own.
- **New VMs are isolated by default.** `clone` puts the VM on `UTILS_PVE_BRIDGE` (default `vnet10`, a PVE SDN VNet) and applies `firewall=1` + the `UTILS_PVE_FW_GROUP` security group (default `spoke`) **before first boot** — it comes up fenced off from its peers, never momentarily open. `spoke` is egress-only: a VM can reach the subnet gateway + DNS + internet but **not** other VMs (hub-and-spoke; the edge gateway is the hub and is not isolated). Pass `--no-isolate` for a VM that legitimately needs east-west reach. Inbound stays open (`policy_in ACCEPT`) so the SSH forward and reverse-proxy reach keep working.
- **Isolation has a one-time host prerequisite** (not done by `clone`): the PVE firewall master switch + the `spoke` group must exist in `/etc/pve/firewall/cluster.fw`, and the internal network must be the SDN VNet with SNAT (PVE-managed NAT — hand-rolled `iptables MASQUERADE` is incompatible with per-VM firewall, the firewall bridge breaks it). Set `UTILS_PVE_FW_GROUP=""` to disable isolation entirely on hosts without this setup.
- **Run the provisioning chain directly from the main agent — no sub-agent.** clone → DNS → forward → SSH alias edit → smoke test is 4-5 commands; spawning another agent for that is pure overhead. This dispatcher is already the abstraction layer.
- **Stop / destroy / forward del / dns remove / caddy remove** are destructive. Confirm with the user, even when the agent has free rein on safe ops.
- **`destroy` cascades by design.** After purging the VM it sweeps every related ref it can find by VM IP: matching `iptables` PREROUTING rules, dnsmasq hosts records, Caddy domain blocks whose `reverse_proxy` upstream resolves to that IP, the `Host <name>` entry in local `~/.ssh/config` (standalone block or name inside a shared `Host a b c` list), the per-VM firewall config `/etc/pve/firewall/<vmid>.fw`, and finally local `~/.ssh/known_hosts` (by VM name, IP, and the `[pve-host]:port` entry if a `:22` forward existed). The pre-confirm plan shows the full cascade list — read it before saying yes. Anything not found is skipped silently.
- **VMID / IP / SSH port are bound by convention — compute, don't ask.** Default assignment when the user just gives a name (+ optional RAM / disk):
  - **VMID** = next free ID `≥100` (smallest gap, not `max+1`). Run `utils pve list` first to see allocated IDs.
  - **IP** = `10.10.10.<VMID>` — last octet always equals VMID.
  - **External SSH forward** = `50<VMID>:22` (PVE host `:50<vmid>` → VM `:22`).

  State the assignment in one glance-able line ("parser → VMID 42 / IP 10.10.10.42 / SSH 50042"); don't break it into separate questions. Only override when the user explicitly names a different value.

## When to consult DEVICES.md

If the user asks about a *specific* host or VM by role ("the auth VM", "the AFC machine", "what IP is the gateway?"), read `~/.claude/DEVICES.md` — it has the live mapping. This skill stays infrastructure-agnostic on purpose.

## Common patterns

**Provision new VM end-to-end** (main agent runs the whole chain — no sub-agent):

```bash
utils pve list                                         # peek next free VMID ≥100 (say 42)
utils pve clone parser --cores 4 --ram 8192 --disk 100 # auto: VMID 42, IP 10.10.10.42, forward 50042→.42:22
utils pve dns parser.internal 10.10.10.42              # internal .internal resolution
# edit ~/.ssh/config per the clone output's ssh_alias_block + ssh_alias_note
ssh -o StrictHostKeyChecking=accept-new parser echo ok # smoke test (first-run host key accept)
```

`clone` derives `--ip` from `<subnet>.<VMID>` when omitted, auto-adds the `50<VMID>:22` forward, and bakes in east-west isolation (bridge + `firewall=1` + `spoke` group). Pass `--no-forward` if the VM shouldn't have external SSH, `--no-isolate` if it needs to reach other VMs. The output's `ssh_alias_block` and `ssh_alias_note` fields tell you exactly what to add to `~/.ssh/config`.

**Expose a VM service externally:**

```bash
utils pve forward 8443:10.10.10.42:443           # raw L4 port forward via PVE host
utils pve caddy parser.zyx.tw 10.10.10.42:8080   # HTTPS termination + reverse proxy via gateway
```

**Quick survey:**

```bash
utils pve list
utils pve status parser
utils pve dns --action list
utils pve caddy --action list
```

**Rebuild a VM from scratch (same VMID + IP):**

```bash
utils pve destroy bro -y                                # cascades VM + forwards + DNS + Caddy + SSH alias
utils pve clone bro --vmid 113 --cores 4 --ram 8192 --disk 100   # auto IP .113 + forward 50113→.113:22
utils pve dns bro.internal 10.10.10.113
utils pve caddy bro.zyx.tw 10.10.10.113:8080            # only if it had a Caddy route
ssh -o StrictHostKeyChecking=accept-new bro echo ok     # smoke test
```

`destroy` now wipes refs along with the VM. Reuse the same IP + VMID and you only re-create whatever routes the new VM actually needs — no leftover ghost rules from the old one.
