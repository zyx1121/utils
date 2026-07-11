# utils MCP server

Local stdio MCP server for Loki's agent toolbox. The user is the agent, so the
MCP surface is the product interface; the legacy `../scripts/*` atoms are
implementation details and debug fallbacks.

## Architecture

```text
src/server.ts              MCP entrypoint: registerTools() -> StdioServerTransport
src/core/argv.ts           argv construction helpers
src/core/exec.ts           Bun.spawn wrapper, timeout, envelope/raw output mapping
src/core/tool.ts           native @modelcontextprotocol/sdk tool registration helper
src/tools/<domain>/        one folder per toolbox domain
tests/                     registry + argv contract tests
```

The server uses `@modelcontextprotocol/sdk` directly. There is no YAML manifest
loader. Each domain owns native zod input schemas and explicit tool names.

Tool call flow:

```text
MCP tool -> zod parse -> domain buildArgs() -> runScript()
         -> Bun.spawn(["../scripts/<atom>", ...argv], stdio=["ignore","pipe","pipe"])
         -> structuredContent + mirrored JSON text content
```

Subprocesses never inherit the MCP server's stdin/stdout because those are the
JSON-RPC channel. Tool logs must go to stderr.

## Domains

Only active agent-facing domains are exposed:

- `calendar`
- `e3p`
- `mail`
- `md2slide`
- `pdf`
- `pve`
- `reminders`
- `safari`
- `screenshot`
- `ubereats`

Dormant utilities such as clipboard/json/uuid/tokens/notebooklm remain outside
the MCP surface.

## Naming Rules

- Tool names are `domain_verb_object`, e.g. `pve_add_caddy`,
  `calendar_list_events`, `mail_compose_draft`.
- One MCP tool should represent one agent intent. Do not expose generic
  `action` or `mode` multiplexers when the actions have different required
  inputs.
- Destructive tools must say so in the description and require explicit
  confirmation input when the underlying operation is confirm-gated.
- Sensitive inputs belong in typed tools only when there is no better local
  credential path. Do not MCP-expose password-login tools without a redaction
  path.
- Interactive tools must say they block for user interaction.

## Current Tool Surface

68 tools total:

- `calendar_list_calendars`, `calendar_list_events`, `calendar_add_event`,
  `calendar_search_events`, `calendar_delete_event`
- `e3p_logout`, `e3p_whoami`, `e3p_list_courses`,
  `e3p_list_assignments`, `e3p_list_due`, `e3p_get_submission`,
  `e3p_list_grades`, `e3p_get_content`, `e3p_download_file`
- `mail_list_accounts`, `mail_list_inbox`, `mail_search_messages`,
  `mail_read_message`, `mail_compose_draft`
- `md2slide_init`, `md2slide_build`
- `pdf_info`, `pdf_extract_text`, `pdf_extract_comments`, `pdf_compress`,
  `pdf_decrypt`, `pdf_merge`, `pdf_split`, `pdf_rotate`, `pdf_render`
- `pve_list_guests`, `pve_get_status`, `pve_start_guest`, `pve_stop_guest`,
  `pve_destroy_guest`, `pve_clone_vm`, `pve_create_ct`,
  `pve_list_forwards`, `pve_add_forward`, `pve_remove_forward`,
  `pve_list_dns`, `pve_add_dns`, `pve_remove_dns`,
  `pve_list_caddy`, `pve_add_caddy`, `pve_remove_caddy`
- `reminders_list_lists`, `reminders_list`, `reminders_add`,
  `reminders_complete`, `reminders_delete`
- `safari_get_url`, `safari_get_title`, `safari_get_text`,
  `safari_list_tabs`, `safari_open_url`, `safari_close_tab`,
  `safari_get_selection`, `safari_eval_js`
- `screenshot_full`, `screenshot_area`, `screenshot_window`,
  `screenshot_region`, `screenshot_clipboard`
- `ubereats_fetch_receipts`, `ubereats_list_orders`,
  `ubereats_update_ledger`, `ubereats_dump_cookie`

## Registering With Clients

```bash
# Claude Code
claude mcp add utils -- bun run /absolute/path/to/utils/mcp/src/server.ts
```

Codex:

```toml
[mcp_servers.utils]
command = "bun"
args = ["run", "/absolute/path/to/utils/mcp/src/server.ts"]
```

## Development

```bash
bun install
bun test
bun run typecheck
bun run start
```

Add a new domain tool by editing `src/tools/<domain>/index.ts` or adding a new
domain folder, then export it from `src/tools/index.ts`. Add/adjust tests for
tool count, name prefix, and any nontrivial argv mapping.

## Executor Rules

Any `../scripts/<atom>` that shells out must capture child stdout/stderr. If a
grandchild inherits the direct child's pipe descriptors, killing the direct
child on timeout does not close the pipes and can hang the MCP response. The
executor has a grace cutoff, but the source script still owns subprocess
hygiene.
