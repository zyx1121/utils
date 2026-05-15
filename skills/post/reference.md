# Reference: anatomy of a good /utils:post

Canonical examples:

- **Thesis-driven**: [CLI 是寫給 agent 看的](https://gist.github.com/zyx1121/f038ad1d58beb3463030004c9cd22bc4) — 推 inversion / 對抗 default
- **Retrospective**: [我重寫了 GitHub profile](https://gist.github.com/zyx1121/53949a0f0a28170821762136b326c1fe) — 分享自己做了什麼 / 個人 reflection

讀過抓 voice，draft 時對照用哪些招。

---

## 1. Skeletons

兩種 valid skeleton。**寫之前先判斷 motivation 對哪邊**：

| Skeleton | 適用 | 標誌語 |
|----------|------|--------|
| **1A. Thesis-driven** (議論文) | 有論點要 argue、push inversion、對抗業界 default | "我覺得 X 該換成 Y" |
| **1B. Retrospective** (個人視角) | 分享自己做了什麼、reflection、純記錄當下 | "我最近 X 了，分享一下" |

選錯 skeleton 是大部分 voice 問題的根源 — 想 share 自己做的事卻用 thesis 結構，會變 lecture / "一包一貶"；想 push 觀點卻用 retrospective 結構，論點 hedge 過頭沒 takeaway。

### 1A. Thesis-driven (7 moves, ~1500 字)

| # | Move | Length | Purpose |
|---|------|--------|---------|
| 1 | Hook | 1 句 | 講核心觀點，禁 "本文" |
| 2 | Pivot | 2-3 句 | 把 hook 攤成 thesis，揭曉 inversion |
| 3 | Contrast section | ~300 字 | "為什麼不是 X、不是 Y" — Goldilocks 三段 |
| 4 | Main body | ~800 字 | N principles（3-5 個），每點 150-200 字 |
| 5 | Implication | ~200 字 | 抽象 → 可動作，numbered list of 3 |
| 6 | Closing | 2-3 句 | Inversion / small observation，不是 summary |
| 7 | References | bullet list | Markdown hyperlink，`*References*` italic header |

範例（agent-first-cli）7 個 move 對應：

1. **Hook**：「看起來只是又一個官方 CLI — Linear 有、Vercel 有、GitHub 早就有，Notion 補齊而已。」
2. **Pivot**：「但細看...會發現一件事：這個 CLI 的 primary user 不是人類，是 Claude Code 跟 Cursor。人類順便用。」
3. **Contrast**：## 為什麼不是 REST API、不是 MCP 段
4. **Main body**：## Agent-first CLI 的五個設計原則 段（5 個 H3）
5. **Implication**：## 對自己寫工具的 implication 段（3 條 bold-led 建議）
6. **Closing**：「Notion CLI 不是技術突破，它是承認 agent 已經改變了「誰在用工具」這件事。」
7. **References**：結尾 `*References*` 區

### 1B. Retrospective (4-5 moves, ~1200 字)

| # | Move | Length | Purpose |
|---|------|--------|---------|
| 1 | Personal news | 1 句 | 「我最近 X 了」直陳事實，不掛 thesis |
| 2 | Why now | ~150 字 | 為什麼這個時機做這件事，個人脈絡 |
| 3 | What I did | ~600 字 | N 個具體項目，每項「我用 X 做什麼」直接敘述，不加抽象 category |
| 4 | What I learned | ~300 字 | 觀察自己的 thinking pattern，最後一條帶 punchline 自然收尾 |
| 5 | References | bullet list | Markdown hyperlink |

範例（我重寫了 GitHub profile）4 個 move 對應：

1. **Personal news**：「最近重寫了一次自己的 GitHub profile。」
2. **Why now**：「主要動機是過去一年多花了大量時間在想「怎麼跟 agent 合作」這件事⋯下面 5 個 repo 各自回應其中一塊。」
3. **What I did**：## dotfiles / utils / scriptorium / baogan / outpost 5 個項目
4. **What I learned**：## 重寫過程中想的事 3 條 pattern，最後一條收在「Profile 該長成 living document，不是 final answer」punchline

### 怎麼選

- **想 push inversion / 對抗 default** → thesis-driven。Goldilocks 三段是 power tool。
- **想分享自己做的事 / 過程中的觀察** → retrospective。沒 contrast、沒 implication 命令式、沒 thesis pivot。
- **既想 share 自己做什麼又想推論點** → 通常是 thesis 但 hook 從個人故事切。**警告**：很容易變「一包一貶」結構 — 嘴上稱讚他人但結構上設為 negative example，下筆要 self-audit。

---

## 2. Voice patterns（反覆出現的招）

⚠ 標 *thesis-only* 的招在 retrospective 用了會出現 "一包一貶" / lecture 感。

### Goldilocks 三段 *(thesis-only)*

**Template**: 「X 太 A，Y 又太 B，Z 剛好卡在甜蜜點」

**範例**:
> REST API 太底層。Notion 的 block tree 是出名的折磨...
>
> MCP 又太肥。社群 benchmark 不是很客氣...
>
> CLI 剛好卡在甜蜜點。

三段排比 + 每段一個短關鍵字，讀者掃一眼就抓到 thesis。每篇 1 次。

### 倒裝對比 *(thesis-leaning)*

**Template**: 「Agent 不 X，但它一定會 Y」/「X 是給 A 用的；Y 是反過來」

**範例**:
> Agent 不讀 README，但它一定會讀 error。

> gh 是給人類設計的，agent 順便用得很好。Notion CLI 是反過來：明確為 agent 設計，人類順便用得很好。

製造記憶點的便宜招。Thesis 1-2 次。Retrospective 用要小心引發貶人感。

### 粗體強調 takeaway *(兩種都用)*

每段或關鍵點處用 **粗體** 框一個抽象觀察，全文 3-5 個。

**範例**:
> 所以**錯誤本身就是 documentation**。

> CLI 是 **agent 早就會的介面**，你不用教。

不要每段都粗體 — 會稀釋。一段一個 takeaway 是上限。

### 自嘲 / 口語修辭 *(兩種都用)*

不矯情 ≠ 沒個性。一兩處口語修辭暖一下：

> Notion 的 block tree 是**出名的折磨**

> 社群 benchmark **不是很客氣**

> 如果你跟我一樣在寫 Claude Code plugin、skill、utility script

### Punchline 收段 *(兩種都用)*

每段最後一句要能 stand alone。

**範例（thesis）**:
> 換句話說，CLI 是 agent 早就會的介面，你不用教。

**範例（retrospective）**:
> Profile 該長成 living document，不是 final answer。

讀者跳讀也能抓到 thesis / takeaway — 段落首尾要扛得住單獨被截圖貼出來。

---

## 3. 排版 conventions（兩種共用）

| 元素 | 規則 |
|------|------|
| H1 | 文章名（短、有 hook，不寫產品名） |
| H2 | 主段落分節，4-6 個 |
| H3 | 細項（thesis 的 principle / retrospective 的項目） |
| `---` | 大段之間插，視覺呼吸，3+ 處 |
| code block | 帶 language tag (` ```bash `, ` ```json `) |
| 表格 | vs 比較 / mapping，不堆資料 |
| inline code | CLI flag、file path、變數名、tool name |
| 段落長度 | 中文一段不超過 4 行 (~100 字) |
| References | 結尾 `*References*` italic header，markdown hyperlink |

---

## 4. 禁用清單

### 4A. 兩種 skeleton 都禁

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
| 自行發明抽象 category 當分類軸 | 例：硬塞「Identity / Capability / Memory」打包 — 改成具體「我用 X 做 Y」 |
| Paraphrase README 上的 stars / forks 數字 | 一律 `gh repo view --json stargazerCount,forkCount` 拿即時值，README stat 是 stale |
| 文學化動詞（"慢慢沉澱"、"徐徐展開"、"緩緩流淌"） | Loki voice 簡潔有力 — 改 punchy 動詞（"變成"、"組起來"、"做出來"） |

### 4B. Retrospective 特別禁

| 不寫 | 為什麼 |
|------|--------|
| Contrast section（"為什麼不是 X、不是 Y"） | 結構性製造對立，會變 lecture |
| 「該 / 應該 / 不該」命令式 | 個人視角不下普世規範 |
| 把他人 work 當 negative example 開頭 | 即使後面 disclaimer "他很厲害" 結構上仍是貶低 |
| Implication 段「下次寫 X 該做 Y」 | 那是 thesis 結尾風，retrospective 用 punchline 自然收 |
| Goldilocks 三段 | 排比結構暗示「前兩個 inferior、第三個 superior」— 不適合純分享 |
| 「share 一下你的版本」/「蠻好奇大家怎麼寫」 | 強行邀請互動 — 單純分享即可，讀者要回應自然會回 |

### 4C. Thesis 特別禁

| 不寫 | 為什麼 |
|------|--------|
| 「沒有標準答案」「看情境」收尾 | Thesis 該下立場，hedging 等於沒 thesis |
| 「我這次嘗試的」這種 hedge | 削弱 inversion 力道，改 punchy 斷言 |

---

## 5. Self-check checklist

Draft 完跑一次 — 對應你選的 skeleton。

### 5A. Thesis-driven

- [ ] Hook + pivot 能單獨貼 X / Threads 還有意思？
- [ ] Goldilocks 三段或倒裝對比至少一次？
- [ ] 粗體 takeaway 3-5 個（不超量）？
- [ ] 沒有 generic 副標題？
- [ ] 結尾是 punchline 不是 "結論"？
- [ ] Inversion 在 pivot 段明確揭曉？
- [ ] References markdown hyperlink？
- [ ] 字數對齊 ±20%？
- [ ] 內文 emoji 0？

### 5B. Retrospective

- [ ] Hook 是「我最近 X 了」直陳，不是觀點？
- [ ] What I did 是「我用 X 做 Y」具體敘述，沒 abstract category？
- [ ] 沒有 contrast section / 沒有 Goldilocks？
- [ ] What I learned 是觀察自己 pattern，不是命令式 advice？
- [ ] 結尾在 What I learned 最後一條 punchline 自然收，沒有強行 invitation？
- [ ] 提到他人 work 時純 neutral / 不當 negative example？
- [ ] 動詞 punchy 不文學（無「慢慢沉澱」之類）？
- [ ] References markdown hyperlink？
- [ ] 字數對齊 ±20%？
- [ ] 內文 emoji 0？

全綠才 publish gist。

---

## 6. Living document

寫多了，這份 reference 就要 update：

- 新 pattern 反覆出現 → 加進 voice patterns
- 舊規則沒用 / 變廉價 → 砍
- 範例 gist 累積後 → 多選幾篇當 reference，標 voice 子類
- 第三種 skeleton 出現（敘事 / case study / 對話形式 ...） → 加 1C

每寫 5 篇 review 一次。**Codify 之前先 N≥2 觀察**：第一次出現的 pattern 是 sample，不是 rule。
