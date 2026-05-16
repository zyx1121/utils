---
description: "Raw journal stats — 純數字 JSON，不寫敘事。Triggers on '/utils:stats', 'journal 統計', 'raw stats'."
argument-hint: "[YYYY-MM-DD] [YYYY-MM-DD]"
---

# Journal Stats

吐原始 JSON，不寫敘事。用來 debug 或自己 grep。

## Steps

1. start = `$1` 或 `$(date +%Y-%m-%d)`
2. end = `$2` 或 start
3. 跑：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/journal/scripts/journal-collect" "$start" "$end"
   ```

4. 直接把 JSON 印到 stdout。**不要**寫 markdown、不要寫檔、不要寫敘事。

## Why

每次 daily/weekly 都先看 stats 一眼，是檢查資料品質的習慣。如果 stats 看起來空，daily 寫出來也不會好。
