#!/usr/bin/env bun
// utils MCP server — stdio transport, exposes utils/scripts/* atoms as MCP
// tools. Manifest-driven (see mcp/README.md + decisions/ADR-0001). No flag
// day: bin/utils stays the CLI entrypoint, this is an additional transport
// over the same scripts.
import { join } from "node:path";
import { homedir } from "node:os";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { loadManifests } from "./lib/manifest.ts";
import { paramsToZodShape } from "./lib/schema.ts";
import { execAtom } from "./lib/exec.ts";

// CC GUI app / other slim-PATH spawners may not have bun/uv on PATH — the
// subprocess needs uv to run Python atoms. Prepend, don't replace.
function withAugmentedPath(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const home = homedir();
  const extra = [join(home, ".bun", "bin"), "/opt/homebrew/bin", join(home, ".local", "bin")];
  return { ...env, PATH: `${extra.join(":")}:${env.PATH ?? ""}` };
}

process.env = withAugmentedPath(process.env);

const REPO_ROOT = join(import.meta.dir, "..");
const MANIFESTS_DIR = join(import.meta.dir, "manifests");
const SCRIPTS_DIR = join(REPO_ROOT, "scripts");

const server = new McpServer({ name: "utils", version: "0.1.0" });

const { tools, errors } = loadManifests(MANIFESTS_DIR, SCRIPTS_DIR);

for (const loaded of tools) {
  const { tool, scriptPath, envelope, timeoutMs } = loaded;

  server.registerTool(
    tool.name,
    {
      description: tool.description,
      inputSchema: paramsToZodShape(tool.params),
    },
    async (args) => {
      const result = await execAtom({
        scriptPath,
        tool,
        args: args as Record<string, unknown>,
        envelope,
        timeoutMs,
      });

      return {
        // Convention (ADR-0001 Consequences): content[0].text must mirror
        // structuredContent as a JSON string — hook telemetry parses this.
        content: [{ type: "text", text: JSON.stringify(result.structuredContent) }],
        structuredContent: result.structuredContent,
        isError: result.isError,
      };
    },
  );
}

console.error(`[utils-mcp] registered ${tools.length} tool(s) from ${MANIFESTS_DIR}${errors.length ? `, ${errors.length} manifest(s) skipped` : ""}`);

const transport = new StdioServerTransport();
await server.connect(transport);
