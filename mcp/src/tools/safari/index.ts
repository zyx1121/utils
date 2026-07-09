import { z } from "zod";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "safari.py";
const envelope = true;
const timeoutMs = 60000;

export const safariTools: ToolboxTool[] = [
  scriptTool({ name: "safari_get_url", description: "Get Safari front tab URL.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["url"] }),
  scriptTool({ name: "safari_get_title", description: "Get Safari front tab title.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["title"] }),
  scriptTool({ name: "safari_get_text", description: "Get visible rendered text from Safari front tab.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["text"] }),
  scriptTool({ name: "safari_list_tabs", description: "List all Safari tabs across windows.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["tabs"] }),
  scriptTool({ name: "safari_open_url", description: "Open a URL in a new Safari tab.", inputSchema: { target: z.string().describe("URL to open.") }, script, envelope, timeoutMs, buildArgs: (input) => ["open", input.target] }),
  scriptTool({ name: "safari_close_tab", description: "Close Safari front tab. Destructive browser state change; requires confirm=true.", inputSchema: { confirm: z.literal(true).describe("Required explicit confirmation.") }, script, envelope, timeoutMs, buildArgs: () => ["close"] }),
  scriptTool({ name: "safari_get_selection", description: "Get current text selection in Safari front tab. Requires JavaScript from Apple Events.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["selection"] }),
  scriptTool({ name: "safari_eval_js", description: "Evaluate JavaScript in Safari front tab. Requires JavaScript from Apple Events.", inputSchema: { expression: z.string().describe("JavaScript expression.") }, script, envelope, timeoutMs, buildArgs: (input) => ["js", input.expression] }),
];
