import { describe, expect, test } from "bun:test";
import { allTools } from "../src/tools/index.ts";

describe("native tool registry", () => {
  test("exposes only the selected agent-toolbox domains", () => {
    const domains = new Set(allTools.map((tool) => tool.name.split("_")[0]));

    expect([...domains].sort()).toEqual(["calendar", "e3p", "mail", "md2slide", "pdf", "pve", "reminders", "safari", "screenshot", "ubereats"]);
    expect(allTools).toHaveLength(68);
  });

  test("tool names are unique and prefixed by their domain", () => {
    const names = allTools.map((tool) => tool.name);
    expect(new Set(names).size).toBe(names.length);

    for (const name of names) {
      expect(name).toMatch(/^(calendar|e3p|mail|md2slide|pdf|pve|reminders|safari|screenshot|ubereats)_/);
    }
  });
});
