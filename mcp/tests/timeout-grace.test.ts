import { beforeAll, describe, expect, test } from "bun:test";
import { join } from "node:path";
import { EXEC_GRACE_MS, execAtom } from "../lib/exec.ts";
import type { ManifestTool } from "../lib/manifest.ts";

// Reviewer-flagged blocking bug: proc.kill() only signals the direct child.
// An atom whose subprocess.run() doesn't capture_output=True leaks its
// stdout/stderr fds to grandchildren — if one outlives the kill, the pipe
// never sees EOF and `.text()` hangs forever regardless of timeoutMs. These
// tests exercise the executor-side fix (EXEC_GRACE_MS bound in lib/exec.ts)
// directly, independent of any single atom's hygiene.

const FIXTURES = join(import.meta.dir, "fixtures", "scripts");
const UNCAPTURED_GRANDCHILD = join(FIXTURES, "uncaptured-grandchild.py");
const SLEEP_FOREVER = join(FIXTURES, "sleep-forever.sh");

const noParamsTool: ManifestTool = { name: "fixture", description: "d", params: [] };

// A cold first `python3` invocation on a fresh process can eat a few hundred
// ms of one-time interpreter/dyld warmup — enough to occasionally starve the
// fixture's own print+flush inside a tight 500ms timeoutMs window and flake
// the content assertion below. Absorb that cost here, outside the timed test.
beforeAll(async () => {
  const proc = Bun.spawn(["python3", "-c", "pass"], { stdio: ["ignore", "ignore", "ignore"] });
  await proc.exited;
});

describe("execAtom timeout+grace hardening", () => {
  test("orphaned uncaptured grandchild does not hang the response past timeout+grace", async () => {
    const timeoutMs = 500;
    const startedAt = Date.now();

    const result = await execAtom({
      scriptPath: UNCAPTURED_GRANDCHILD,
      tool: noParamsTool,
      args: {},
      envelope: false,
      timeoutMs,
    });

    const elapsedMs = Date.now() - startedAt;

    // The grandchild sleeps 8s — an unbounded `.text()` read would have
    // taken ~8000ms+. Bounding by timeoutMs + EXEC_GRACE_MS (2500ms here)
    // must win instead. Generous margin for process-spawn jitter, but still
    // nowhere near the grandchild's lifetime.
    expect(elapsedMs).toBeLessThan(timeoutMs + EXEC_GRACE_MS + 2000);
    expect(elapsedMs).toBeLessThan(6000);

    expect(result.isError).toBe(true);
    expect(result.structuredContent.timed_out).toBe(true);
    // Partial output from before the kill should still come through — the
    // parent printed this line and flushed before the executor gave up.
    expect(String(result.structuredContent.stdout)).toContain("parent: spawning uncaptured grandchild");
  }, 15000);

  test("a well-behaved hung direct child (no grandchild) is killed near timeoutMs, not the full grace window", async () => {
    const timeoutMs = 500;
    const startedAt = Date.now();

    const result = await execAtom({
      scriptPath: SLEEP_FOREVER,
      tool: noParamsTool,
      args: {},
      envelope: false,
      timeoutMs,
    });

    const elapsedMs = Date.now() - startedAt;

    expect(result.isError).toBe(true);
    expect(result.structuredContent.timed_out).toBe(true);
    // No grandchild holding the pipe open — stdout should close right after
    // the kill, so this should resolve near timeoutMs, well before grace
    // would even matter. Generous margin, but must be meaningfully faster
    // than the grandchild-hang case above.
    expect(elapsedMs).toBeLessThan(timeoutMs + 1500);
  }, 10000);
});
