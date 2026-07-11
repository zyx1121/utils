import { z } from "zod";
import { pushFlag } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "md2slide.py";
const envelope = true;
const timeoutMs = 60000;

export const md2slideTools: ToolboxTool[] = [
  scriptTool({
    name: "md2slide_init",
    description: "Scaffold a new slide-deck project: slides.md, theme.css, and an empty assets/ dir. Entry point for starting a new deck — the output is hand-editable markdown + theme, not a finished deck.",
    inputSchema: { dir: z.string().describe("Target directory to scaffold (created if missing).") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => ["init", input.dir],
  }),
  scriptTool({
    name: "md2slide_build",
    description: "Render a slides.md into a self-contained HTML deck and a Chrome print-to-PDF. Theme, header/footer, and paginate settings live in the markdown front-matter and the sibling theme.css, not in tool args.",
    inputSchema: {
      md: z.string().describe("Source markdown file."),
      out_dir: z.string().optional().describe("Output directory. Default: alongside the source."),
      format: z.enum(["both", "html", "pdf"]).optional().describe("Which outputs to emit. Default: both."),
    },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["build", input.md];
      pushFlag(argv, "--out", input.out_dir);
      if (input.format === "html") argv.push("--html-only");
      else if (input.format === "pdf") argv.push("--pdf-only");
      return argv;
    },
  }),
];
