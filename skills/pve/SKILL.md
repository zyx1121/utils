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
utils pve clone <name> --ip 10.10.10.42 [--template 9000] [--ram 4096]
utils pve forward 8443:10.10.10.42:443         # add
utils pve forward --action list
utils pve forward --action del --line 3
utils pve dns parser.internal 10.10.10.42
utils pve caddy parser.zyx.tw 10.10.10.42:8080
```

`stop`, `clone`, and `forward del` are confirmation-gated unless `--yes` is passed.

## Decision rules

- **Never bypass the dispatcher with hardcoded IP/port.** If `ssh <name>` fails, the alias is missing — fix the alias, don't write a raw `ssh -p ... user@<ip>` workaround.
- **Defaults come from env vars** (`UTILS_PVE_HOST`, `UTILS_PVE_GATEWAY`, `UTILS_PVE_TEMPLATE`, `UTILS_PVE_GATEWAY_IP`, `UTILS_PVE_GATEWAY_DNS`, `UTILS_PVE_GATEWAY_CADDY`). Loki's conventions are the fallback; other operators set their own.
- **Full provisioning chain** (clone → DNS → forward → Caddy → smoke test) should go through the `pve-provisioner` agent, not done by hand. Invoke it when the user asks for the whole sequence in one breath.
- **Stop / forward del / caddy domain rewrites** are destructive. Confirm with the user, even when the agent has free rein on safe ops.

## When to consult DEVICES.md

If the user asks about a *specific* host or VM by role ("the auth VM", "the AFC machine", "what IP is the gateway?"), read `~/.claude/DEVICES.md` — it has the live mapping. This skill stays infrastructure-agnostic on purpose.

## Common patterns

**Provision new VM end-to-end:**

```bash
utils pve clone parser --ip 10.10.10.42
# append the printed ssh_alias_block to ~/.ssh/config
utils pve dns parser.internal 10.10.10.42
utils pve ssh parser echo ok                # smoke test
```

**Expose a VM service externally:**

```bash
utils pve forward 8443:10.10.10.42:443           # raw L4 port forward via PVE host
utils pve caddy parser.zyx.tw 10.10.10.42:8080   # HTTPS termination + reverse proxy via gateway
```

**Quick survey:**

```bash
utils pve list
utils pve status parser
```
