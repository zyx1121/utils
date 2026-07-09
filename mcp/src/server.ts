#!/usr/bin/env bun
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { allTools } from "./tools/index.ts";
import { registerTools } from "./core/tool.ts";

const server = new McpServer({ name: "utils", version: "0.2.0" });

registerTools(server, allTools);
console.error(`[utils-mcp] registered ${allTools.length} native tool(s)`);

const transport = new StdioServerTransport();
await server.connect(transport);
