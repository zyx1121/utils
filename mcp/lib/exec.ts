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
  const argv: string[] = [scriptPath, ...(tool.argv_prefix ?? [])];

  for (const param of tool.params ?? []) {
    const value = args[param.name];
    appendParam(argv, param, value);
  }

  return argv;
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

export async function execAtom(opts: ExecOptions): Promise<ExecResult> {
  const { tool, args, scriptPath, envelope, timeoutMs, env } = opts;
  const argv = buildArgv(scriptPath, tool, args);

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

  let stdout: string;
  let stderr: string;
  let exitCode: number;
  try {
    [stdout, stderr, exitCode] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);
  } finally {
    clearTimeout(timer);
  }

  return mapRunOutput(envelope, { stdout, stderr, exitCode, timedOut, timeoutMs, argv0: argv[0]! });
}
