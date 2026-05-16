---
description: "本週 journal 週報 — Initiative + PPP + Numbers + Δ vs 上週 架構。Triggers on '/utils:weekly', '週報', 'weekly report', '這週做了什麼'."
argument-hint: "[YYYY-MM-DD (本週任一天)]"
---

# Weekly Journal

寫週報到 `~/.claude/data/utils/journal/reports/<YYYY>/W<NN>.md`。

## Steps

1. 算 ISO week 範圍：基準日 = `$1` 或今天 → 找出該週週一到週日。ISO week number: `date +%G-W%V` 或 Python `date.isocalendar()`。

2. 收集本週資料：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/journal/scripts/journal-collect" <monday> <sunday>
   ```

3. 收集上週資料（給 Δ 對比 + Top decisions 引用）：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/journal/scripts/journal-collect" <last-monday> <last-sunday>
   ```

4. 用 Skill tool 載入 `journal` skill — Weekly template 在裡面。

5. 讀本週每日 daily（如有）— `~/.claude/data/utils/journal/reports/<YYYY>/<MM>/*.md`。Aggregate 每日 Initiative 找週主軸，aggregate 每日 Decisions 挑 top 3-5 cross-reference。

6. 讀上週 weekly（如有）— `~/.claude/data/utils/journal/reports/<YYYY>/W<NN-1>.md`。比 Sessions / Prompts / Commits 算 Δ，比較 initiative focus 有沒有換軌。

7. 目的 path = `~/.claude/data/utils/journal/reports/<YYYY>/W<NN>.md`。如果該檔案已存在（本週稍早跑過），**先 Read 一次**作為 reference — Write tool 對 existing file 強制 prior Read。

8. 按 skill weekly template 寫 markdown — Numbers (含 Δ) → Initiatives this week (含 Progress arc / Top decisions / Open) → Knowledge (本週入庫) → Next cycle (continuing / starting fresh / parking)。

9. Write 到該 path。印確認 + 路徑。

## 重點

週報不是日報拼貼。是抽**主軸弧線** + **跨日對比** + **Top decisions 引用**。同個 initiative 跨多日，週報講它的 arc（週一 X → 週三 Y → 週五 Z）。

## 邊界情況

- **沒日報**：直接從 events + git 寫，承認「無 daily aggregate」
- **sessions < 3**：寫 Numbers + 一段「本週 Claude Code 可見範圍有限」，略 Initiatives 段
- **無上週資料**：Δ 段寫「W<NN-1> 無 journal，無從比較」
- **檔案已存在**：step 7 必須先 Read 再 Write — Write tool 會 reject「沒 Read 過的 existing file」
