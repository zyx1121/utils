---
name: keynote-style
description: Use when user is creating, editing, or reviewing a Keynote / slide deck / 投影片 / 簡報 — defines Loki's personal deck format. Triggers on "做投影片", "幫我做簡報", "整理成 keynote", "outline 一下", "review my slides", "rewrite this deck", "presentation", "keynote", ".key 檔", "slides". Covers cover-page fields, outline-as-section-labels, claim-style content titles, multi-level bullet hierarchy (L0–L3), three body patterns (nested bullets / ASCII tree / comparison table), English copy with explicit subject/object, and optional Chinese speaker notes.
---

# Keynote Style — Loki's Format

每份 deck 同一套規範：結構固定、投影片英文、speaker note 中文（可選）。

## Tooling

執行一律走 `utils keynote`（已在 PATH，`utils keynote --help` 看完整 atom 列表）。常用：

- `list-slides` / `list-shapes` — 先讀現況（list-shapes 顯示每個 shape 的 text，等於 read-only dump）
- `set-title` / `set-body` / `set-notes` — 改單張的標題 / bullets / 中文 note
- `add-slide` / `delete-slide` / `delete-shape` — 結構調整
- `set-shape-text` — 處理非 default placeholder 的 layout（如雙欄）
- `add-table` / `set-cell` — 比較表
- `preview` / `export` — 出 PDF 對排版

`utils keynote` 還在長，atom 不夠用時補一個比繞回 raw `osascript` 划算 — 走 `/utils:review` 讓它升級成新 atom。

## Deck Structure

### Slide 1 — Cover

三件東西，全用 default body / title placeholder：

- Title — 整份 deck 名稱（英文）
- Body line 1 — 日期 `YYYY/M/D`（斜線格式，不是 ISO `YYYY-MM-DD`）
- Body line 2 — 中文姓名 **詹詠翔**（即使整份 deck 英文，cover 簽名仍用中文）

範例：title `Claude Code Plugins`、body `2026/5/18\n詹詠翔`。

機構 / footer（如 `NYCU CS`）是 master template 自帶，不寫進 body。

### Slide 2 — Outline

切 section，讓聽眾先看到整份的骨架。

- 每條 bullet 用幾個字代表一個 section，**不是句子**
- 一個 outline 條目 = 一個 section，但 section 內可有多張 slide（例如 `Components` 對到一張總表 + 每個元件一張詳細）
- Outline 排列順序 = 後面 section 出場順序
- Outline 本身用 flat L0 bullets，不分層

範例：`Plugin Structure` / `Components` / `Use Cases` / `Getting Started`。不寫成 `What problem we are trying to solve in this work`。

### Slide 3+ — Content

每張內容頁：

- **Title = 這頁的 claim 或 dash 句型。** 例 `Skill — instructions Claude can load on demand`。`Background` / `Details` / `Discussion` 這種空殼分類名禁用。
- **Body 用 nested bullets 表達層級**（多數情況）；檔案結構用 ASCII tree、N 個項目並排比較用 table — 見下面 *Body patterns*。
- 由上到下要有 narrative：claim → evidence → implication，不是 random walk。

#### Bullet Hierarchy

Keynote bullet 有層級（L0 / L1 / L2 / L3），同層必同類：

| Level | 角色 | 範例 |
|-------|------|------|
| L0 | section header，以 `:` 結尾 | `File:` / `Trigger:` / `What it does:` |
| L1 | section 下的單一 item | `Claude picks based on description` |
| L2 | L1 的細分、選項、或多步驟拆解 | `` with frontmatter `name`, `description`, ... `` |
| L3 | L2 的具體例子 / 列舉 | `GitHub, Linear, Notion, Slack, ...` |

規則：

- 同一個 nest level 的 bullets 必須是相同高度的關聯 — 都是並列 facts、並列 alternatives、並列 steps
- 一個 bullet 一件事。塞兩件就拆兩個 bullet（同層）或拆成 parent + children（下層）
- L0 句尾用 `:`，L1+ 不用結尾標點
- 不需要每張都用到 L2 / L3 — 階層服務內容，不是裝飾

**Bullet level 只能在 Keynote.app GUI 手動設**（select bullet + Tab 縮排 / Shift-Tab 提升）— Keynote AppleScript dictionary 沒開放 paragraph level 寫入，`set-body` 灌進去的 paragraph 都是 L0。流程：先用 `set-body` 寫完所有文字，再進 GUI 把該縮的 Tab 出去。

#### Body patterns

三種 body 寫法，看 content 性質選：

1. **Nested bullets**（最常用）— 段落式內容，用 L0-L3 階層。範例（slide 6 Agent）：

   ```
   File:                                            ← L0
     `agents/<name>.md`                             ← L1
       with frontmatter `name`, `description`, …    ← L2
   Trigger:                                         ← L0
     Claude picks based on description and …        ← L1
   What it does:                                    ← L0
     the worker runs in its own context …           ← L1
     Use it to keep noisy work out of …             ← L1
     Route lighter tasks to cheaper models …        ← L1
   ```

2. **ASCII tree** — 講檔案 / 目錄結構時用純文字 `├── └── │` 排版（**不是** nested bullets）。Keynote 預設 monospace 渲染這些字元對齊。範例（slide 3）：

   ```
   my-plugin/
   ├── .claude-plugin/
   │   └── plugin.json
   ├── agents/
   │   └── <name>.md
   ├── hooks/
   │   └── hooks.json
   ├── skills/
   │   └── <name>/
   │       └── SKILL.md
   └── .mcp.json
   ```

   寫法：`set-body` 灌進預設 body placeholder 即可，字體顏色 / monospace 由 master template 處理。

3. **Comparison table** — N 個 items 並排比較同一組 dimensions 時用表格，比 nested bullets 易讀。慣例：

   - 第一欄 = item name，**置中**
   - 其他欄 = 各 dimension 描述，**靠左**
   - Header row 配色與內容區分（master template 通常已配好）
   - 行高一致；header ~20pt，內文 ~16-18pt
   - 用 `add-table --rows R --cols C --data "..."` 一次 seed 完整個 grid，再進 GUI 調 cell 字體 / 對齊 / row banding（`utils keynote` 不開放 cell styling）

## Story Arc Across Slides

整份 deck 是一條線，不是 random walk。

- 每張內容頁的 takeaway 接到下一張的前提
- 跨 section 之前，補一張 divider（standalone title page）告訴聽眾 "now we shift to X"
- 從 Slide 2 outline 順著讀，跟實際播放的 section 順序對得起來

## Writing — Slide Copy

投影片內文一律**英文**：

- Simple, clear, explicit. 不用學術腔、不用 marketing 詞（`revolutionary` / `best-in-class` / `seamlessly`）
- 主詞受詞寫清楚。不寫 `It improves performance`，寫 `Caching cuts p99 latency by 40%`
- 短句優於長句；一條 bullet 撐不過一行就拆下一層
- 縮寫第一次出現要附全稱（slide title 或 L0 bullet）
- 程式碼路徑 / 識別字 / config key 用 backtick 包：`` `agents/<name>.md` ``、`` `SessionStart` ``

例外：slide 1 body 的姓名用中文（詹詠翔）。

## Speaker Notes — 中文（可選）

需要時才寫，不是每張都要：

- **要寫就用中文。** 投影片英文、note 中文，分工明確
- Note 跟著 slide 上的 bullet 順序，一條 bullet 一段 note
- Note 解釋 why / source / example / 數字怎麼來，**不是逐字念投影片**
- 投影片是主角，note 是 backup line — 投影片站不住，再多 note 也救不回來
- Cover / outline / divider / 純 demo 頁可以不寫；複雜論述頁建議寫
- 對外分享前（export PDF / PPTX 給聽眾）通常清掉 — note 是給講者自己看的

## Self-Review Before Done

收尾前一張一張對：

- [ ] Slide 1: title / 日期 `YYYY/M/D` / 中文姓名 詹詠翔 三項齊全
- [ ] Slide 2: outline 每條都是 section label，不是句子
- [ ] 每張內容頁 title 是 claim 或 dash 句型，不是空殼分類名
- [ ] Body 用對 pattern：nested bullets / ASCII tree / comparison table 三選一
- [ ] 同 nest level 的 bullets 是同類關聯
- [ ] L0 句尾用 `:`，L1+ 不用結尾標點
- [ ] Bullet level 在 GUI 縮過（不是全部都 L0 平著）
- [ ] 從 outline 讀下來，section 順序對得起來
- [ ] 縮寫第一次出現有全稱
- [ ] 對外分享前該清的 speaker notes 清掉
