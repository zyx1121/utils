import { describe, expect, test } from "bun:test";
import { buildArgv, mapRunOutput } from "../lib/exec.ts";
import type { ManifestTool } from "../lib/manifest.ts";

describe("buildArgv", () => {
  test("positional params append raw values in declared order, no flags", () => {
    const tool: ManifestTool = {
      name: "subject_lift",
      description: "d",
      params: [
        { name: "input", type: "string", positional: true },
        { name: "output", type: "string", positional: true },
      ],
    };
    const argv = buildArgv("/scripts/subject-lift.swift", tool, { input: "cat.jpg", output: "cat.png" });
    expect(argv).toEqual(["/scripts/subject-lift.swift", "cat.jpg", "cat.png"]);
  });

  test("flagged string/number/enum params append cli then value", () => {
    const tool: ManifestTool = {
      name: "uuid",
      description: "d",
      params: [
        { name: "count", type: "number", cli: "--count" },
        { name: "version", type: "enum", enum: ["4", "7"], cli: "--version" },
      ],
    };
    const argv = buildArgv("/scripts/uuid.py", tool, { count: 3, version: "7" });
    expect(argv).toEqual(["/scripts/uuid.py", "--count", "3", "--version", "7"]);
  });

  test("boolean flagged param appends only the flag, and only when true", () => {
    const tool: ManifestTool = {
      name: "t",
      description: "d",
      params: [{ name: "verbose", type: "boolean", cli: "--verbose" }],
    };
    expect(buildArgv("/s", tool, { verbose: true })).toEqual(["/s", "--verbose"]);
    expect(buildArgv("/s", tool, { verbose: false })).toEqual(["/s"]);
    expect(buildArgv("/s", tool, {})).toEqual(["/s"]);
  });

  test("undefined optional values are omitted entirely (positional and flagged)", () => {
    const tool: ManifestTool = {
      name: "t",
      description: "d",
      params: [
        { name: "count", type: "number", required: false, cli: "--count" },
        { name: "tag", type: "string", required: false, positional: true },
      ],
    };
    expect(buildArgv("/s", tool, {})).toEqual(["/s"]);
  });

  test("argv_prefix is placed before params, in declared order", () => {
    const tool: ManifestTool = {
      name: "clipboard_read",
      description: "d",
      argv_prefix: ["read"],
    };
    expect(buildArgv("/scripts/clipboard.sh", tool, {})).toEqual(["/scripts/clipboard.sh", "read"]);
  });

  test("params respect declared order regardless of args object key order", () => {
    const tool: ManifestTool = {
      name: "t",
      description: "d",
      params: [
        { name: "b", type: "string", positional: true },
        { name: "a", type: "string", positional: true },
      ],
    };
    const argv = buildArgv("/s", tool, { a: "A", b: "B" });
    expect(argv).toEqual(["/s", "B", "A"]);
  });
});

describe("mapRunOutput — envelope atoms", () => {
  const base = { stderr: "", timedOut: false, timeoutMs: 60000, argv0: "/scripts/uuid.py" };

  test("success envelope maps to structuredContent {data, metadata}, isError false", () => {
    const stdout = JSON.stringify({ success: true, data: ["u1", "u2"], metadata: { count: 2 } });
    const result = mapRunOutput(true, { ...base, stdout, exitCode: 0 });
    expect(result.isError).toBe(false);
    expect(result.structuredContent).toEqual({ data: ["u1", "u2"], metadata: { count: 2 } });
  });

  test("failure envelope maps to isError true, error object passed through", () => {
    const stdout = JSON.stringify({
      success: false,
      error: { message: "bad count", why: "must be >= 1", hint: "pass --count 1" },
    });
    const result = mapRunOutput(true, { ...base, stdout, exitCode: 1 });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toEqual({
      error: { message: "bad count", why: "must be >= 1", hint: "pass --count 1" },
    });
  });

  test("non-JSON stdout falls back to raw {stdout, stderr, exit_code}, isError true", () => {
    const stdout = "not json at all";
    const result = mapRunOutput(true, { ...base, stdout, stderr: "traceback...", exitCode: 1 });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toEqual({ stdout, stderr: "traceback...", exit_code: 1 });
  });

  test("JSON without a 'success' field also falls back to raw shape", () => {
    const stdout = JSON.stringify({ foo: "bar" });
    const result = mapRunOutput(true, { ...base, stdout, exitCode: 0 });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toEqual({ stdout, stderr: "", exit_code: 0 });
  });
});

describe("mapRunOutput — non-envelope atoms", () => {
  const base = { timedOut: false, timeoutMs: 60000, argv0: "/scripts/clipboard.sh" };

  test("exit 0 maps to isError false, raw stdout/stderr/exit_code passthrough", () => {
    const result = mapRunOutput(false, { ...base, stdout: "clipboard contents", stderr: "", exitCode: 0 });
    expect(result.isError).toBe(false);
    expect(result.structuredContent).toEqual({ stdout: "clipboard contents", stderr: "", exit_code: 0 });
  });

  test("non-zero exit maps to isError true", () => {
    const result = mapRunOutput(false, { ...base, stdout: "", stderr: "boom", exitCode: 2 });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toEqual({ stdout: "", stderr: "boom", exit_code: 2 });
  });
});

describe("mapRunOutput — timeout", () => {
  test("timed_out short-circuits both envelope and non-envelope paths", () => {
    const run = { stdout: "partial", stderr: "", exitCode: -1, timedOut: true, timeoutMs: 5000, argv0: "/scripts/x" };
    const result = mapRunOutput(true, run);
    expect(result.isError).toBe(true);
    expect(result.structuredContent.timed_out).toBe(true);
    expect(result.structuredContent.message).toContain("timed out after 5000ms");
  });
});
