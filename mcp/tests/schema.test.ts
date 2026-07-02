import { describe, expect, test } from "bun:test";
import { z } from "zod";
import { paramToZodType, paramsToZodShape } from "../lib/schema.ts";
import type { ManifestParam } from "../lib/manifest.ts";

function required(overrides: Partial<ManifestParam>): ManifestParam {
  return { name: "x", type: "string", ...overrides };
}

describe("paramToZodType", () => {
  test("string type parses strings, rejects numbers", () => {
    const schema = paramToZodType(required({ type: "string" }));
    expect(schema.safeParse("hello").success).toBe(true);
    expect(schema.safeParse(42).success).toBe(false);
  });

  test("number type parses numbers, rejects strings", () => {
    const schema = paramToZodType(required({ type: "number" }));
    expect(schema.safeParse(42).success).toBe(true);
    expect(schema.safeParse("42").success).toBe(false);
  });

  test("boolean type parses booleans, rejects strings", () => {
    const schema = paramToZodType(required({ type: "boolean" }));
    expect(schema.safeParse(true).success).toBe(true);
    expect(schema.safeParse("true").success).toBe(false);
  });

  test("enum type accepts only listed values", () => {
    const schema = paramToZodType(required({ type: "enum", enum: ["a", "b"] }));
    expect(schema.safeParse("a").success).toBe(true);
    expect(schema.safeParse("c").success).toBe(false);
  });

  test("enum type without an enum list throws", () => {
    expect(() => paramToZodType(required({ type: "enum" }))).toThrow();
  });

  test("array type (v1.1) parses string arrays, rejects non-arrays and non-string items", () => {
    const schema = paramToZodType(required({ type: "array" }));
    expect(schema.safeParse(["a", "b"]).success).toBe(true);
    expect(schema.safeParse([]).success).toBe(true);
    expect(schema.safeParse("a").success).toBe(false);
    expect(schema.safeParse([1, 2]).success).toBe(false);
  });

  test("required (default / explicit true) rejects undefined", () => {
    const implicitlyRequired = paramToZodType(required({ type: "string" }));
    const explicitlyRequired = paramToZodType(required({ type: "string", required: true }));
    expect(implicitlyRequired.safeParse(undefined).success).toBe(false);
    expect(explicitlyRequired.safeParse(undefined).success).toBe(false);
  });

  test("required: false accepts undefined", () => {
    const schema = paramToZodType(required({ type: "string", required: false }));
    expect(schema.safeParse(undefined).success).toBe(true);
  });
});

describe("paramsToZodShape", () => {
  test("maps an ordered param list into a raw shape keyed by name", () => {
    const shape = paramsToZodShape([
      required({ name: "count", type: "number", required: false }),
      required({ name: "version", type: "enum", enum: ["4", "7"], required: false }),
    ]);

    expect(Object.keys(shape)).toEqual(["count", "version"]);

    const objectSchema = z.object(shape);
    expect(objectSchema.safeParse({}).success).toBe(true);
    expect(objectSchema.safeParse({ count: 3, version: "7" }).success).toBe(true);
    expect(objectSchema.safeParse({ version: "9" }).success).toBe(false);
  });

  test("empty/undefined params produces an empty shape", () => {
    expect(paramsToZodShape()).toEqual({});
    expect(paramsToZodShape([])).toEqual({});
  });
});
