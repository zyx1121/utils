# utils

Loki's agent toolbox: local scripts plus a native stdio MCP server.

`utils` keeps small machine-local capabilities close to the machine: Calendar,
Mail, Reminders, Safari, screenshots, PDFs, PVE, E3, Uber Eats, and other
personal automation. Humans can still call scripts through the CLI; agents
should use the MCP server.

## CLI

Install the dispatcher shim:

```bash
printf '#!/usr/bin/env bash\nexec "$HOME/utils/bin/utils" "$@"\n' > ~/.local/bin/utils && chmod +x ~/.local/bin/utils
```

Use it:

```bash
utils --list
utils calendar list
utils safari url
utils screenshot
```

Python scripts use PEP 723 and run through `uv`; bash and other executable
scripts work as long as they have a shebang and exec bit.

## MCP

The MCP server lives in `mcp/` and uses `@modelcontextprotocol/sdk` directly.
It exposes only active agent-facing domains:

```text
calendar e3p mail pdf pve reminders safari screenshot ubereats
```

Register it:

```bash
claude mcp add utils -- bun run /absolute/path/to/utils/mcp/src/server.ts
```

Codex:

```toml
[mcp_servers.utils]
command = "bun"
args = ["run", "/absolute/path/to/utils/mcp/src/server.ts"]
```

## Layout

```text
bin/utils      CLI dispatcher
scripts/       script atoms, each self-contained
lib/           shared script helpers
mcp/src/       native MCP server and domain tools
```

## Development

```bash
cd mcp
bun install
bun test
bun run typecheck
```

## License

[MIT](LICENSE)
