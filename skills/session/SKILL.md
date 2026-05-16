---
description: "整理 Claude Code session(s) — 單個、最近 N 個、今天所有、特定日期、UUID。Skill 解析範圍後 dispatch session-summarizer agent(s) 並行整理。Triggers on '/utils:session', '整理 session', '這個 session 在幹嘛', '整理今天所有 session', '整理最近 N 個 session', 'summarize this session', 'summarize my sessions'."
argument-hint: "[<session-id> | last <N> | today | <YYYY-MM-DD>]"
---

# Journal Session

整理一個或多個 Claude Code session 成 `~/.claude/data/utils/journal/sessions/<id>.md`。透過 dispatch **session-summarizer** agent (一個 session 一個 agent，多 sessions 並行) 完成；主 context 只負責解析範圍、分派、收結果。

## Why agent, not inline

整理一個 session 要讀整段 transcript + 跑 journal-session 拿 JSON + 寫 markdown，這吃掉的 token 跟 wall time 很可觀。如果在主 session 裡跑，整 5 個 session 就把主 context 灌爆。改成 sub-agent 之後：

- 每個 session 一個 agent，獨立 context window
- 多 session 可以同一個 message 並行 dispatch
- 主 context 只收回 `wrote: <path>` 一行，乾淨

## Steps

1. **解析範圍** — 從 `$1` 或 user 自然語言判斷：

   | 輸入 | 解析 |
   |------|------|
   | 無 args / 「這個 session」 / 「current」 | 當前 session — 跑 `journal-session` 無 arg，它會自動抓 `source=live` 最新一筆 |
   | UUID 形式 | 該 session |
   | `last N` / 「最近 N 個 session」 | 今天 events 裡最後 N 個 session_id |
   | `today` / 「今天所有 session」 | 今天有 prompts 的所有 session_id |
   | `YYYY-MM-DD` / 「<日期> 的 session」 | 該日所有 session_id |
   | 範圍 `YYYY-MM-DD..YYYY-MM-DD` / 「最近三天」 | 跨日所有 session_id |

   解析時跑 `python3 "${CLAUDE_PLUGIN_ROOT}/skills/journal/scripts/journal-collect" <start> [<end>]` 拿 sessions 列表。

2. **過濾**：
   - 排除 `prompts == 0` 的 session（純 resume / 短啟動，無內容可整理）
   - 排除已存在 `~/.claude/data/utils/journal/sessions/<id>.md` 且 mtime 比 session `last_ts` 新的（已是最新整理，跳過）
   - 如果 user 明確說「重寫」/「force」則不過濾

3. **Confirm 大量 dispatch**：
   - 過濾後 session 數 > 5 → 先停下來問 user：「找到 N 個 session，要全部整理還是只取最近 X 個？」避免一次 fire 太多 API。
   - ≤ 5 直接執行。

4. **並行 dispatch** — 用 Agent tool（subagent_type = `session-summarizer`）：

   - **多個 session 一次 message 多個 tool calls**（並行執行，不要 sequential）
   - 每個 agent prompt 帶 `session_id` 跟一行 hint（從 collect JSON 的 `ai_title` 或 cwd 推斷）
   - Agent 自己會跑 journal-session、寫 `sessions/<id>.md`、回傳路徑

5. **收結果** — 印一份 summary table：

   ```
   整理了 N 個 session：
   - <id-short> · <hh:mm-hh:mm> · <cwd> · <headline>
   - ...

   檔案：
   - ~/.claude/data/utils/journal/sessions/<id>.md
   - ...
   ```

   被 agent skip 的 (`no data` / `up-to-date`) 也列出來，標 `skipped`。

## 邊界情況

- **無 live session 可偵測**（無 events / 從未跑過 Claude Code）：印 "no live sessions found" 退出
- **單一 session 走快路** — 只有一個 session 時也透過 agent 跑，不要 inline，保持 entry point 一致
- **多 live session 並行時的當前 session auto-detect**：無 arg 抓「最近一筆 source=live」可能不是執行這個 skill 的 session（背景另一個 Claude Code 視窗剛打 prompt）。要鎖定請給 UUID。找最新 transcript 拿 UUID：

  ```bash
  ls -t ~/.claude/projects/-Users-loki/*.jsonl | head
  ```

## 跟 SessionEnd Haiku auto-summary 的關係

- **SessionEnd hook (auto, Haiku)**：每個 session 結束時自動寫一份輕量 summary 到 `sessions/<id>.md`，作為日報週報的 raw material。沒成本壓力。
- **這個 skill (manual, Sonnet via agent)**：user 主動要求「整理」時跑，產出比 Haiku 版深的 Initiative + Decisions + Knowledge 結構。會覆蓋 Haiku 版。

兩者寫到**同一個檔案路徑**，後寫的覆蓋前寫的，無命名衝突。
