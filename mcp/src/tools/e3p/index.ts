import { z } from "zod";
import { pushFlag, pushPos } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "e3p.py";
const envelope = true;
const timeoutMs = 60000;

export const e3pTools: ToolboxTool[] = [
  scriptTool({
    name: "e3p_logout",
    description: "Forget the stored E3 token/config file. Destructive credential reset; requires confirm=true.",
    inputSchema: { confirm: z.literal(true).describe("Required explicit confirmation.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: () => ["logout"],
  }),
  scriptTool({ name: "e3p_whoami", description: "Show the authenticated E3 user and site info.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["whoami"] }),
  scriptTool({
    name: "e3p_list_courses",
    description: "List enrolled E3 courses, sorted newest first.",
    inputSchema: { show_hidden: z.boolean().optional().describe("Include hidden/archived courses.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["courses"];
      pushFlag(argv, "--hidden", input.show_hidden);
      return argv;
    },
  }),
  scriptTool({
    name: "e3p_list_assignments",
    description: "List assignments for one course or all enrolled courses. status=true performs extra API calls.",
    inputSchema: { courseid: z.number().optional().describe("Course ID. Omit for all courses."), status: z.boolean().optional().describe("Also fetch submission status per assignment.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["assignments"];
      pushPos(argv, input.courseid);
      pushFlag(argv, "--status", input.status);
      return argv;
    },
  }),
  scriptTool({
    name: "e3p_list_due",
    description: "List upcoming E3 action events and deadlines.",
    inputSchema: { days: z.number().optional().describe("Look-ahead days. Default: 14."), limit: z.number().optional().describe("Maximum events. Default: 50.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["due"];
      pushFlag(argv, "--days", input.days);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({ name: "e3p_get_submission", description: "Get detailed submission status for one assignment.", inputSchema: { assignid: z.number().describe("Assignment ID.") }, script, envelope, timeoutMs, buildArgs: (input) => ["submission", String(input.assignid)] }),
  scriptTool({ name: "e3p_list_grades", description: "List gradebook items for one course or all enrolled courses.", inputSchema: { courseid: z.number().optional().describe("Course ID. Omit for all courses.") }, script, envelope, timeoutMs, buildArgs: (input) => { const argv = ["grades"]; pushPos(argv, input.courseid); return argv; } }),
  scriptTool({ name: "e3p_get_content", description: "Get a course outline with sections and activities.", inputSchema: { courseid: z.number().describe("Course ID.") }, script, envelope, timeoutMs, buildArgs: (input) => ["content", String(input.courseid)] }),
  scriptTool({
    name: "e3p_download_file",
    description: "Download a Moodle pluginfile.php URL with the stored auth token.",
    inputSchema: { url: z.string().describe("pluginfile.php URL."), out: z.string().optional().describe("Output path. Default: URL basename.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["download", input.url];
      pushFlag(argv, "--out", input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "e3p_call",
    description: "Escape hatch for Moodle Web Services. Use only when no typed E3 tool covers the function.",
    inputSchema: { function: z.string().describe("Moodle WS function name."), params: z.array(z.string()).optional().describe("key=value pairs; repeat key[]=v for arrays.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => ["call", input.function, ...(input.params ?? [])],
  }),
];
