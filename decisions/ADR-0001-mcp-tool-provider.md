# ADR-0001: MCP tool provider layer over the atom scripts

Status: Accepted (2026-07-02)

## Context

- utils is a scripts-only CLI toolbox (30 atoms: 26 Python typer/argparse, 3 bash, 1 Swift) dispatched via `bin/utils`. Its sole real consumer is the kilo agent — 7 weeks of observation logs show 515 atom calls across 84 sessions, 83% concentrated in `pve` + `safari`, and zero manual human usage.
- Decision driver is semantics: MCP is the native contract for agent-facing tools (typed input schemas, structured results, first-class registration in the client), whereas the current skill-doc + CLI path requires the agent to recall shell conventions. The self-evolution loop plans MCP-facing work regardless, so the transport layer converges there either way.
- De-risking spikes ran 2026-07-02 on CC CLI 2.1.198 / bun 1.3.13 / `@modelcontextprotocol/sdk` 1.29.0:
  - **TCC**: the CC CLI → bun stdio server → `osascript` chain inherits the terminal's existing Automation grants (Safari probe: exit 0, no prompt, identical to direct Bash baseline). osascript-backed atoms are viable under MCP.
  - **Hooks**: PostToolUse matchers accept regex for MCP tool names (`mcp__probe__.*` fires). Payload `tool_input` is structured JSON; `tool_response` arrives as the serialized text-content *string*, not a `{content, structuredContent, isError}` object; identical hook commands across multiple matchers are deduped per event.

## Decision

1. **Server**: TypeScript stdio MCP server at `mcp/` inside this repo, run via `bun run`, built on `@modelcontextprotocol/sdk` ^1.29 high-level `McpServer`. No `bun build --compile` (known subpath module-resolution issue). The Node toolchain stays confined to `mcp/`; atom land keeps its zero-ceremony rule.
2. **Tool declaration**: a per-atom manifest (`mcp/manifests/<atom>.yaml`: description, args with simple types, exec, timeout) is the source of truth. A small runtime mapper turns manifests into zod schemas for `registerTool` (SDK v1 does not accept raw JSON Schema). Typer/argparse introspection may bootstrap initial manifests once, but is not a runtime dependency. Only atoms with observed usage get manifests up front; dormant atoms stay CLI-only until needed.
3. **Execution**: the server spawns the same `scripts/<atom>` files with `stdio: ["ignore", "pipe", "pipe"]` — subprocesses must never inherit the server's stdout, which is the JSON-RPC channel. Python envelope output (`{success, data, metadata}` / `{success: false, error}`) maps to `structuredContent` + `isError`; non-envelope atoms (bash/Swift) are wrapped as `{stdout, stderr, exit_code}`.
4. **CLI coexists**: `bin/utils` stays untouched for SSH, Noir, promoter acceptance, and manual use. No flag-day — MCP is an additional transport over the same scripts.
5. **Observability**: scriptorium's `observe.py` gains an `mcp__utils__*` branch (atom name from the tool-name suffix; params from structured `tool_input`; result via `JSON.parse` of the `tool_response` string) and `hooks.json` gets the matching matcher. That change lives in the scriptorium repo.
6. **Registration**: user-scope `claude mcp add utils -- bun run <repo>/mcp/server.ts`; Codex via `[mcp_servers.utils]` in `config.toml`. Same command, both clients.

## Consequences

- (+) Tools carry typed schemas and structured results; the agent sees them as first-class MCP tools instead of recalling CLI conventions from a skill doc.
- (+) Telemetry quality improves: structured `tool_input` replaces Bash-command regex scraping.
- (−) First Node/TS toolchain in the repo, confined to `mcp/`; the README's no-package-ceremony stance now applies to atoms, not the server.
- (−) Manifests are a new artifact that can drift from atom flags; mitigate later with introspection-assisted checks.
- (−) Hook telemetry depends on the tool's text content mirroring `structuredContent` — the MCP spec does not guarantee this, so the server must uphold it as a convention (CC hook payloads only carry the text content string; verified on CC 2.1.198).
- (−) The error-path hook payload (`isError` shape) was not probed; verify during M2.

## Plan

- M1: `mcp/` server MVP + manifests for actively-used atoms; register in CC.
- M2: `observe.py` + `hooks.json` MCP branch (scriptorium repo); probe the error-path payload.
- M3: update kilo-side references — utils skill, KILO.md `utils --list` habit line, pve/macos-dev skill examples, utils-promoter acceptance flow.
- M4: dormant-atom review (11 unused atoms; check each atom's age before retiring).
