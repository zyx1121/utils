# Reference: anatomy of a good /utils:post

Canonical example: [CLI 是寫給 agent 看的 (gist)](https://gist.github.com/zyx1121/f038ad1d58beb3463030004c9cd22bc4)

讀一次抓 voice，draft 時對照用哪些招。

---

## 1. Skeleton

A ~1500-word personal blog post is 7 moves:

| # | Move | Length | Purpose |
|---|------|--------|---------|
| 1 | Hook | 1 句 | 講核心觀點，禁 "本文" |
| 2 | Pivot | 2-3 句 | 把 hook 攤成 thesis，揭曉 inversion |
| 3 | Contrast section | ~300 字 | "為什麼不是 X、不是 Y" — Goldilocks 三段 |
| 4 | Main body | ~800 字 | N principles（3-5 個），每點 150-200 字 |
| 5 | Implication | ~200 字 | 抽象 → 可動作，numbered list of 3 |
| 6 | Closing | 2-3 句 | Inversion / small observation，不是 summary |
| 7 | References | bullet list | Markdown hyperlink，`*References*` italic header |

範例文 7 個 move 對應：

1. **Hook**：「看起來只是又一個官方 CLI — Linear 有、Vercel 有、GitHub 早就有，Notion 補齊而已。」
2. **Pivot**：「但細看...會發現一件事：這個 CLI 的 primary user 不是人類，是 Claude Code 跟 Cursor。人類順便用。」
3. **Contrast**：## 為什麼不是 REST API、不是 MCP 段
4. **Main body**：## Agent-first CLI 的五個設計原則 段（5 個 H3）
5. **Implication**：## 對自己寫工具的 implication 段（3 條 bold-led 建議）
6. **Closing**：「Notion CLI 不是技術突破，它是承認 agent 已經改變了「誰在用工具」這件事。」
7. **References**：結尾 `*References*` 區

---

## 2. Voice patterns（反覆出現的招）

### Goldilocks 三段

**Template**: 「X 太 A，Y 又太 B，Z 剛好卡在甜蜜點」

**範例**:
> REST API 太底層。Notion 的 block tree 是出名的折磨...
>
> MCP 又太肥。社群 benchmark 不是很客氣...
>
> CLI 剛好卡在甜蜜點。

三段排比 + 每段一個短關鍵字，讀者掃一眼就抓到 thesis。每篇用 1 次。

### 倒裝對比

**Template**: 「Agent 不 X，但它一定會 Y」/「X 是給 A 用的；Y 是反過來」

**範例**:
> Agent 不讀 README，但它一定會讀 error。

> gh 是給人類設計的，agent 順便用得很好。Notion CLI 是反過來：明確為 agent 設計，人類順便用得很好。

對比 + 倒裝是製造記憶點的便宜招。每篇 1-2 次，過多變廉價。

### 粗體強調 takeaway

每段或關鍵點處用 **粗體** 框一個抽象觀察，全文 3-5 個。

**範例**:
> 所以**錯誤本身就是 documentation**。

> CLI 是 **agent 早就會的介面**，你不用教。

不要每段都粗體 — 會稀釋。一段一個 takeaway 是上限。

### 自嘲 / 口語修辭

不矯情 ≠ 沒個性。一兩處口語修辭暖一下：

> Notion 的 block tree 是**出名的折磨**

> 社群 benchmark **不是很客氣**

> 如果你跟我一樣在寫 Claude Code plugin、skill、utility script

### Punchline 收段

每段最後一句要能 stand alone。

**範例**:
> 換句話說，CLI 是 agent 早就會的介面，你不用教。

> 沒有 escape hatch 的 CLI 等於把 agent 鎖在你的抽象裡 — 你想不到的用例它就做不到。

讀者跳讀也能抓到 thesis — 段落首尾要扛得住單獨被截圖貼出來。

---

## 3. 排版 conventions

| 元素 | 規則 |
|------|------|
| H1 | 文章名（短、有 hook，不寫產品名） |
| H2 | 主段落分節，4-6 個 |
| H3 | 細項（如 main body 的 principle 1, 2, 3） |
| `---` | 大段之間插，視覺呼吸，3+ 處 |
| code block | 帶 language tag (` ```bash `, ` ```json `) |
| 表格 | vs 比較 / mapping，不堆資料 |
| inline code | CLI flag、file path、變數名、tool name |
| 段落長度 | 中文一段不超過 4 行 (~100 字) |
| References | 結尾 `*References*` italic header，markdown hyperlink |

---

## 4. 禁用清單

| 不寫 | 為什麼 |
|------|--------|
| 「本文將討論」/「今天來聊聊」 | 浪費 hook 位置 |
| 「前言」/「結論」/「總而言之」/「綜上所述」 | Generic 副標題，文章自己會收 |
| 「請各位」/「讓我們一起」 | 客服 / 教學語氣 |
| Emoji 在內文 | 標題附近最多 1，內文 0 |
| Markdown footnote `[^1]` | References 區就夠 |
| 「我會告訴你...」/「接下來介紹...」 | Meta-narrative，跳過 |
| 每段都粗體強調 | 稀釋 takeaway |
| 「綜合以上幾點」收尾 | 用 punchline 不用 summary |

---

## 5. Self-check checklist

Draft 完跑一次：

- [ ] Hook + pivot 能單獨貼 X / Threads 還有意思？
- [ ] Goldilocks 三段或倒裝對比至少一次？
- [ ] 粗體 takeaway 3-5 個（不超量）？
- [ ] 沒有 generic 副標題？
- [ ] 結尾是 punchline 不是 "結論"？
- [ ] References 用 markdown hyperlink？
- [ ] 字數對齊 ±20%？
- [ ] 內文 emoji 是 0？

全綠才 publish gist。

---

## 6. Living document

寫多了，這份 reference 就要 update：

- 新 pattern 反覆出現 → 加進 voice patterns
- 舊規則沒用 / 變廉價 → 砍
- 範例 gist 累積後 → 多選幾篇當 reference，標 voice 子類（深度技術 / 產業觀察 / 個人 retrospective）

每寫 5 篇 review 一次。
