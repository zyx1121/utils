import { z } from "zod";
import { pushPos } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "screenshot.sh";
const envelope = false;
const timeoutMs = 60000;
const out = z.string().optional().describe("Output PNG path. Default: /tmp/screenshot.png.");

export const screenshotTools: ToolboxTool[] = [
  scriptTool({
    name: "screenshot_full",
    description: "Capture the full macOS screen to a PNG file. Unattended.",
    inputSchema: { out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv: string[] = [];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "screenshot_area",
    description: "Interactively capture a dragged screen region. Blocks for user interaction.",
    inputSchema: { out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--area"];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "screenshot_window",
    description: "Interactively capture a clicked window. Blocks for user interaction.",
    inputSchema: { out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--window"];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "screenshot_region",
    description: "Capture a known pixel region with no UI interaction.",
    inputSchema: { region: z.string().describe("x,y,w,h."), out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--region", input.region];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({ name: "screenshot_clipboard", description: "Capture full screen to clipboard; no file path is produced.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["--clipboard"] }),
];
