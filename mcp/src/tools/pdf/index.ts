import { z } from "zod";
import { pushFlag, pushPos } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "pdf.py";
const envelope = true;
const timeoutMs = 60000;

const file = z.string().describe("PDF path.");
const pages = z.string().optional().describe("Page range, e.g. 1-3,5.");
const out = z.string().optional().describe("Output path.");

export const pdfTools: ToolboxTool[] = [
  scriptTool({ name: "pdf_info", description: "Get page count, encryption status, version, metadata, and file size.", inputSchema: { file }, script, envelope, timeoutMs, buildArgs: (input) => ["info", input.file] }),
  scriptTool({
    name: "pdf_extract_text",
    description: "Extract plain text from a PDF, optionally limited to pages.",
    inputSchema: { file, pages, out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["text"];
      pushPos(argv, input.file);
      pushFlag(argv, "--pages", input.pages);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "pdf_extract_comments",
    description: "Extract annotations, highlights, and comments from a PDF.",
    inputSchema: { file, pages, fields: z.string().optional().describe("Comma-separated keys: page,type,author,content,marked_text."), out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["comments"];
      pushPos(argv, input.file);
      pushFlag(argv, "--pages", input.pages);
      pushFlag(argv, "--fields", input.fields);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "pdf_compress",
    description: "Shrink a PDF via Ghostscript recompression.",
    inputSchema: { file, level: z.enum(["screen", "ebook", "printer", "prepress"]).optional().describe("Compression preset. Default: ebook."), out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["compress"];
      pushPos(argv, input.file);
      pushFlag(argv, "--level", input.level);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "pdf_decrypt",
    description: "Remove PDF password protection/encryption. Password is sensitive.",
    inputSchema: { file, password: z.string().optional().describe("Open password, if required."), out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["decrypt"];
      pushPos(argv, input.file);
      pushFlag(argv, "--password", input.password);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "pdf_merge",
    description: "Concatenate two or more PDFs in order.",
    inputSchema: { inputs: z.array(z.string()).describe("Input PDF paths in merge order."), out: z.string().describe("Output path.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["merge", ...input.inputs];
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "pdf_split",
    description: "Extract a page range into a new PDF.",
    inputSchema: { file, pages: z.string().describe("Pages to keep, e.g. 1-3,5."), out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["split"];
      pushPos(argv, input.file);
      pushFlag(argv, "--pages", input.pages);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "pdf_rotate",
    description: "Rotate PDF pages by a multiple of 90 degrees.",
    inputSchema: { file, deg: z.number().describe("Degrees clockwise: 90, 180, 270, or negative equivalent."), pages, out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["rotate"];
      pushPos(argv, input.file);
      pushFlag(argv, "--deg", input.deg);
      pushFlag(argv, "--pages", input.pages);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "pdf_render",
    description: "Render PDF pages to PNG images for visual inspection.",
    inputSchema: { file, pages, dpi: z.number().optional().describe("Render DPI. Default: 150."), out },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["render"];
      pushPos(argv, input.file);
      pushFlag(argv, "--pages", input.pages);
      pushFlag(argv, "--dpi", input.dpi);
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
];
