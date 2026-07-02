// Manifest params -> zod raw shape. `registerTool`'s inputSchema wants a
// `Record<string, ZodTypeAny>` (a "raw shape"), not a constructed
// `z.object(...)` — the SDK wraps that itself.
import { z } from "zod";
import type { ManifestParam } from "./manifest.ts";

export function paramToZodType(param: ManifestParam): z.ZodTypeAny {
  let schema: z.ZodTypeAny;

  switch (param.type) {
    case "string":
      schema = z.string();
      break;
    case "number":
      schema = z.number();
      break;
    case "boolean":
      schema = z.boolean();
      break;
    case "array":
      // Spec v1.1: array items are always strings — no nested item typing.
      schema = z.array(z.string());
      break;
    case "enum": {
      const values = param.enum;
      if (!values || values.length === 0) {
        throw new Error(`param '${param.name}': type 'enum' requires a non-empty 'enum' list`);
      }
      schema = z.enum(values as [string, ...string[]]);
      break;
    }
    default:
      throw new Error(`param '${param.name}': unknown type '${param.type}'`);
  }

  if (param.description) {
    schema = schema.describe(param.description);
  }
  // Absence of `required` defaults to required — only an explicit `false`
  // makes the param optional (matches the manifest spec example).
  if (param.required === false) {
    schema = schema.optional();
  }

  return schema;
}

export function paramsToZodShape(params: ManifestParam[] = []): Record<string, z.ZodTypeAny> {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const param of params) {
    shape[param.name] = paramToZodType(param);
  }
  return shape;
}
