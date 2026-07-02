// Manifest loading — YAML files under manifests/ describe how an atom in
// ../scripts/ maps onto one or more MCP tools. Spec v1.1 (frozen v1 base +
// three lead-approved extensions — stdin, array, cli_false — see
// decisions/ADR-0001-mcp-tool-provider.md + mcp/README.md's spec section).
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { parse as parseYaml } from "yaml";

export type ParamType = "string" | "number" | "boolean" | "enum" | "array";

export interface ManifestParam {
  name: string;
  type: ParamType;
  required?: boolean;
  description?: string;
  cli?: string;
  /** boolean-only: flag to append when the value is `false` (default omit). */
  cli_false?: string;
  positional?: boolean;
  /** value routed to the subprocess's stdin instead of argv. At most one per tool. */
  stdin?: boolean;
  enum?: string[];
}

export interface ManifestTool {
  name: string;
  description: string;
  argv_prefix?: string[];
  params?: ManifestParam[];
}

export interface Manifest {
  atom: string;
  envelope: boolean;
  timeout_ms?: number;
  tools: ManifestTool[];
}

export interface LoadedTool {
  file: string;
  atom: string;
  envelope: boolean;
  timeoutMs: number;
  scriptPath: string;
  tool: ManifestTool;
}

export interface LoadResult {
  tools: LoadedTool[];
  errors: ManifestError[];
}

/** Named error for a specific manifest file — caller skips just that file. */
export class ManifestError extends Error {
  file: string;
  constructor(file: string, message: string) {
    super(`${file}: ${message}`);
    this.name = "ManifestError";
    this.file = file;
  }
}

const DEFAULT_TIMEOUT_MS = 60000;
const VALID_TYPES: ParamType[] = ["string", "number", "boolean", "enum", "array"];

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function validateParam(raw: unknown, ctx: string): ManifestParam {
  if (!isPlainObject(raw)) {
    throw new Error(`${ctx}: param must be a mapping`);
  }
  const { name, type, required, description, cli, cli_false, positional, stdin, enum: enumValues } = raw;

  if (typeof name !== "string" || name.length === 0) {
    throw new Error(`${ctx}: param 'name' must be a non-empty string`);
  }
  const pctx = `${ctx} param '${name}'`;

  if (typeof type !== "string" || !VALID_TYPES.includes(type as ParamType)) {
    throw new Error(`${pctx}: 'type' must be one of ${VALID_TYPES.join("|")}, got ${JSON.stringify(type)}`);
  }
  if (required !== undefined && typeof required !== "boolean") {
    throw new Error(`${pctx}: 'required' must be a boolean`);
  }
  if (description !== undefined && typeof description !== "string") {
    throw new Error(`${pctx}: 'description' must be a string`);
  }
  if (cli !== undefined && typeof cli !== "string") {
    throw new Error(`${pctx}: 'cli' must be a string`);
  }
  if (cli_false !== undefined && typeof cli_false !== "string") {
    throw new Error(`${pctx}: 'cli_false' must be a string`);
  }
  if (positional !== undefined && typeof positional !== "boolean") {
    throw new Error(`${pctx}: 'positional' must be a boolean`);
  }
  if (stdin !== undefined && typeof stdin !== "boolean") {
    throw new Error(`${pctx}: 'stdin' must be a boolean`);
  }

  const isPositional = positional === true;
  const hasCli = typeof cli === "string" && cli.length > 0;
  const isStdin = stdin === true;
  const deliveryModes = [isPositional, hasCli, isStdin].filter(Boolean).length;
  if (deliveryModes !== 1) {
    throw new Error(`${pctx}: exactly one of 'positional: true', 'cli', or 'stdin: true' must be set`);
  }

  const hasCliFalse = typeof cli_false === "string" && cli_false.length > 0;
  if (hasCliFalse && (type !== "boolean" || !hasCli)) {
    throw new Error(`${pctx}: 'cli_false' is only valid on a boolean param that also has 'cli' set`);
  }

  if (type === "enum") {
    if (!Array.isArray(enumValues) || enumValues.length === 0 || !enumValues.every((e) => typeof e === "string")) {
      throw new Error(`${pctx}: type 'enum' requires a non-empty 'enum' list of strings`);
    }
  } else if (enumValues !== undefined) {
    throw new Error(`${pctx}: 'enum' is only valid when type is 'enum'`);
  }

  return {
    name,
    type: type as ParamType,
    required,
    description,
    cli: hasCli ? (cli as string) : undefined,
    cli_false: hasCliFalse ? (cli_false as string) : undefined,
    positional: isPositional || undefined,
    stdin: isStdin || undefined,
    enum: type === "enum" ? (enumValues as string[]) : undefined,
  };
}

function validateTool(raw: unknown, ctx: string, seenNames: Set<string>): ManifestTool {
  if (!isPlainObject(raw)) {
    throw new Error(`${ctx}: tool must be a mapping`);
  }
  const { name, description, argv_prefix, params } = raw;

  if (typeof name !== "string" || name.length === 0) {
    throw new Error(`${ctx}: tool 'name' must be a non-empty string`);
  }
  const tctx = `${ctx} tool '${name}'`;
  if (seenNames.has(name)) {
    throw new Error(`${tctx}: duplicate tool name within manifest domain`);
  }

  if (typeof description !== "string" || description.length === 0) {
    throw new Error(`${tctx}: 'description' must be a non-empty string`);
  }

  let prefix: string[] | undefined;
  if (argv_prefix !== undefined) {
    if (!Array.isArray(argv_prefix) || !argv_prefix.every((p) => typeof p === "string")) {
      throw new Error(`${tctx}: 'argv_prefix' must be an array of strings`);
    }
    prefix = argv_prefix as string[];
  }

  let toolParams: ManifestParam[] | undefined;
  if (params !== undefined) {
    if (!Array.isArray(params)) {
      throw new Error(`${tctx}: 'params' must be an array`);
    }
    const paramNames = new Set<string>();
    toolParams = params.map((p) => {
      const validated = validateParam(p, tctx);
      if (paramNames.has(validated.name)) {
        throw new Error(`${tctx}: duplicate param name '${validated.name}'`);
      }
      paramNames.add(validated.name);
      return validated;
    });

    const stdinCount = toolParams.filter((p) => p.stdin).length;
    if (stdinCount > 1) {
      throw new Error(`${tctx}: at most one param may set 'stdin: true' (found ${stdinCount})`);
    }
  }

  seenNames.add(name);
  return { name, description, argv_prefix: prefix, params: toolParams };
}

/** Structural validation of a parsed YAML document. Throws on any violation. */
export function validateManifest(raw: unknown, file: string): Manifest {
  if (!isPlainObject(raw)) {
    throw new ManifestError(file, "manifest must be a YAML mapping");
  }
  const { atom, envelope, timeout_ms, tools } = raw;

  if (typeof atom !== "string" || atom.length === 0) {
    throw new ManifestError(file, "'atom' must be a non-empty string");
  }
  if (typeof envelope !== "boolean") {
    throw new ManifestError(file, "'envelope' must be a boolean");
  }
  if (timeout_ms !== undefined && (typeof timeout_ms !== "number" || timeout_ms <= 0)) {
    throw new ManifestError(file, "'timeout_ms' must be a positive number");
  }
  if (!Array.isArray(tools) || tools.length === 0) {
    throw new ManifestError(file, "'tools' must be a non-empty array");
  }

  try {
    const seenNames = new Set<string>();
    const validatedTools = tools.map((t) => validateTool(t, `manifest '${atom}'`, seenNames));
    return {
      atom,
      envelope,
      timeout_ms: timeout_ms as number | undefined,
      tools: validatedTools,
    };
  } catch (e) {
    throw new ManifestError(file, e instanceof Error ? e.message : String(e));
  }
}

/**
 * Resolve an atom name to its script path, mirroring bin/utils' dispatch
 * rule: `scripts/$atom` (extensionless) or `scripts/$atom.*`, first exec-bit
 * match wins. Glob-sorted to match bash's `$cmd.*` expansion order.
 */
export function resolveAtomScript(scriptsDir: string, atom: string): string {
  const bare = join(scriptsDir, atom);
  const dotMatches = existsSync(scriptsDir)
    ? readdirSync(scriptsDir)
        .filter((f) => f.startsWith(`${atom}.`))
        .sort()
        .map((f) => join(scriptsDir, f))
    : [];

  for (const candidate of [bare, ...dotMatches]) {
    if (!existsSync(candidate)) continue;
    const st = statSync(candidate);
    if (st.isFile() && (st.mode & 0o111) !== 0) {
      return candidate;
    }
  }
  throw new Error(`no executable script found for atom '${atom}' in ${scriptsDir}`);
}

/**
 * Load + validate every *.yaml/*.yml file under manifestsDir. A broken
 * manifest is skipped (named error collected + logged to stderr) — it never
 * takes the whole server down.
 */
export function loadManifests(manifestsDir: string, scriptsDir: string): LoadResult {
  const tools: LoadedTool[] = [];
  const errors: ManifestError[] = [];
  const globalToolNames = new Set<string>();

  if (!existsSync(manifestsDir)) {
    return { tools, errors };
  }

  const files = readdirSync(manifestsDir)
    .filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"))
    .sort();

  for (const file of files) {
    const filePath = join(manifestsDir, file);
    try {
      const raw = parseYaml(readFileSync(filePath, "utf-8"));
      const manifest = validateManifest(raw, file);
      const scriptPath = resolveAtomScript(scriptsDir, manifest.atom);
      const timeoutMs = manifest.timeout_ms ?? DEFAULT_TIMEOUT_MS;

      // Build the whole file's tool list before committing any of it —
      // a name collision partway through must skip the entire file, not
      // just the colliding tool.
      const fileTools: LoadedTool[] = [];
      for (const tool of manifest.tools) {
        if (globalToolNames.has(tool.name)) {
          throw new ManifestError(file, `tool name '${tool.name}' collides with a tool already registered from another manifest`);
        }
        globalToolNames.add(tool.name);
        fileTools.push({
          file,
          atom: manifest.atom,
          envelope: manifest.envelope,
          timeoutMs,
          scriptPath,
          tool,
        });
      }
      tools.push(...fileTools);
    } catch (e) {
      const err = e instanceof ManifestError ? e : new ManifestError(file, e instanceof Error ? e.message : String(e));
      errors.push(err);
      console.error(`[manifest] skipping ${file}: ${err.message}`);
    }
  }

  return { tools, errors };
}
