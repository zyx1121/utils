import { describe, expect, test } from "bun:test";
import { pushBoolFlag, pushFlag, pushPos } from "../src/core/argv.ts";
import { pveTools } from "../src/tools/pve/index.ts";
import { screenshotTools } from "../src/tools/screenshot/index.ts";
import { ubereatsTools } from "../src/tools/ubereats/index.ts";

function build(name: string, input: Record<string, unknown>): string[] {
  const tool = [...pveTools, ...screenshotTools, ...ubereatsTools].find((candidate) => candidate.name === name);
  if (!tool) throw new Error(`missing test tool ${name}`);

  let captured: string[] | undefined;
  const original = Bun.spawn;
  Bun.spawn = ((argv: string[]) => {
    captured = argv.slice(1);
    return {
      stdout: new ReadableStream({ start(controller) { controller.close(); } }),
      stderr: new ReadableStream({ start(controller) { controller.close(); } }),
      exited: Promise.resolve(0),
      kill() {},
    };
  }) as typeof Bun.spawn;

  try {
    tool.run(input);
    if (!captured) throw new Error("argv was not captured");
    return captured;
  } finally {
    Bun.spawn = original;
  }
}

describe("argv helpers", () => {
  test("pushFlag handles scalar, boolean, and array values", () => {
    const argv: string[] = [];
    pushFlag(argv, "--x", "a");
    pushFlag(argv, "--n", 2);
    pushFlag(argv, "--on", true);
    pushFlag(argv, "--off", false);
    pushFlag(argv, "--arr", ["a", "b"]);
    expect(argv).toEqual(["--x", "a", "--n", "2", "--on", "--arr", "a", "--arr", "b"]);
  });

  test("pushBoolFlag supports explicit false flags", () => {
    const argv: string[] = [];
    pushBoolFlag(argv, "--unprivileged", false, "--privileged");
    pushBoolFlag(argv, "--nesting", true);
    expect(argv).toEqual(["--privileged", "--nesting"]);
  });

  test("pushPos omits undefined only", () => {
    const argv: string[] = [];
    pushPos(argv, undefined);
    pushPos(argv, 0);
    expect(argv).toEqual(["0"]);
  });
});

describe("selected native tool argv mappings", () => {
  test("pve_create_ct maps unprivileged=false to --privileged", () => {
    expect(build("pve_create_ct", { name: "dev", unprivileged: false, yes: true })).toEqual(["create-ct", "dev", "--privileged", "--yes"]);
  });

  test("pve_add_caddy maps the split add tool without action ambiguity", () => {
    expect(build("pve_add_caddy", { domain: "app.example.com", upstream: "10.0.0.2:3000", dry_run: true })).toEqual([
      "caddy",
      "app.example.com",
      "10.0.0.2:3000",
      "--action",
      "add",
      "--dry-run",
    ]);
  });

  test("pve_add_dns passes confirmation to the confirm-gated add path", () => {
    expect(build("pve_add_dns", { host: "dev.internal", ip: "10.0.0.2", yes: true })).toEqual([
      "dns",
      "dev.internal",
      "10.0.0.2",
      "--action",
      "add",
      "--yes",
    ]);
  });

  test("pve_remove_forward requires MCP-level confirmation but does not invent a CLI flag", () => {
    expect(build("pve_remove_forward", { line: 4, confirm: true })).toEqual(["forward", "--action", "del", "--line", "4"]);
  });

  test("screenshot tools encode mode in the tool, not boolean switches", () => {
    expect(build("screenshot_region", { region: "0,0,100,100", out: "/tmp/a.png" })).toEqual(["--region", "0,0,100,100", "/tmp/a.png"]);
    expect(build("screenshot_clipboard", {})).toEqual(["--clipboard"]);
  });

  test("ubereats split tools set the correct mode", () => {
    expect(build("ubereats_list_orders", { recent: 5 })).toEqual(["--list-only", "--recent", "5"]);
    expect(build("ubereats_update_ledger", { since: "2026-07-01", csv_dir: "ue" })).toEqual(["--ledger", "--since", "2026-07-01", "--csv-dir", "ue"]);
  });
});
