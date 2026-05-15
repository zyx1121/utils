---
name: keynote-style
description: Use when user is creating, editing, or reviewing a Keynote / slide deck / 投影片 / 簡報 — defines Loki's personal deck format. Triggers on "做投影片", "幫我做簡報", "整理成 keynote", "outline 一下", "review my slides", "rewrite this deck", "presentation", "keynote", ".key 檔", "slides". Covers cover-page fields, outline-as-scope-labels, claim-style content titles, nested bullet rules, English copy with explicit subject/object, and Chinese speaker notes that follow bullet order.
---

# Keynote Style — Loki's Format

每份 deck 同一套規範：結構固定、投影片英文、speaker note 中文。

## Tooling

執行一律走 `utils keynote`（已在 PATH，`utils keynote --help` 看完整 atom 列表）。常用：

- `list-slides` / `list-shapes` — 先讀現況
- `set-title` / `set-body` / `set-notes` — 改單張的標題 / bullets / 中文 note
- `add-slide` / `delete-slide` / `delete-shape` — 結構調整
- `set-shape-text` — 處理非 default placeholder 的 layout（如雙欄）
- `preview` / `export` — 出 PDF 對排版

`utils keynote` 還在長，atom 不夠用時補一個比繞回 raw `osascript` 划算 — 走 `/utils:review` 讓它升級成新 atom。

## Deck Structure

### Slide 1 — Cover

三件東西，缺一不可：

- Title
- 日期（YYYY-MM-DD 或 Month YYYY）
- 姓名（詹詠翔 / Loki）

### Slide 2 — Outline

切 scope、切 section，讓聽眾先看到整份的骨架。

- 每條 bullet 用幾個字代表一個 scope，**不是句子**
- Outline 排列順序 = 後面內容頁的順序，一一對應
- 從 outline 讀完應能猜到 deck 在講什麼

範例：`Problem` / `Approach` / `Results` / `Next steps`。不寫成 `What problem we are trying to solve in this work`。

### Slide 3+ — Content

每張內容頁：

- **Title = 這頁的 claim。** 聽眾看 title 就該知道這頁在講什麼。`Background` / `Details` / `Discussion` 這種無內容分類名禁用。
- **Nested bullets** 表達層級。
- 一個 bullet 一件事。塞兩件就拆兩個 bullet。
- 同一個 nest level 的 bullets 必須是相同高度的關聯 — 都是並列 facts、並列 alternatives、並列 steps。混層級就分頁。
- 由上到下要有 narrative：setup → tension → payoff，或 claim → evidence → implication。

## Story Arc Across Slides

整份 deck 是一條線，不是 random walk。

- 每張內容頁的 takeaway 接到下一張的前提
- 跨主題之前，補一張 section divider 告訴聽眾「now we shift to X」
- 從 Slide 2 outline 順著讀，跟實際播放順序對得起來

## Writing — Slide Copy

投影片內文一律**英文**：

- Simple, clear, explicit. 不用學術腔、不用 marketing 詞（`revolutionary` / `best-in-class` / `seamlessly`）
- 主詞受詞寫清楚。不寫 `It improves performance`，寫 `Caching cuts p99 latency by 40%`
- 短句優於長句；一條 bullet 撐不過一行就拆
- 縮寫第一次出現要附全稱

## Speaker Notes — 中文

每張 slide 都附 note：

- **用中文寫。** 投影片英文、note 中文，分工明確
- Note 跟著 slide 上的 bullet 順序，一條 bullet 一段 note
- Note 解釋 why / source / example / 數字怎麼來，**不是逐字念投影片**
- 投影片是主角，note 是 backup line — 投影片站不住，再多 note 也救不回來

## Self-Review Before Done

收尾前一張一張對：

- [ ] Slide 1: title / 日期 / 姓名 三項齊全
- [ ] Slide 2: outline 每條都是 scope label，不是句子
- [ ] 每張內容頁 title 是 claim，不是空泛分類名
- [ ] 沒有 bullet 塞超過一個主題
- [ ] 同 nest level 的 bullets 是同類關聯
- [ ] 從 outline 讀下來，內容頁順序對得起來
- [ ] 每張 slide 都有中文 speaker note
- [ ] 縮寫第一次出現有全稱
