import { z } from "zod";
import { pushFlag, pushPos } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "mail.py";
const envelope = true;
const timeoutMs = 130000;

export const mailTools: ToolboxTool[] = [
  scriptTool({ name: "mail_list_accounts", description: "List configured Mail.app accounts.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["accounts"] }),
  scriptTool({
    name: "mail_list_inbox",
    description: "List recent inbox messages across Mail.app accounts.",
    inputSchema: { unread: z.boolean().optional().describe("Only unread messages."), limit: z.number().optional().describe("Maximum rows. Default: 20.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["inbox"];
      pushFlag(argv, "--unread", input.unread);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({
    name: "mail_search_messages",
    description: "Search inbox subject and sender by substring.",
    inputSchema: { query: z.string().describe("Subject/sender substring."), limit: z.number().optional().describe("Maximum rows. Default: 20.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["search"];
      pushPos(argv, input.query);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({ name: "mail_read_message", description: "Read the first inbox message whose subject matches. Returns full body.", inputSchema: { subject: z.string().describe("Exact subject preferred; falls back to contains.") }, script, envelope, timeoutMs, buildArgs: (input) => ["read", input.subject] }),
  scriptTool({
    name: "mail_compose_draft",
    description: "Open a visible Mail.app draft. User reviews and sends manually; this never auto-sends.",
    inputSchema: {
      to: z.array(z.string()).describe("Recipient addresses."),
      subject: z.string().describe("Subject line."),
      body: z.string().optional().describe("Body text."),
      cc: z.array(z.string()).optional().describe("CC addresses."),
      bcc: z.array(z.string()).optional().describe("BCC addresses."),
      account: z.string().optional().describe("Send-from account name."),
    },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["compose"];
      pushFlag(argv, "--to", input.to);
      pushFlag(argv, "--subject", input.subject);
      pushFlag(argv, "--body", input.body);
      pushFlag(argv, "--cc", input.cc);
      pushFlag(argv, "--bcc", input.bcc);
      pushFlag(argv, "--account", input.account);
      return argv;
    },
  }),
];
