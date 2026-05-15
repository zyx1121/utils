---
name: post
description: Turn an idea surfaced in conversation into a ~1500-word personal-blog-style article and publish it as a private GitHub gist. Use when the user runs `/utils:post` or says things like "幫我寫成文章 / 整理成 blog / 整理這個 idea 成文章 / 寫一篇 / write this up as a post / draft a blog post". Targets Loki's personal voice — concise, opinionated, low-emoji, no fluffy intros. Not for changelogs, PR descriptions, academic papers.
---

# /utils:post — idea → blog → gist

把對話裡剛剛浮現的觀念，整理成個人 blog 風的文章，丟 private gist。

不是 changelog。不是 PR description。不是 paper。是 **Loki 的個人 blog 風**：
- 簡潔、有觀點、有個性
- 不矯情、不過度 emoji
- 像跟朋友聊，但每段都該有立場

## Steps

### 1. Align angle, length, audience (mandatory)

不要悶頭寫。一個觀念能切多個面向，先用 AskUserQuestion 對齊兩件事：

- **主軸角度** — 設計原則 / 產業解讀 / 概念之爭 / 個人 retrospective / mixed
- **篇幅 / 平台** — short (~800, 社群貼文) / medium (~1500, personal blog) / long (~3000, 深度分析) / 備忘錄

如果 user 已在指令裡指定（"幫我寫一篇 800 字的..."），跳過這步。

### 2. Research（只在引用外部事實時）

並行 fetch references：

```
WebFetch <source URL>
WebSearch <2-3 個方向：社群討論 / 技術比較 / prior art>
```

讓論點有外部 anchor，不要空講。

純抒情文、純概念整理（不引用外部事實）可以直接跳到 step 3。

如果 WebFetch 被擋（403、paywall），別硬翻牆 — 換用 search 拼出全貌即可。

### 3. Draft markdown to `/tmp/<slug>.md`

Slug 用 kebab-case 從標題抽，例：`agent-first-cli.md`。

**風格 checklist**（個人 blog ≠ 技術文件 ≠ 學術 paper）：

- **開頭 hook** — 一句話講核心觀點。禁用「本文將討論...」「今天來聊聊...」
- **觀點先行** — 不平鋪羅列。每段該有立場
- **個性 OK** — 自嘲、形容詞、口語 OK，但別硬擠
- **emoji ≤ 1** — 標題附近最多一個，內文不放
- **不寫 generic 副標題** — 禁用「前言 / 結論 / 總而言之」
- **code block / 表格** — 幫助理解就放
- **References 區放結尾** — markdown hyperlink 格式，不貼 raw URL

字數對齊 user 要求 ±20%。中文以「字」算（不算英文 word）。

### 4. Publish to private gist

```bash
gh gist create /tmp/<slug>.md --desc "<one-line hook from article>"
```

預設就是 secret（不加 `--public`）。Loki 帳號是 `zyx1121`，commit email 走 global config (`yongxiang.zhan@outlook.com`) — 不要 `-c user.email=...` override。

### 5. Report back

只回報：
- gist URL
- 一行文章結構摘要（hook → 中間幾大段 → 收尾）

**不要**在 chat 裡重貼整篇文章 — gist 才是 source of truth。
**不要**追問「要不要推到 blog / 公開 / 分享」— user 想就會說。

如果 user 之後說「推到個人 site」，再 git mv 到對應 repo（例 1909.zyx.tw 或未來的 blog repo）。

## Style anchors

對齊 voice 時可參考：

- `~/dotfiles/.claude/CLAUDE.md` 的 "Coding" 段 — Loki 對文字風格的明文要求（"像朋友聊天，不是客服回工單"）
- `~/utils/README.md` — README 風（口語、ASCII art、自嘲 MIT license「if it breaks, you keep both halves」）
- 過去寫過的 gist — `gh gist list --secret | head` 看歷史 voice

## Quality bar

- 開頭第一句話就有觀點，不是 setup
- 沒有 generic 副標題（前言 / 結論 / 總而言之）
- emoji 標題 0-1 個，內文 0
- 字數對齊 ±20%
- References 用 markdown hyperlink
- Private gist，不公開
- 回報只給 URL + 結構摘要，不重貼內容

## Anti-patterns

- ❌ 直接開寫不對齊角度 — 一個 idea 可以切 3-4 個面向，沒對齊容易做白工
- ❌ 把對話 transcript 當 outline — chat 是探索過程，文章要重新組織
- ❌ 把所有 references 都塞進文中當佐證 — 取 1-3 個最重要的，其他列 references 區
- ❌ 結尾寫「總而言之...」— 好文章用 punchline 收，不用總結
- ❌ 寫完直接公開 gist — Loki 偏好 private，公開時機由他決定
- ❌ 用 -c user.email 改 commit identity — 會跟 GitHub profile 斷鏈（見 `feedback_git_no_email_override`）
