# utils MCP server

Stdio MCP server exposing `../scripts/*` atoms as MCP tools. Design decisions
live in `../decisions/ADR-0001-mcp-tool-provider.md` — read that first, this
file is the how-to.

`bin/utils` stays the CLI entrypoint for SSH / manual / Noir use. This is an
additional transport over the same scripts, not a replacement.

## Architecture

```
server.ts          entry: loadManifests() → registerTool() per tool → StdioServerTransport
lib/manifest.ts     YAML loading + structural validation, atom→script resolution
lib/schema.ts        manifest params → zod raw shape (for registerTool's inputSchema)
lib/exec.ts           argv construction + subprocess spawn + output mapping
manifests/*.yaml     one file per atom, source of truth for its MCP tool(s)
```

Flow per tool call: `registerTool` callback → `buildArgv()` turns validated
args into `[scriptPath, ...argv_prefix, ...params]` → `Bun.spawn` runs it with
`stdio: ["ignore", "pipe", "pipe"]` (subprocess never touches the server's
real stdin/stdout — those are the JSON-RPC channel) → `mapRunOutput()` turns
stdout/stderr/exit code into `{structuredContent, isError}`.

## Manifest spec (frozen — see ADR-0001, don't extend)

```yaml
atom: uuid              # scripts/ base name; resolved like bin/utils:
                         # scripts/$atom or scripts/$atom.*, first exec-bit match wins
envelope: true           # true = python envelope atom (stdout is the
                          # {success,data,metadata} / {success:false,error} JSON contract)
timeout_ms: 60000        # optional, default 60000
tools:
  - name: uuid            # MCP tool name (snake_case, unique across ALL manifests)
    description: "..."     # shown to the calling agent — make it earn its keep
    argv_prefix: []         # fixed leading tokens (e.g. a subcommand)
    params:                  # order matters — argv is built in this order
      - name: count
        type: number          # string | number | boolean | enum
        required: false        # omitted = required (only explicit `false` is optional)
        description: "..."
        cli: "--count"          # flag form; booleans append only the flag when true
      # positional params use `positional: true` instead of `cli` — exactly
      # one of the two must be set, never both, never neither.
      # enum type requires `enum: [a, b, ...]`.
```

argv is always built as an array and passed to `spawn` directly — never
shell-joined.

## Pilot manifests

- `uuid.yaml` — python envelope atom, `--count` / `--version`.
- `clipboard.yaml` — bash non-envelope atom, `read` / `clear` subcommands via
  `argv_prefix`. **`write` is intentionally not exposed** — see the comment
  in the manifest file for why (stdin-only atom input has no manifest-level
  representation under the frozen spec).
- `subject-lift.yaml` — Swift non-envelope atom, two positional args
  (`input`, `output`), longer `timeout_ms` since first-run Vision model load
  takes a few seconds on top of Swift's interpreted-mode compile step.

## Running the server

```bash
bun install
bun run server.ts          # stdio server; talk to it via an MCP client, not directly
```

PATH is prepended at startup with `~/.bun/bin:/opt/homebrew/bin:~/.local/bin`
so atoms that shell out to `uv`/`bun` still resolve when this server is
spawned from an environment with a slim PATH (e.g. the CC GUI app).

## Registering with a client

```bash
# Claude Code (user scope)
claude mcp add utils -- bun run /absolute/path/to/utils/mcp/server.ts

# Codex — add to config.toml
# [mcp_servers.utils]
# command = "bun"
# args = ["run", "/absolute/path/to/utils/mcp/server.ts"]
```

## Tests

```bash
bun test                          # lib/ unit tests + manifest loader fixtures
bunx tsc --noEmit -p tsconfig.json   # type check
```

Coverage:

- `tests/schema.test.ts` — param type → zod schema correctness, required/optional handling.
- `tests/exec.test.ts` — argv construction (positional / flagged / boolean / enum / argv_prefix ordering) and envelope→result mapping (success / failure / non-JSON stdout / timeout), all against fixture data — no real subprocess spawned.
- `tests/manifest.test.ts` — valid manifest loads correctly; a manifest missing required fields or pointing at a nonexistent atom script is skipped (named `ManifestError`, logged to stderr) without taking the rest of the load down; `resolveAtomScript` cross-checked against the real `../scripts/` dir for all three pilot atoms.

## Adding a new manifest

1. Read the atom's script under `../scripts/` — flags come from its actual
   CLI surface, not from guessing.
2. Write `manifests/<atom>.yaml` following the spec above.
3. `bun test` — the loader fixtures don't cover your new file, but a syntax
   or structural error will surface at server startup via the
   `[manifest] skipping ...` stderr line (or from `loadManifests()` directly
   if you add a fixture).
4. Restart the server / re-run `tools/list` against it to confirm the tool
   shows up with the schema you expect.
