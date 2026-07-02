// Subprocess executor — spawns an atom script, maps its output onto the MCP
// CallToolResult shape. Hard rule from ADR-0001: subprocess stdio is always
// ["ignore", "pipe", "pipe"] — it must never inherit the server's stdout,
// which is the JSON-RPC channel.
import type { ManifestParam, ManifestTool } from "./manifest.ts";

export interface ExecOptions {
  scriptPath: string;
  tool: ManifestTool;
  args: Record<string, unknown>;
  envelope: boolean;
  timeoutMs: number;
  env?: Record<string, string | undefined>;
}

export interface ExecResult {
  structuredContent: Record<string, unknown>;
  isError: boolean;
}

/**
 * argv = [scriptPath, ...argv_prefix, <params in declared order>].
 * Positional params append their value directly; flagged params append
 * `cli` then the value (booleans append only the flag, and only when true —
 * or `cli_false` when explicitly false and declared). `array` params (v1.1)
 * append every item in order for positional, or repeat `cli` once per item
 * for flagged. A `stdin: true` param is never touched here — it's routed to
 * the subprocess's stdin by `execAtom`, not argv.
 * Always returned as an array for `spawn` — never joined into a shell string.
 */
export function buildArgv(scriptPath: string, tool: ManifestTool, args: Record<string, unknown>): string[] {
  assertNoPositionalGap(tool, args);

  const argv: string[] = [scriptPath, ...(tool.argv_prefix ?? [])];

  for (const param of tool.params ?? []) {
    const value = args[param.name];
    appendParam(argv, param, value);
  }

  return argv;
}

/**
 * Positional params are consumed by argv position, not by name — the
 * underlying CLI has no way to know a later positional was "meant" to skip
 * an earlier one. If an earlier positional is missing while a later one has
 * a value (e.g. `pve_dns` giving `ip` without `host`, or `pve_caddy` giving
 * `upstream` without `domain`), silently building argv would shift every
 * later positional one slot to the left and corrupt the call without any
 * error. Reject by name instead of guessing.
 */
function assertNoPositionalGap(tool: ManifestTool, args: Record<string, unknown>): void {
  const positionals = (tool.params ?? []).filter((p) => p.positional);
  let gapAt: string | undefined;

  for (const param of positionals) {
    const present = args[param.name] !== undefined;
    if (!present) {
      if (gapAt === undefined) gapAt = param.name;
      continue;
    }
    if (gapAt !== undefined) {
      throw new Error(
        `tool '${tool.name}': positional param '${param.name}' has a value but earlier positional param ` +
          `'${gapAt}' does not — passing it would shift argv positions and corrupt the call. ` +
          `Provide '${gapAt}' too, or omit '${param.name}'.`,
      );
    }
  }
}

function appendParam(argv: string[], param: ManifestParam, value: unknown): void {
  if (param.stdin) return;

  if (param.positional) {
    if (value === undefined) return;
    if (param.type === "array") {
      for (const item of value as unknown[]) argv.push(String(item));
    } else {
      argv.push(String(value));
    }
    return;
  }

  // flagged
  if (param.type === "boolean") {
    if (value === true) {
      argv.push(param.cli as string);
    } else if (value === false && param.cli_false) {
      argv.push(param.cli_false);
    }
    return;
  }

  if (param.type === "array") {
    if (value === undefined) return;
    for (const item of value as unknown[]) {
      argv.push(param.cli as string);
      argv.push(String(item));
    }
    return;
  }

  if (value === undefined) return;
  argv.push(param.cli as string);
  argv.push(String(value));
}

/**
 * The single `stdin: true` param's value (if the tool declares one and the
 * caller supplied it), flattened to a string for feeding the subprocess.
 * Arrays join with newlines; every other type stringifies directly.
 */
export function resolveStdinInput(tool: ManifestTool, args: Record<string, unknown>): string | undefined {
  const stdinParam = (tool.params ?? []).find((p) => p.stdin);
  if (!stdinParam) return undefined;
  const value = args[stdinParam.name];
  if (value === undefined) return undefined;
  if (Array.isArray(value)) return value.map(String).join("\n");
  return String(value);
}

interface EnvelopeSuccess {
  success: true;
  data: unknown;
  metadata?: Record<string, unknown>;
}
interface EnvelopeFailure {
  success: false;
  error?: { message?: string; why?: string | null; hint?: string | null };
}
type Envelope = EnvelopeSuccess | EnvelopeFailure;

function isEnvelope(v: unknown): v is Envelope {
  return typeof v === "object" && v !== null && "success" in v && typeof (v as { success: unknown }).success === "boolean";
}

export interface RunOutput {
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut: boolean;
  timeoutMs: number;
  argv0: string;
}

/**
 * Pure mapping from a completed (or timed-out) run onto the MCP result
 * shape — no subprocess I/O in here, which is what makes it unit-testable
 * against fixture stdout without actually spawning anything.
 */
export function mapRunOutput(envelope: boolean, run: RunOutput): ExecResult {
  const { stdout, stderr, exitCode, timedOut, timeoutMs, argv0 } = run;

  if (timedOut) {
    return {
      isError: true,
      structuredContent: {
        stdout,
        stderr,
        exit_code: exitCode,
        timed_out: true,
        message: `atom '${argv0}' timed out after ${timeoutMs}ms and was killed`,
      },
    };
  }

  if (!envelope) {
    return {
      isError: exitCode !== 0,
      structuredContent: { stdout, stderr, exit_code: exitCode },
    };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    // Envelope atom didn't produce parseable JSON on stdout — broken
    // contract, fall back to the raw non-envelope shape.
    return {
      isError: true,
      structuredContent: { stdout, stderr, exit_code: exitCode },
    };
  }

  if (!isEnvelope(parsed)) {
    return {
      isError: true,
      structuredContent: { stdout, stderr, exit_code: exitCode },
    };
  }

  if (parsed.success) {
    return {
      isError: false,
      structuredContent: { data: parsed.data, metadata: parsed.metadata ?? {} },
    };
  }

  return {
    isError: true,
    structuredContent: { error: parsed.error ?? { message: "atom reported failure with no error detail" } },
  };
}

// After a timeout kill, how long we wait for stdio to actually close before
// giving up on it. Not tunable per-tool — this is an executor-wide backstop,
// not part of the manifest spec.
//
// Why this exists: `proc.kill()` only signals the *direct* child. If that
// child spawned a grandchild without capturing its output (a bug, but one
// the executor cannot assume atoms are free of — see scripts/mac-app.py's
// pre-fix subprocess.run() calls and tests/fixtures/scripts/
// uncaptured-grandchild.py), the grandchild inherits the same pipe write
// end. The read end then never sees EOF — `.text()` on the stream waits for
// EOF, not for the direct child's exit — so an uncaptured orphan can hold
// the MCP response open indefinitely even though the "parent" atom is dead.
// The ADR's timeout guarantee has to hold from the executor's side alone; it
// cannot depend on every atom's subprocess hygiene being correct.
export const EXEC_GRACE_MS = 2000;

interface DrainResult {
  text: string;
  drained: boolean;
}

/** Read a stream to EOF, but give up at `deadlineAt` (ms since epoch) and
 * return whatever was collected so far instead of waiting forever. */
async function readStreamUntil(stream: ReadableStream<Uint8Array> | null, deadlineAt: number): Promise<DrainResult> {
  if (!stream) return { text: "", drained: true };

  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let drained = false;

  const readLoop = (async () => {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          text += decoder.decode();
          drained = true;
          return;
        }
        text += decoder.decode(value, { stream: true });
      }
    } catch {
      // Reader was cancelled below (deadline hit) or the stream errored —
      // either way we already keep whatever text was collected up to here.
    }
  })();

  const remainingMs = Math.max(0, deadlineAt - Date.now());
  const deadline = new Promise<void>((resolve) => setTimeout(resolve, remainingMs));
  await Promise.race([readLoop, deadline]);

  if (!drained) {
    // Give up — do not await; the underlying fd may never close if an
    // orphaned grandchild still holds it open, and we must not block on it.
    reader.cancel().catch(() => {});
  }

  return { text, drained };
}

interface ExitedLike {
  exited: Promise<number>;
}

/** Wait for a process's exit code, but give up at `deadlineAt` and return a
 * sentinel (-1) instead of waiting forever for a direct child that ignores
 * its kill signal. */
async function waitExitedUntil(proc: ExitedLike, deadlineAt: number): Promise<{ code: number; settled: boolean }> {
  let settled = false;
  const exitedPromise = proc.exited.then((code) => {
    settled = true;
    return code;
  });
  const remainingMs = Math.max(0, deadlineAt - Date.now());
  const timeoutPromise = new Promise<number>((resolve) => setTimeout(() => resolve(-1), remainingMs));
  const code = await Promise.race([exitedPromise, timeoutPromise]);
  return { code, settled };
}

export async function execAtom(opts: ExecOptions): Promise<ExecResult> {
  const { tool, args, scriptPath, envelope, timeoutMs, env } = opts;

  let argv: string[];
  try {
    argv = buildArgv(scriptPath, tool, args);
  } catch (e) {
    // A rejected buildArgv (e.g. the positional-gap guard) never reaches the
    // subprocess — surface it the same way every other atom failure is
    // surfaced, so hook telemetry's content[0].text === JSON.stringify(structuredContent)
    // convention (ADR-0001 Consequences) holds even for pre-spawn errors.
    return {
      isError: true,
      structuredContent: { error: { message: e instanceof Error ? e.message : String(e) } },
    };
  }

  // Default is "ignore" (ADR-0001 hard rule: subprocess never inherits the
  // server's real stdio, which is the JSON-RPC channel). A `stdin: true`
  // param (v1.1) is the one carve-out — it feeds a synthetic in-memory Blob,
  // never the server's actual process.stdin, so the JSON-RPC stream is still
  // never touched.
  const stdinInput = resolveStdinInput(tool, args);
  const stdin0: "ignore" | Blob = stdinInput !== undefined ? new Blob([stdinInput]) : "ignore";

  const proc = Bun.spawn(argv, {
    stdio: [stdin0, "pipe", "pipe"],
    env: env ?? process.env,
  });

  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    proc.kill();
  }, timeoutMs);

  // Hard ceiling on the whole read phase, computed once so stdout/stderr/exit
  // all race against the same wall-clock cutoff: timeoutMs for the atom to
  // behave, plus EXEC_GRACE_MS for its stdio to actually close afterward.
  // See EXEC_GRACE_MS's comment for why this can't just be `.text()` + `await`.
  const deadlineAt = Date.now() + timeoutMs + EXEC_GRACE_MS;

  let stdout: string;
  let stderr: string;
  let exitCode: number;
  try {
    const [stdoutResult, stderrResult, exitResult] = await Promise.all([
      readStreamUntil(proc.stdout, deadlineAt),
      readStreamUntil(proc.stderr, deadlineAt),
      waitExitedUntil(proc, deadlineAt),
    ]);
    stdout = stdoutResult.text;
    stderr = stderrResult.text;
    exitCode = exitResult.code;
  } finally {
    clearTimeout(timer);
  }

  return mapRunOutput(envelope, { stdout, stderr, exitCode, timedOut, timeoutMs, argv0: argv[0]! });
}
