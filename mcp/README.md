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

## Manifest spec v1.1

v1 base is frozen (see ADR-0001). v1.1 adds three lead-approved extensions —
`stdin`, `array`, `cli_false` — that closed real gaps found while writing the
full 16-manifest set (see `manifests/NOTES.md`-derived history in git log).
Nothing else gets bolted on without another explicit sign-off.

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
        type: number          # string | number | boolean | enum | array
        required: false        # omitted = required (only explicit `false` is optional)
        description: "..."
        cli: "--count"          # flag form; booleans append only the flag when true
        cli_false: "--no-count" # v1.1, boolean+cli only: append this when the value is false
                                 # instead of omitting — needed for --on/--off flag pairs whose
                                 # default is true (e.g. typer's --unprivileged/--privileged)
      # positional params use `positional: true` instead of `cli`.
      # stdin params use `stdin: true` instead of `cli`/`positional` (v1.1) —
      # the value is fed to the subprocess's stdin (a synthetic in-memory
      # Blob, never the server's real process.stdin/JSON-RPC stream) instead
      # of argv. At most one `stdin: true` param per tool.
      # -> exactly one of `positional: true` / `cli` / `stdin: true` per param.
      # enum type requires `enum: [a, b, ...]`.
      # array type (v1.1): items are always strings. positional appends every
      # item in order; flagged repeats `cli` once per item. No min-length
      # enforcement — the underlying atom's own validation is the backstop.
```

argv is always built as an array and passed to `spawn` directly — never
shell-joined.

## Manifests

19 manifest files, 66 tools total. `uuid.yaml` / `clipboard.yaml` /
`subject-lift.yaml` are the original M1 pilots; the other 16 map every
actively-used atom (see ADR-0001's usage-driven scoping rule). Notable spots:

- `uuid.yaml` — python envelope atom, `--count` / `--version`.
- `clipboard.yaml` — bash non-envelope atom, `read` / `clear` / `write`
  subcommands via `argv_prefix`. `write`'s `text` param uses `stdin: true`
  (v1.1) — `clipboard.sh write` pipes stdin straight into `pbcopy`, no CLI
  arg exists.
- `subject-lift.yaml` — Swift non-envelope atom, two positional args
  (`input`, `output`), longer `timeout_ms` since first-run Vision model load
  takes a few seconds on top of Swift's interpreted-mode compile step.
- `pve.yaml` — 10 of `pve.py`'s 11 subcommands. `ssh` is excluded: it runs
  `subprocess.run([...])` with fully inherited stdio, which is exactly the
  stdio-hijack ADR-0001 forbids — not a manifest gap, genuinely unsuited to
  MCP as this server is built. Every confirm-gated command (`stop`,
  `destroy`, `clone`, `create-ct`, `dns remove`, `caddy remove`/shrinking
  `add`) already has a `--yes/-y` bypass in the underlying CLI, so all of
  them stay in the manifest with `yes` exposed as a boolean param and the
  destructive consequence stated in the description — see
  `tests/confirm-gate.test.ts` for the evidence that an unconfirmed call
  fails fast instead of hanging. `create_ct.unprivileged` uses `cli_false`
  (v1.1) since the underlying flag pair defaults to `true`.
- `json.yaml` — `pretty` uses `cli_false: "--minify"` (v1.1) for the same
  default-true flag-pair reason.
- `e3p.yaml` — 10 of `e3p.py`'s 11 subcommands. **`e3p_login` is excluded**
  (lead decision, not a manifest gap): its `--password` would flow as a
  plaintext MCP `tool_input` field, which M2's `observe.py` will start
  logging structured for every `mcp__utils__*` call with no redaction path
  yet. Login is low-frequency; use `utils e3p login` directly until
  redaction exists. `e3p_call`'s `params` uses `type: array` (v1.1) for the
  variadic `key=value` list.
- `mail.yaml` — `mail_compose`'s `to`/`cc`/`bcc` use `type: array` (v1.1) for
  the underlying repeatable `--to`/`--cc`/`--bcc` flags.
- `pdf.yaml` — `pdf_merge`'s `inputs` uses `type: array` (v1.1) for the
  variadic 2+ positional path list.
- `ubereats.yaml` — non-envelope, `timeout_ms: 300000` (paginated fetch +
  per-order sleep can run minutes on a large history). `dump_cookie` writes a
  live session credential to disk — treat the output path as sensitive.

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

- `tests/schema.test.ts` — param type → zod schema correctness (including v1.1 `array`), required/optional handling.
- `tests/exec.test.ts` — argv construction (positional / flagged / boolean / enum / argv_prefix ordering, plus v1.1 `array` and `cli_false` behavior and `stdin: true` never reaching argv), the positional-gap guard (`assertNoPositionalGap`), `resolveStdinInput`, envelope→result mapping (success / failure / non-JSON stdout / timeout) against fixture data, and that a `buildArgv` rejection surfaces through `execAtom()` as a normal `isError` result instead of an uncaught rejection.
- `tests/manifest.test.ts` — valid manifest loads correctly; a manifest missing required fields or pointing at a nonexistent atom script is skipped (named `ManifestError`, logged to stderr) without taking the rest of the load down; v1.1 field validation (`stdin`/`array`/`cli_false` legality rules); `resolveAtomScript` cross-checked against the real `../scripts/` dir for all three pilot atoms.
- `tests/confirm-gate.test.ts` — runs a minimal `typer.confirm()` fixture atom through the real `execAtom()` and asserts it aborts fast (non-zero exit, no `timed_out`) under the executor's `stdio[0] = "ignore"` — the ADR-0001 unverified point, now verified.
- `tests/timeout-grace.test.ts` — real-subprocess regression coverage for the `EXEC_GRACE_MS` hardening (see the atom author rule below): an atom that spawns an uncaptured grandchild (`tests/fixtures/scripts/uncaptured-grandchild.py`, the reviewer's repro template for the `mac-app.py` bug) must still resolve within `timeoutMs + EXEC_GRACE_MS` with `timed_out: true` and whatever partial output was collected — not hang for the grandchild's full lifetime. A well-behaved hung atom with no grandchild (`sleep-forever.sh`) is asserted to resolve near `timeoutMs`, proving the grace window doesn't add latency to the ordinary case.

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

## Atom author rule: `capture_output=True` (or equivalent) on every subprocess call

Any `scripts/<atom>` that itself shells out — `subprocess.run`, `Popen`, etc.
— **must** capture that child's stdout/stderr (`capture_output=True` in
Python; the bash/Swift equivalent of not letting a grandchild inherit your
fds). This isn't just about clean error messages.

The MCP executor's timeout guarantee (ADR-0001) works by killing the atom's
**direct child process** and then reading its stdout/stderr pipes to EOF.
`kill()` only signals that one process — it does not touch anything *that*
process itself spawned. If an atom's subprocess call doesn't capture output,
the grandchild inherits the atom's stdout/stderr file descriptors (the same
pipes the executor is reading), and killing the atom does nothing to it. The
pipe's read end then never sees EOF until the orphaned grandchild happens to
exit on its own — which can be arbitrarily long after the MCP call was
supposed to time out.

This actually happened: `scripts/mac-app.py`'s icon-generation and
`git init`/`add`/`commit` calls were missing `capture_output=True`, and a
reviewer reproduced a real hang from it. The executor now bounds this from
its own side too (`EXEC_GRACE_MS` in `lib/exec.ts`, see
`tests/timeout-grace.test.ts`) — a misbehaving atom returns partial output
with `timed_out: true` instead of hanging the MCP response forever — but
that's a backstop, not a substitute for atoms capturing their own children's
output. Fix it at the source.
