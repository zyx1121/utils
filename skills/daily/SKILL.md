---
description: "今日 journal 日報 — Initiative + PPP + Numbers 架構。Triggers on '/utils:daily', '日報', 'daily report', '今天做了什麼'."
argument-hint: "[YYYY-MM-DD]"
---

# Daily Journal

寫今日日報到 `~/.claude/data/utils/journal/reports/<YYYY>/<MM>/<DD>.md`。

## Steps

1. 確定日期：`$1` 或 `$(date +%Y-%m-%d)`。

2. 收集資料：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/journal/scripts/journal-collect" <date>
   ```

   產出 JSON: `totals` / `sessions` / `cwd_distribution` / `prompts` (含完整內容、`source: "live"|"backfill"` tag) / `git`。

3. 用 Skill tool 載入 `journal` skill — 報告**架構與風格規則的單一來源**。Skill 涵蓋：
   - Initiative + PPP + Numbers + Tomorrow 四段骨架
   - 無人稱、Taipei 時間、status emoji、Decisions 格式

4. 補資料源：
   - Memory 新增：glob `~/.claude/projects/*/memory/MEMORY.md` 看 mtime 在當日的條目 (Knowledge 段素材)
   - 昨日 daily：`~/.claude/data/utils/journal/reports/<YYYY>/<MM>/<DD-1>.md` (有的話讀，可在 Tomorrow 段引「延續昨日 X」)
   - SessionEnd Haiku summaries (如有)：`~/.claude/data/utils/journal/sessions/*.md`，當天 mtime 的可作 Initiative 段佐證

5. 從 prompts + commits + cwd 分布**推斷 initiative 群**：同主題的事件合一個 initiative，跨主題的同 cwd 拆兩個 initiative。

6. 目的 path = `~/.claude/data/utils/journal/reports/<YYYY>/<MM>/<DD>.md`。如果該檔案已存在（今天稍早跑過），**先 Read 一次**作為 reference — Write tool 對 existing file 強制 prior Read，且舊版可能有當天較早的 context 值得延續。

7. 按 skill template 寫 markdown，Write 到該 path（目錄不存在先 `mkdir -p`）。

8. 印確認 + 絕對路徑。

## 邊界情況

- **events < 5**：略 `Initiatives` 段、直接寫「Claude Code 可見範圍有限」+ Numbers + Tomorrow
- **檔案已存在**：step 6 必須先 Read 再 Write — 不是 reference 而已，Write tool 會 reject「沒 Read 過的 existing file」
