import { join } from "node:path";
import { homedir } from "node:os";
import type { ToolRunResult } from "./result.ts";

export interface RunScriptOptions {
  script: string;
  args: string[];
  envelope: boolean;
  timeoutMs: number;
  env?: Record<string, string | undefined>;
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

const REPO_ROOT = join(import.meta.dir, "..", "..", "..");
const SCRIPTS_DIR = join(REPO_ROOT, "scripts");

export const EXEC_GRACE_MS = 2000;

function scriptPath(script: string): string {
  return join(SCRIPTS_DIR, script);
}

export function augmentedEnv(env: Record<string, string | undefined> = process.env): Record<string, string | undefined> {
  const home = homedir();
  const extra = [join(home, ".bun", "bin"), "/opt/homebrew/bin", join(home, ".local", "bin")];
  return { ...env, PATH: `${extra.join(":")}:${env.PATH ?? ""}` };
}

function isEnvelope(value: unknown): value is Envelope {
  return typeof value === "object" && value !== null && "success" in value && typeof (value as { success: unknown }).success === "boolean";
}

async function readStreamUntil(stream: ReadableStream<Uint8Array> | null, deadlineAt: number): Promise<string> {
  if (!stream) return "";

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
      // Keep partial output when cancellation or stream errors happen.
    }
  })();

  const remainingMs = Math.max(0, deadlineAt - Date.now());
  await Promise.race([readLoop, new Promise<void>((resolve) => setTimeout(resolve, remainingMs))]);

  if (!drained) reader.cancel().catch(() => {});
  return text;
}

async function waitExitedUntil(proc: { exited: Promise<number> }, deadlineAt: number): Promise<number> {
  const remainingMs = Math.max(0, deadlineAt - Date.now());
  return Promise.race([proc.exited, new Promise<number>((resolve) => setTimeout(() => resolve(-1), remainingMs))]);
}

export function mapScriptOutput(envelope: boolean, run: { stdout: string; stderr: string; exitCode: number; timedOut: boolean; timeoutMs: number; argv0: string }): ToolRunResult {
  if (run.timedOut) {
    return {
      isError: true,
      structuredContent: {
        stdout: run.stdout,
        stderr: run.stderr,
        exit_code: run.exitCode,
        timed_out: true,
        message: `script '${run.argv0}' timed out after ${run.timeoutMs}ms and was killed`,
      },
    };
  }

  if (!envelope) {
    return {
      isError: run.exitCode !== 0,
      structuredContent: { stdout: run.stdout, stderr: run.stderr, exit_code: run.exitCode },
    };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(run.stdout);
  } catch {
    return {
      isError: true,
      structuredContent: { stdout: run.stdout, stderr: run.stderr, exit_code: run.exitCode },
    };
  }

  if (!isEnvelope(parsed)) {
    return {
      isError: true,
      structuredContent: { stdout: run.stdout, stderr: run.stderr, exit_code: run.exitCode },
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
    structuredContent: { error: parsed.error ?? { message: "script reported failure with no error detail" } },
  };
}

export async function runScript(options: RunScriptOptions): Promise<ToolRunResult> {
  const argv = [scriptPath(options.script), ...options.args];
  const timeoutMs = options.timeoutMs;
  const proc = Bun.spawn(argv, {
    stdio: ["ignore", "pipe", "pipe"],
    env: options.env ?? augmentedEnv(),
  });

  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    proc.kill();
  }, timeoutMs);
  const deadlineAt = Date.now() + timeoutMs + EXEC_GRACE_MS;

  try {
    const [stdout, stderr, exitCode] = await Promise.all([readStreamUntil(proc.stdout, deadlineAt), readStreamUntil(proc.stderr, deadlineAt), waitExitedUntil(proc, deadlineAt)]);
    return mapScriptOutput(options.envelope, { stdout, stderr, exitCode, timedOut, timeoutMs, argv0: argv[0]! });
  } finally {
    clearTimeout(timer);
  }
}
