import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { ManifestError, loadManifests, resolveAtomScript, validateManifest } from "../lib/manifest.ts";

const FIXTURES = join(import.meta.dir, "fixtures");
const MANIFESTS_DIR = join(FIXTURES, "manifests");
const SCRIPTS_DIR = join(FIXTURES, "scripts");

describe("loadManifests", () => {
  test("loads the valid manifest and skips the broken ones without throwing", () => {
    const { tools, errors } = loadManifests(MANIFESTS_DIR, SCRIPTS_DIR);

    expect(tools).toHaveLength(1);
    expect(tools[0]!.tool.name).toBe("echoit");
    expect(tools[0]!.atom).toBe("echoit");
    expect(tools[0]!.scriptPath).toBe(join(SCRIPTS_DIR, "echoit"));

    // Both bad-missing-atom.yaml and bad-missing-script.yaml should be
    // collected as named errors, not thrown.
    expect(errors).toHaveLength(2);
    expect(errors.every((e) => e instanceof ManifestError)).toBe(true);
    expect(errors.map((e) => e.file).sort()).toEqual(["bad-missing-atom.yaml", "bad-missing-script.yaml"]);
  });

  test("a missing manifests dir returns an empty result, not a crash", () => {
    const { tools, errors } = loadManifests(join(FIXTURES, "nope"), SCRIPTS_DIR);
    expect(tools).toEqual([]);
    expect(errors).toEqual([]);
  });
});

describe("validateManifest", () => {
  test("rejects a non-mapping document", () => {
    expect(() => validateManifest(["not", "a", "mapping"], "f.yaml")).toThrow(ManifestError);
  });

  test("rejects missing 'atom'", () => {
    expect(() => validateManifest({ envelope: true, tools: [] }, "f.yaml")).toThrow(/atom/);
  });

  test("rejects non-boolean 'envelope'", () => {
    expect(() => validateManifest({ atom: "x", envelope: "yes", tools: [{ name: "x", description: "d" }] }, "f.yaml")).toThrow(/envelope/);
  });

  test("rejects empty tools array", () => {
    expect(() => validateManifest({ atom: "x", envelope: true, tools: [] }, "f.yaml")).toThrow(/tools/);
  });

  test("rejects a param with neither positional nor cli", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "string" }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).toThrow(/positional.*cli|cli.*positional/);
  });

  test("rejects a param with both positional and cli", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "string", positional: true, cli: "--p" }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).toThrow();
  });

  test("rejects enum type without an enum list", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "enum", cli: "--p" }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).toThrow(/enum/);
  });

  test("accepts array type with no enum list required", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "array", positional: true }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).not.toThrow();
  });

  test("accepts a stdin: true param with neither positional nor cli", () => {
    const raw = {
      atom: "clipboard",
      envelope: false,
      tools: [{ name: "clipboard_write", description: "d", argv_prefix: ["write"], params: [{ name: "text", type: "string", stdin: true }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).not.toThrow();
  });

  test("rejects a param with both stdin: true and positional/cli", () => {
    const rawWithPositional = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "string", stdin: true, positional: true }] }],
    };
    expect(() => validateManifest(rawWithPositional, "f.yaml")).toThrow();

    const rawWithCli = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "string", stdin: true, cli: "--p" }] }],
    };
    expect(() => validateManifest(rawWithCli, "f.yaml")).toThrow();
  });

  test("rejects more than one stdin: true param on the same tool", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [
        {
          name: "x",
          description: "d",
          params: [
            { name: "a", type: "string", stdin: true },
            { name: "b", type: "string", stdin: true },
          ],
        },
      ],
    };
    expect(() => validateManifest(raw, "f.yaml")).toThrow(/stdin/);
  });

  test("accepts cli_false on a boolean param with cli", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "boolean", cli: "--p", cli_false: "--no-p" }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).not.toThrow();
  });

  test("rejects cli_false on a non-boolean param", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "string", cli: "--p", cli_false: "--no-p" }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).toThrow(/cli_false/);
  });

  test("rejects cli_false on a positional boolean param", () => {
    const raw = {
      atom: "x",
      envelope: true,
      tools: [{ name: "x", description: "d", params: [{ name: "p", type: "boolean", positional: true, cli_false: "--no-p" }] }],
    };
    expect(() => validateManifest(raw, "f.yaml")).toThrow(/cli_false/);
  });

  test("accepts a well-formed manifest and returns it structurally intact", () => {
    const raw = {
      atom: "uuid",
      envelope: true,
      timeout_ms: 5000,
      tools: [
        {
          name: "uuid",
          description: "d",
          argv_prefix: [],
          params: [{ name: "count", type: "number", required: false, cli: "--count" }],
        },
      ],
    };
    const manifest = validateManifest(raw, "uuid.yaml");
    expect(manifest.atom).toBe("uuid");
    expect(manifest.timeout_ms).toBe(5000);
    expect(manifest.tools[0]!.params![0]!.name).toBe("count");
  });
});

describe("resolveAtomScript", () => {
  test("resolves an extensionless executable script", () => {
    expect(resolveAtomScript(SCRIPTS_DIR, "echoit")).toBe(join(SCRIPTS_DIR, "echoit"));
  });

  test("throws for an atom with no matching script", () => {
    expect(() => resolveAtomScript(SCRIPTS_DIR, "nope")).toThrow(/no executable script/);
  });

  test("resolves scripts/<atom>.<ext> against the real repo scripts/ dir", () => {
    const realScripts = join(import.meta.dir, "..", "..", "scripts");
    expect(resolveAtomScript(realScripts, "uuid")).toBe(join(realScripts, "uuid.py"));
    expect(resolveAtomScript(realScripts, "clipboard")).toBe(join(realScripts, "clipboard.sh"));
    expect(resolveAtomScript(realScripts, "subject-lift")).toBe(join(realScripts, "subject-lift.swift"));
  });
});
