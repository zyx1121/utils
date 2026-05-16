---
description: "現在 journal 快照 — 拉最近 N 小時看你在幹嘛。Triggers on '/utils:now', '現在在幹嘛', 'snapshot'."
argument-hint: "[hours=4]"
---

# Journal Now Snapshot

拉最近 N 小時（預設 4）的活動，stdout 印口語化摘要。**不存檔**。

## Steps

1. N = `$1` 或 `4`
2. 跑 `python3 "${CLAUDE_PLUGIN_ROOT}/skills/journal/scripts/journal-collect" $(date +%Y-%m-%d)` 拿今天資料
3. 在記憶體中過濾 events 到「最近 N 小時」(以 `now - N hours` 為下界)
4. 列出：
   - 開了幾個 session、active cwd
   - Prompt 數 + 最主要的主題（看 cwd 或 prompt 內容推斷）
   - Git 動向（如果有）
5. 印一段 2-4 句口語摘要，不寫檔案

## 範例輸出

> 過去 4 小時你開了 3 個 session，主要在 `~/journal` 跟 `~/dotfiles`。Prompt 數 47，看起來在 scaffold 新 plugin。Git 還沒 commit。

## 風格

短、口語、沒 markdown 結構（直接 prose）。像同事問你 "現在在幹嘛" 你回的那種一兩句。
