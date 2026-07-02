import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { execAtom } from "../lib/exec.ts";
import type { ManifestTool } from "../lib/manifest.ts";

// ADR-0001 flagged this as unverified: what does `typer.confirm()` do when
// the executor's stdio[0] = "ignore" (never a real TTY)? This runs a
// confirm-gated fixture atom through the real execAtom() and asserts it
// aborts fast (non-zero exit, well under the timeout) rather than hanging
// until timeout_ms kills it. See mcp/manifests/pve.yaml + NOTES.md for how
// this result was applied to the real pve confirm-gated commands.

const CONFIRM_FIXTURE = join(import.meta.dir, "fixtures", "scripts", "confirm-fixture.py");

const tool: ManifestTool = { name: "confirm_fixture", description: "d", params: [] };

describe("confirm-gated atom under stdio[0] = 'ignore'", () => {
  test("aborts fast (non-zero exit) instead of hanging", async () => {
    const startedAt = Date.now();
    const result = await execAtom({
      scriptPath: CONFIRM_FIXTURE,
      tool,
      args: {},
      envelope: false,
      // Generous relative to expected latency, but the real assertion is the
      // elapsed-time check below — a hang would eat the whole budget and
      // still show timed_out: true, which the elapsed check catches either way.
      timeoutMs: 15000,
    });
    const elapsedMs = Date.now() - startedAt;

    expect(result.structuredContent.timed_out).toBeUndefined();
    expect(result.isError).toBe(true);
    expect(result.structuredContent.exit_code).toBe(1);
    // "fast" = didn't ride the timeout out. uv's first-run dependency
    // resolution can take a couple seconds; 8s is generous headroom while
    // still being nowhere near the 15s timeout budget.
    expect(elapsedMs).toBeLessThan(8000);
  }, 20000);
});
