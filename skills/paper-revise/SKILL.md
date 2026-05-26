---
name: paper-revise
description: Use when revising an academic paper against reviewer comments (IEEE / ACM conference style) — provides a checklist for terminology consistency, abbreviation expansion, academic writing conventions, structural forward-references, over-claim avoidance, and reviewer mindset patterns. Triggers on '/utils:paper-revise', '改 reviewer comments', '回應審稿意見', '老師說要改 paper', 'revise paper', 'paper revision checklist', '改 paper'.
---

# /utils:paper-revise — academic paper review checklist

收到 reviewer / 指導老師 / 審稿意見後改 paper 的通用 checklist。IEEE / ACM conference 風格底色 — 10 條 review 心法 + reviewer 視角，動手前先過一遍 self-audit，動完再對一次。

## Workflow

1. **抽 reviewer comments** — PDF annotation 走 `uvx pdfannots <pdf>` 一次抽全部（含 highlight / sticky-note / strike-through）
2. **逐條 verdict**：對每條給 `✓ 已 cover / ⚠ 部分 cover / ✗ 未 cover / N/A`
3. **依下面 10 條 checklist self-audit**：reviewer 沒明示但同類問題往往散在其他段落
4. **改完跑 LaTeX 重編譯**確認頁數 + cross-ref 沒壞
5. **回信給 reviewer 條列改了什麼** — 分塊條列、跟 reviewer 原 comment 對齊、過 claim 的設計判斷要附理由

---

## 1. 全文一致性（最大宗）

多數 reviewer 第一輪就抓「同義詞混用」「格式不統一」。

- **對比詞統一**：「未改前的版本」整篇挑一個（`existing` / `original` / `baseline` / `current` 擇一），不要混用同義詞
- **設計版本詞統一**：`proposed` / `improved` / `new` / `revised` 擇一
- **Section / subsection heading 形式統一**：A/B/C/D 同型（全動名詞 OR 全名詞短語），不要混
- **縮寫定義格式統一**：「全名 (縮寫)」或「縮寫 (全名)」擇一，全文用同一種
- **同類縮寫順序統一**：keyword list / index terms / category list 內字母順序或出現順序保持一致

## 2. 縮寫第一次出現必須定義

- 任何縮寫第一次出現要展開全名
- IEEE Style Manual 標準：「全名 (縮寫)」前置（不是「縮寫 (全名)」）
- Title / Abstract / 主文 各區獨立看，不能假設「上面定義過」
- 同個縮寫不能在不同段落用兩種不同 expansion

## 3. 學術寫作慣例

- **避免 colloquial wording**：口語詞 → 正式詞（e.g., lab → laboratory）
- **弱動詞 → 強動詞**：address → overcome / tackle / resolve
- **模糊形容詞拿掉**：`actual` / `real-world` 沒語境時表達不清
- **被動式自我指涉避免**：`is reported` / `are presented` 邏輯怪（研究自己 report 給自己看？）
- **Forward-reference 段是 IEEE 標配**：Introduction 結尾的 "The remainder of this paper is organized as follows…"
- **Reference 必須按文中首次出現順序排**（不是字母序、不是時間序）
- **Academic reference 比例**：全是 standards / vendor / regulator docs 不夠，要有 peer-reviewed paper

## 4. wording 精確 / 反模糊指代

- 代詞 `it` / `them` / `that` / `those` 必須有**明確 antecedent**
- `the X` 沒指明哪個時要補形容詞（`the proposed X` / `the existing X` / `the previous X`）
- 縮寫式 / 暗示式表達（如 `update by edit`）對讀者來說要展開
- 副句要交代清楚（`X that follows` —— follows 什麼？哪個 section？）

## 5. 句子精簡 / 內容分層

- **Abstract 該砍枝節**：核心訊息留下，細節（數據、列表、廠牌）挪後文
- **Caption 不該重複內文**：caption 一句概括，細節寫在 prose
- **列表式內部細節在摘要級別應抽象化**：不要 `(A, B, C, D)` 在 abstract
- **長句拆短**：用句號分，避免 `; in parallel` / `; on the other hand` 連接

## 6. 結構引導 / forward reference

- Section 開頭該有「we propose X to Y」/「this section presents Z」開頭句
- Background section 該預告後面要動的元件（讓讀者提早抓到 paper 攻擊面）
- 純括號圖表 reference（如 `(Fig. 1)`）IEEE 少見，改 `As illustrated in Fig. 1, ...`
- Section 跟 section 之間過渡該明確

## 7. avoid over-specificity / over-claim

- **不要把廠牌 / 工具 / 實作細節寫進 contribution claim**
- 例子可以 specific（`e.g., XXX`），但 claim 該抽象
- 視覺一致性：圖與圖之間共同元件**該長一樣**（避免讀者誤解「同一個東西怎麼變了」）

## 8. 邏輯流暢 / 重複偵測

- Title 跟 Conclusion 要前後呼應
- Conclusion 用「測 X 驗證 Y、測 Z 證明 W」結構呼應 contribution
- 同份資訊不該重複出現（caption vs 內文、abstract vs conclusion）
- 段落內邏輯 A → B → C 要連貫，跳躍要補橋句

## 9. Reviewer 的問句 vs 斷言

看到「**這邊是不是該用 X？**」「**這個詞想表達什麼？**」這類 question form：

- 是 reviewer **不強制方向、要 author 自己思考**的訊號
- 對應動作：給選項評估後挑一個 + 給理由，不該無視
- 設計判斷型問題（圖該不該改、Section 該不該重排）—— 用「保留 + 內文加 disambig 句」往往比動圖 cheaper 且精準

## 10. 拒絕「extension 視為 limitation」

Contribution 講「extensible / vendor-neutral / any X」時：

- 實際只 demo 一個 X，reviewer 會抓 N=1
- 對策：要嘛收 claim（`validated on one instrument` 之類），要嘛 frame 成「provide the extension point + reference implementation」而非「prove generality」
- Abstract / Conclusion 收 claim 要對稱 —— 一邊改一邊不改 reviewer 會抓頭尾不一致

---

## Reviewer mindset

理解 reviewer 在做什麼 → 改 paper 才不會錯位：

- **Copy-editor + structural editor 混合**：wording 精確、學術慣例、全文一致是三大主軸
- 內容層面用**問句**（不用斷言）讓 author 自己思考方向 —— 看到 question form 不是 "她不確定"，是 "她不想 dictate"
- 視覺一致性跟 wording 一致性都會抓
- N=1 / 過 claim 是高風險區，提早收 claim 比硬撐安全

---

## Anti-pattern

- 把 reviewer comment 當「逐條 to-do」做完就收 —— 漏掉 self-audit 同類問題散在別處
- 過度修導致 5 頁論文 overflow —— 改完一定要重編譯驗證頁數
- 為了「處理 comment」加新概念但不在 paper 框架內 —— 增加 reviewer 下一輪 attack surface
- 對 reviewer 設計判斷型 question 直接動圖／動架構 —— 通常用內文一句 disambig 更精準
- Cross-check 用 generic reviewer agent 但用 top-tier venue 標準（會抓出超出 reviewer scope 的新問題） —— prompt 要明確「只 verify 對齊原 comments，不擴展 scope」
