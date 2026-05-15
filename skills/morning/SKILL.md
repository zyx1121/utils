---
name: morning
description: Daily briefing skill — pulls yesterday's chronicle daily report, `~/.claude/TODO.md`, Reminders.app default list, today's Calendar events, and recent unread Mail, then proposes today's top 3 focus items with reasoning. Use when the user runs `/utils:morning`.
---

# /utils:morning — daily briefing

Five sources → one focus list. Run all five, integrate, propose top 3 with reasoning.

Don't just dump each source. The whole point is the **judgement** — what should today actually look like, given everything in flight?

## Steps

### 1. Compute dates

```bash
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -v-1d +%Y-%m-%d)           # macOS BSD date
Y=${YESTERDAY:0:4}; M=${YESTERDAY:5:2}; D=${YESTERDAY:8:2}
REPORT=~/.claude/data/chronicle/reports/$Y/$M/$D.md
```

### 2. Chronicle 昨日日報 (optional)

```bash
test -f "$REPORT" && cat "$REPORT"
```

Skip silently if file missing — chronicle is optional, don't fail and don't apologise. Same if the user never ran it yesterday.

### 3. TODO 主清單

Read `~/.claude/TODO.md`. This is the long-running initiative backlog.

### 4. Reminders.app

```bash
utils reminders list
```

Default list. Surface deadline / overdue items first.

### 5. Calendar 今日 events

```bash
utils calendar list --from "$TODAY" --to "$TODAY"
```

Time-of-day commitments. Anything that pins where the day's chunks fit.

### 6. Mail 最近 unread

```bash
utils mail inbox --unread --limit 10
```

If empty: just say "inbox clean", don't pad.

### 7. Integrate & propose

Don't repeat each source. Synthesise:

- 昨日 highlight — chronicle 1-2 lines on what shipped, what's still open
- 進行中 initiative — TODO entries with judgement on stage (剛起 / 過半要收 / 卡關)
- 今日約 — calendar time blocks, esp. fixed-time meetings
- Reminders — overdue + today only, skip far-future
- Inbox — unread that need a today-response

Then propose **top 3** for the day. Each one gets a one-line reason. Common reasons:
- deadline pressure (`兩週試水期到了` / `merge freeze 前要進`)
- blocker for other work (`VM migration 不跑 quant 試跑不到`)
- 進度過半要收 (`outpost README + deployment 一收就 ship 進 Stack`)
- collaboration timing (對方在等 / 老師 group meeting 要 present)

## Output structure

```markdown
# Morning · YYYY-MM-DD

## 昨日 (chronicle)
<1-2 lines, or "— no chronicle yesterday">

## 進行中 (TODO)
- <initiative> — <stage / 卡點>

## 今日約 (calendar)
- HH:MM — <event> (— no events if empty)

## Reminders
- <overdue/today items only>

## Inbox (unread)
- <up to 5 lines: subject — sender, or "inbox clean">

## 今日 top 3
1. <item> — why
2. <item> — why
3. <item> — why
```

## Quality bar

- Run all 5 sources. If one's empty/missing, say so explicitly (`— no chronicle / inbox clean / no events`) — don't silently drop.
- Top 3 must include *reasoning*, not just restate the source line.
- If today is genuinely light, say `今天輕鬆 — 收一下 outpost README 就好` — don't manufacture a fake top 3.
- Cross-reference: if chronicle's 昨日「下一步」isn't in TODO/Reminders, surface it as a possible top-3 candidate.
- This is a **briefing**, not a status report. Length budget: ~30 lines including everything.
