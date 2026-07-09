import { describe, expect, test } from "bun:test";
import { pushBoolFlag, pushFlag, pushPos } from "../src/core/argv.ts";
import type { ToolboxTool } from "../src/core/tool.ts";
import { calendarTools } from "../src/tools/calendar/index.ts";
import { e3pTools } from "../src/tools/e3p/index.ts";
import { pdfTools } from "../src/tools/pdf/index.ts";
import { pveTools } from "../src/tools/pve/index.ts";
import { remindersTools } from "../src/tools/reminders/index.ts";
import { safariTools } from "../src/tools/safari/index.ts";
import { screenshotTools } from "../src/tools/screenshot/index.ts";
import { ubereatsTools } from "../src/tools/ubereats/index.ts";

const testTools = [...calendarTools, ...e3pTools, ...pdfTools, ...pveTools, ...remindersTools, ...safariTools, ...screenshotTools, ...ubereatsTools];

function getTool(name: string): ToolboxTool {
  const tool = testTools.find((candidate) => candidate.name === name);
  if (!tool) throw new Error(`missing test tool ${name}`);
  return tool;
}

async function runCaptured(name: string, input: Record<string, unknown>): Promise<{ argv: string[]; env?: Record<string, string | undefined> }> {
  const tool = getTool(name);
  let captured: string[] | undefined;
  let capturedEnv: Record<string, string | undefined> | undefined;
  const original = Bun.spawn;
  Bun.spawn = ((argv: string[], options?: { env?: Record<string, string | undefined> }) => {
    captured = argv.slice(1);
    capturedEnv = options?.env;
    return {
      stdout: new ReadableStream({ start(controller) { controller.close(); } }),
      stderr: new ReadableStream({ start(controller) { controller.close(); } }),
      exited: Promise.resolve(0),
      kill() {},
    };
  }) as typeof Bun.spawn;

  try {
    await tool.run(input);
    if (!captured) throw new Error("argv was not captured");
    return { argv: captured, env: capturedEnv };
  } finally {
    Bun.spawn = original;
  }
}

async function expectRejected(name: string, input: Record<string, unknown>): Promise<void> {
  const original = Bun.spawn;
  Bun.spawn = (() => {
    throw new Error("spawn should not be reached");
  }) as typeof Bun.spawn;

  try {
    await expect(getTool(name).run(input)).rejects.toThrow();
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
  test("pve_create_ct maps unprivileged=false to --privileged", async () => {
    expect((await runCaptured("pve_create_ct", { name: "dev", unprivileged: false, yes: true })).argv).toEqual(["create-ct", "dev", "--privileged", "--yes"]);
  });

  test("pve_add_caddy maps the split add tool without action ambiguity", async () => {
    expect((await runCaptured("pve_add_caddy", { domain: "app.example.com", upstream: "10.0.0.2:3000", dry_run: true, yes: true })).argv).toEqual([
      "caddy",
      "app.example.com",
      "10.0.0.2:3000",
      "--action",
      "add",
      "--dry-run",
      "--yes",
    ]);
  });

  test("pve_add_dns passes confirmation to the confirm-gated add path", async () => {
    expect((await runCaptured("pve_add_dns", { host: "dev.internal", ip: "10.0.0.2", yes: true })).argv).toEqual([
      "dns",
      "dev.internal",
      "10.0.0.2",
      "--action",
      "add",
      "--yes",
    ]);
  });

  test("pve_remove_forward requires MCP-level confirmation but does not invent a CLI flag", async () => {
    expect((await runCaptured("pve_remove_forward", { line: 4, confirm: true })).argv).toEqual(["forward", "--action", "del", "--line", "4"]);
  });

  test("screenshot tools encode mode in the tool, not boolean switches", async () => {
    expect((await runCaptured("screenshot_region", { region: "0,0,100,100", out: "/tmp/a.png" })).argv).toEqual(["--region", "0,0,100,100", "/tmp/a.png"]);
    expect((await runCaptured("screenshot_clipboard", {})).argv).toEqual(["--clipboard"]);
  });

  test("ubereats split tools set the correct mode", async () => {
    expect((await runCaptured("ubereats_list_orders", { recent: 5 })).argv).toEqual(["--list-only", "--recent", "5"]);
    expect((await runCaptured("ubereats_update_ledger", { since: "2026-07-01", csv_dir: "ue" })).argv).toEqual(["--ledger", "--since", "2026-07-01", "--csv-dir", "ue"]);
  });

  test("pdf_decrypt passes password through env, not argv", async () => {
    const result = await runCaptured("pdf_decrypt", { file: "locked.pdf", password: "secret", out: "plain.pdf" });
    expect(result.argv).toEqual(["decrypt", "locked.pdf", "--out", "plain.pdf"]);
    expect(result.env?.UTILS_PDF_PASSWORD).toBe("secret");
  });

  test("sensitive/destructive tools require schema-level confirmation", async () => {
    await expectRejected("ubereats_dump_cookie", { path: "/tmp/ue-cookie" });
    await expectRejected("pve_add_forward", { spec: "5001:10.0.0.2:22" });
    await expectRejected("calendar_delete_event", { summary: "standup", cal: "Work" });
    await expectRejected("reminders_complete", { name: "pay bill" });
    await expectRejected("reminders_delete", { name: "pay bill" });
    await expectRejected("safari_close_tab", {});
  });
});
