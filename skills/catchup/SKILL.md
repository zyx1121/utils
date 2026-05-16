---
description: "補寫漏掉的 journal 報告 — launchd 漏跑 (laptop 睡太久 / 關機過) 後手動補日報週報。Triggers on '/utils:catchup', '補日報', '補週報', 'backfill journal'."
argument-hint: "[<days>=14]"
---

# Journal Catchup

掃過去 N 天（預設 14），找出「該日有 Claude Code 活動但沒報告」的日期，補寫。

## 為什麼需要

launchd `StartCalendarInterval` 在 Mac 睡眠時會在 wake 時補跑**一次**（多天 missed 會 coalesce 成一次），關機時則完全錯過。所以可能漏好幾天的日報。

這個 skill 就是漏跑後的補丁。

## Steps

1. N = `$1` or `14`
2. 算出今天往前 N 天的日期列表
3. **找漏掉的日報**：對每個日期 D
   - 跑 `journal-collect <D>`，看 `totals.sessions > 0`（該日有活動）
   - 檢查 `~/.claude/data/utils/journal/reports/<YYYY>/<MM>/<DD>.md` **不存在**
   - 兩條件都成立 → 加進補寫列表
4. **找漏掉的週報**：對最近 3 個 ISO week
   - 跑 `journal-collect <monday> <sunday>`，看該週至少有 3 個 active 日
   - 檢查 `~/.claude/data/utils/journal/reports/<YYYY>/W<NN>.md` **不存在**
   - 兩條件都成立 → 加進補寫列表
5. 對每個漏掉的日報，按 `skills/daily/SKILL.md` 的流程寫 (Bash → journal-collect → Skill journal → Write report)
6. 對每個漏掉的週報，按 `skills/weekly/SKILL.md` 的流程寫
7. 最後印一行 summary：

   > 補了 X 個日報、Y 個週報。最早的是 YYYY-MM-DD。

## 注意

- **不會重寫已存在的報告**。如果想 force 重新生成某天，自己先 `rm` 舊的再跑 `/utils:daily <date>`。
- 補寫資料來源是 `~/.claude/projects/*/*.jsonl` transcripts 加 git log，**不**包含當時的 IDE / 開會 / paper 資料，無法 retroactive 看到更多東西。
- 如果 catchup 找到 > 7 個漏掉的日報，**先停下來問 user**：「找到 N 個漏掉的日報。要全部補寫，還是只補最近 X 天？」避免一次 fire 太多 API。
