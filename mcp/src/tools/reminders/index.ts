import { z } from "zod";
import { pushFlag, pushPos } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "reminders.py";
const envelope = true;
const timeoutMs = 60000;

export const remindersTools: ToolboxTool[] = [
  scriptTool({ name: "reminders_list_lists", description: "List Reminders.app lists.", inputSchema: {}, script, envelope, timeoutMs, buildArgs: () => ["show-lists"] }),
  scriptTool({
    name: "reminders_list",
    description: "List reminders in a list.",
    inputSchema: { list_name: z.string().optional().describe("Reminder list name."), show_done: z.boolean().optional().describe("Include completed reminders."), limit: z.number().optional().describe("Maximum reminders.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["list"];
      pushFlag(argv, "--list", input.list_name);
      pushFlag(argv, "--show-done", input.show_done);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({
    name: "reminders_add",
    description: "Add a reminder. Writes to Reminders.app.",
    inputSchema: { name: z.string().describe("Reminder text."), due: z.string().optional().describe("Due time/date."), list_name: z.string().optional().describe("Target list."), notes: z.string().optional().describe("Reminder notes.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["add"];
      pushPos(argv, input.name);
      pushFlag(argv, "--due", input.due);
      pushFlag(argv, "--list", input.list_name);
      pushFlag(argv, "--notes", input.notes);
      return argv;
    },
  }),
  scriptTool({
    name: "reminders_complete",
    description: "Mark the first exact-matching reminder as completed.",
    inputSchema: { name: z.string().describe("Exact reminder name."), list_name: z.string().optional().describe("List to search.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["done"];
      pushPos(argv, input.name);
      pushFlag(argv, "--list", input.list_name);
      return argv;
    },
  }),
  scriptTool({
    name: "reminders_delete",
    description: "Delete the first exact-matching reminder. Destructive.",
    inputSchema: { name: z.string().describe("Exact reminder name."), list_name: z.string().optional().describe("List to search.") },
    script,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["delete"];
      pushPos(argv, input.name);
      pushFlag(argv, "--list", input.list_name);
      return argv;
    },
  }),
];
