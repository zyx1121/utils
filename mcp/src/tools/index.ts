import { calendarTools } from "./calendar/index.ts";
import { e3pTools } from "./e3p/index.ts";
import { mailTools } from "./mail/index.ts";
import { pdfTools } from "./pdf/index.ts";
import { pveTools } from "./pve/index.ts";
import { remindersTools } from "./reminders/index.ts";
import { safariTools } from "./safari/index.ts";
import { screenshotTools } from "./screenshot/index.ts";
import { ubereatsTools } from "./ubereats/index.ts";

export const allTools = [
  ...calendarTools,
  ...e3pTools,
  ...mailTools,
  ...pdfTools,
  ...pveTools,
  ...remindersTools,
  ...safariTools,
  ...screenshotTools,
  ...ubereatsTools,
];
