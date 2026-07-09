import { z } from "zod";
import { pushBoolFlag, pushFlag, pushPos } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "pve.py";
const envelope = true;
const timeoutMs = 120000;
const name = z.string().describe("VM/CT name or VMID.");
const yes = z.literal(true).describe("Required explicit confirmation; passed as --yes to confirm-gated CLI commands.");
const confirm = z.literal(true).describe("Required explicit confirmation.");

export const pveTools: ToolboxTool[] = [
  scriptTool({ name: "pve_list_guests", description: "List PVE VMs and LXC containers.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["list"] }),
  scriptTool({ name: "pve_get_status", description: "Show config and status for one PVE guest.", inputSchema: { name }, script, envelope, timeoutMs, buildArgs: (input) => ["status", input.name] }),
  scriptTool({ name: "pve_start_guest", description: "Start a stopped VM or LXC container.", inputSchema: { name }, script, envelope, timeoutMs, buildArgs: (input) => ["start", input.name] }),
  scriptTool({ name: "pve_stop_guest", description: "Force-stop a running VM/container. Destructive; pass yes=true to confirm.", inputSchema: { name, yes }, script, envelope, timeoutMs, buildArgs: (input) => { const argv = ["stop", input.name]; pushFlag(argv, "--yes", input.yes); return argv; } }),
  scriptTool({ name: "pve_destroy_guest", description: "Permanently destroy a VM/container and cascade cleanup. Irreversible; pass yes=true to confirm.", inputSchema: { name, yes }, script, envelope, timeoutMs, buildArgs: (input) => { const argv = ["destroy", input.name]; pushFlag(argv, "--yes", input.yes); return argv; } }),
  scriptTool({
    name: "pve_clone_vm",
    description: "Clone a new QEMU VM from a template, with optional forward/firewall setup. Confirm-gated.",
    inputSchema: {
      name: z.string().describe("New VM name."),
      ip: z.string().optional().describe("Internal IP."),
      template: z.number().optional().describe("Source template VMID."),
      vmid: z.number().optional().describe("Target VMID."),
      cores: z.number().optional().describe("CPU core count."),
      ram: z.number().optional().describe("RAM in MB."),
      disk: z.number().optional().describe("Disk size in GB."),
      no_forward: z.boolean().optional().describe("Skip SSH port forward."),
      no_isolate: z.boolean().optional().describe("Skip spoke firewall isolation."),
      yes,
    },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["clone", input.name];
      pushFlag(argv, "--ip", input.ip);
      pushFlag(argv, "--template", input.template);
      pushFlag(argv, "--vmid", input.vmid);
      pushFlag(argv, "--cores", input.cores);
      pushFlag(argv, "--ram", input.ram);
      pushFlag(argv, "--disk", input.disk);
      pushFlag(argv, "--no-forward", input.no_forward);
      pushFlag(argv, "--no-isolate", input.no_isolate);
      pushFlag(argv, "--yes", input.yes);
      return argv;
    },
  }),
  scriptTool({
    name: "pve_create_ct",
    description: "Create a new LXC container, with optional forward/firewall setup. Confirm-gated.",
    inputSchema: {
      name: z.string().describe("Container hostname."),
      template: z.string().optional().describe("vztmpl volid."),
      vmid: z.number().optional().describe("Target VMID."),
      ip: z.string().optional().describe("Internal IP."),
      cores: z.number().optional().describe("CPU core count."),
      ram: z.number().optional().describe("RAM in MB."),
      disk: z.number().optional().describe("Root filesystem GB."),
      swap: z.number().optional().describe("Swap MB."),
      storage: z.string().optional().describe("Storage pool."),
      unprivileged: z.boolean().optional().describe("true -> --unprivileged; false -> --privileged."),
      nesting: z.boolean().optional().describe("Enable container nesting."),
      no_forward: z.boolean().optional().describe("Skip SSH port forward."),
      no_isolate: z.boolean().optional().describe("Skip spoke firewall isolation."),
      yes,
    },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["create-ct", input.name];
      pushFlag(argv, "--template", input.template);
      pushFlag(argv, "--vmid", input.vmid);
      pushFlag(argv, "--ip", input.ip);
      pushFlag(argv, "--cores", input.cores);
      pushFlag(argv, "--ram", input.ram);
      pushFlag(argv, "--disk", input.disk);
      pushFlag(argv, "--swap", input.swap);
      pushFlag(argv, "--storage", input.storage);
      pushBoolFlag(argv, "--unprivileged", input.unprivileged, "--privileged");
      pushFlag(argv, "--nesting", input.nesting);
      pushFlag(argv, "--no-forward", input.no_forward);
      pushFlag(argv, "--no-isolate", input.no_isolate);
      pushFlag(argv, "--yes", input.yes);
      return argv;
    },
  }),
  scriptTool({ name: "pve_list_forwards", description: "List PVE gateway port-forward rules.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["forward", "--action", "list"] }),
  scriptTool({ name: "pve_add_forward", description: "Add HOST_PORT:VM_IP:VM_PORT port forward. Exposes a service externally; requires confirm=true.", inputSchema: { spec: z.string().describe("HOST_PORT:VM_IP:VM_PORT."), confirm }, script, envelope, timeoutMs, buildArgs: (input) => ["forward", input.spec, "--action", "add"] }),
  scriptTool({
    name: "pve_remove_forward",
    description: "Remove a PVE forward by iptables line number. Destructive; requires confirm=true.",
    inputSchema: { line: z.number().describe("Line number from pve_list_forwards."), confirm },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => ["forward", "--action", "del", "--line", String(input.line)],
  }),
  scriptTool({ name: "pve_list_dns", description: "List gateway dnsmasq internal DNS records.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["dns", "--action", "list"] }),
  scriptTool({
    name: "pve_add_dns",
    description: "Add or preview an internal DNS record.",
    inputSchema: { host: z.string().describe("Hostname."), ip: z.string().describe("IP address."), dry_run: z.boolean().optional().describe("Preview without writing."), yes },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["dns", input.host, input.ip, "--action", "add"];
      pushFlag(argv, "--dry-run", input.dry_run);
      pushFlag(argv, "--yes", input.yes);
      return argv;
    },
  }),
  scriptTool({ name: "pve_remove_dns", description: "Remove an internal DNS record. Destructive; pass yes=true to confirm.", inputSchema: { host: z.string().describe("Hostname."), yes }, script, envelope, timeoutMs, buildArgs: (input) => { const argv = ["dns", input.host, "--action", "remove"]; pushFlag(argv, "--yes", input.yes); return argv; } }),
  scriptTool({ name: "pve_list_caddy", description: "List Caddy reverse-proxy site blocks.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["caddy", "--action", "list"] }),
  scriptTool({
    name: "pve_add_caddy",
    description: "Add or update a Caddy reverse-proxy block with validation and reload-or-rollback.",
    inputSchema: {
      domain: z.string().describe("Public domain head; comma-join for multi-host block."),
      upstream: z.string().optional().describe("Upstream host:port for simple reverse_proxy."),
      tls: z.string().optional().describe("TLS setting: 'internal' or 'CERT KEY'."),
      body: z.string().optional().describe("Verbatim Caddy block body; mutually exclusive with upstream/tls in the CLI."),
      on_exists: z.enum(["update", "skip", "fail"]).optional().describe("Existing block behavior. Default: update."),
      dry_run: z.boolean().optional().describe("Render/validate diff without writing."),
      yes,
    },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["caddy", input.domain];
      pushPos(argv, input.upstream);
      pushFlag(argv, "--action", "add");
      pushFlag(argv, "--tls", input.tls);
      pushFlag(argv, "--body", input.body);
      pushFlag(argv, "--on-exists", input.on_exists);
      pushFlag(argv, "--dry-run", input.dry_run);
      pushFlag(argv, "--yes", input.yes);
      return argv;
    },
  }),
  scriptTool({ name: "pve_remove_caddy", description: "Remove a Caddy site block. Destructive; pass yes=true to confirm.", inputSchema: { domain: z.string().describe("Domain block to remove."), yes }, script, envelope, timeoutMs, buildArgs: (input) => { const argv = ["caddy", input.domain, "--action", "remove"]; pushFlag(argv, "--yes", input.yes); return argv; } }),
];
