import { z } from "zod";
import { pushFlag } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "ubereats.py";
const envelope = false;
const timeoutMs = 300000;

const common = {
  recent: z.number().optional().describe("Only include N most recent orders."),
  since: z.string().optional().describe("Only include orders on/after YYYY-MM-DD."),
  until: z.string().optional().describe("Only include orders on/before YYYY-MM-DD."),
  locale: z.string().optional().describe("Uber Eats locale code. Default: tw-en."),
  cookie_file: z.string().optional().describe("Path to raw Cookie header file. Optional: auth falls back to Safari cookies (macOS) then ~/.config/ubereats/cookie.txt."),
};

function pushCommon(argv: string[], input: { recent?: number; since?: string; until?: string; locale?: string; cookie_file?: string }): void {
  pushFlag(argv, "--recent", input.recent);
  pushFlag(argv, "--since", input.since);
  pushFlag(argv, "--until", input.until);
  pushFlag(argv, "--locale", input.locale);
  pushFlag(argv, "--cookie-file", input.cookie_file);
}

export const ubereatsTools: ToolboxTool[] = [
  scriptTool({
    name: "ubereats_fetch_receipts",
    description: "Fetch Uber Eats itemized receipt details into an output directory. Auth: Safari cookies (macOS) or ~/.config/ubereats/cookie.txt fallback.",
    inputSchema: { ...common, out: z.string().optional().describe("Receipt output directory."), no_cache: z.boolean().optional().describe("Force refetch instead of cached JSON.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv: string[] = [];
      pushCommon(argv, input);
      pushFlag(argv, "--out", input.out);
      pushFlag(argv, "--no-cache", input.no_cache);
      return argv;
    },
  }),
  scriptTool({
    name: "ubereats_list_orders",
    description: "List matching Uber Eats past orders without fetching per-order receipt details.",
    inputSchema: { ...common, out: z.string().optional().describe("Directory for index.json.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--list-only"];
      pushCommon(argv, input);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "ubereats_update_ledger",
    description: "Update group-order debt CSVs from Uber Eats orders. Writes debts.csv/names.csv.",
    inputSchema: { ...common, csv_dir: z.string().optional().describe("Ledger CSV directory."), no_cache: z.boolean().optional().describe("Force refetch receipts."), me: z.string().optional().describe("Your Uber display name.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--ledger"];
      pushCommon(argv, input);
      pushFlag(argv, "--csv-dir", input.csv_dir);
      pushFlag(argv, "--no-cache", input.no_cache);
      pushFlag(argv, "--me", input.me);
      return argv;
    },
  }),
  scriptTool({
    name: "ubereats_dump_cookie",
    description: "Export Safari ubereats.com Cookie header to a chmod 600 file. Writes live session credential; requires confirm=true.",
    inputSchema: { path: z.string().describe("Output cookie file path."), confirm: z.literal(true).describe("Required explicit confirmation.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => ["--dump-cookie", input.path],
  }),
];
