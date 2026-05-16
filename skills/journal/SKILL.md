---
description: "Journal 報告寫作架構 — Initiative-grouped + PPP + Numbers dashboard。Daily / weekly / monthly 都用同一套骨架。Triggers when generating journal reports via /utils:daily, /utils:weekly, or any '寫日報 / 寫週報 / journal entry about Claude Code activity' task. Load this skill before writing any journal report."
---

# Journal — 寫作架構

Journal 不是日記、不是事件 dump，是 **initiative-based 進度紀錄** — 借鏡 Google snippets / PPP (Progress / Plans / Problems) / devlog 三種業界 pattern 的混合。

啟動這個 skill 後接著寫的 journal 報告必須遵守下方架構。

---

## 核心架構

每份報告四大段，**順序固定**：

1. **Numbers** — code-block 風 dashboard，一眼掃完量化資料
2. **Initiatives** — 按**主題**分組 (不按 cwd / repo)，每個下面：Progress / Next / Decisions / Blocked
3. **Knowledge** — 入庫的學習：memory adds、踩雷、framework 行為發現
4. **Tomorrow / Next cycle** — Forward queue

四段缺一不可。沒內容的子段可以略，但**四大段標題必須出現**。

---

## 規則

### 1. Initiative > cwd / repo

主題分組是主軸。Initiative 從 prompts + commit messages + cwd 變化**推斷**：

- `journal` 是一個 initiative
- "utils v2 hatch" 是一個 initiative (跨 `~/utils` / `~/marketplace` / `~/dotfiles`)
- "stack housekeeping" (TODO / README / config 雜事) 是一個 initiative

同個 cwd 搞兩件事 → **拆兩個**。三個 repo 在做同一件事 → **合一個**。

### 2. 每個 initiative 帶 status emoji

放在 initiative 標題後：

- 🟢 shipped — 該週期內收尾完成
- 🟡 ongoing — 進行中
- 🔵 exploring — spike / research / 還沒定案
- 🔴 stuck — 卡住、需要 unblock
- ⚪ paused — 暫停 / 背景 / 旁支

### 3. PPP: Progress / Next / Decisions / Blocked

每個 initiative 必有 **Progress**。其他選擇性：

- **Progress** — 做了什麼。Bullet, 具體 (file / commit / decision)。
- **Next** — 接下來要做什麼。沒有就略，但 ongoing 通常有。
- **Decisions** — 做了什麼**關鍵選擇 + 為什麼**。這是 devlog 精華。格式：`選 X 而不選 Y — 因為 Z`。沒做關鍵決策就略。
- **Blocked** — 卡在什麼。沒卡就略。

### 4. Numbers 是 dashboard，不是文字

固定 code block，top-of-report：

```
Sessions:  N (active ~Xh, longest <id-short>)
Prompts:   N
Commits:   N across <X> repos
  <repo>: <n> | <repo>: <m> | ...
Memory:    +N
```

Weekly 加 Δ 比較上週：`Sessions: 14  Δ vs W17: +3`。

### 5. 無人稱主語

不寫「你 / 我 / the user / agent」。Subject elision (中文自然)。時間詞當 adverb，不當主語。

### 6. Local time (Asia/Taipei +08:00)

Raw events 是 UTC，輸出**永遠**轉 +8。Sessions / 時間引用必標 `(時間 Asia/Taipei +08:00)`。

### 7. 跨日連續

Weekly 必須引用該週**每日**的 Next 是否被 deliver。Monthly 引 weekly。Daily 可在 Tomorrow 段標「延續昨日的 X」。

### 8. 禁用語句

- **修飾詞**: 顯著提升 / 大幅進展 / 高度生產力 / 完成多項任務 / 持續優化 / 深耕 / 賦能 / 全力以赴
- **人稱**: 你今天 / 我今天 / the user did
- **抒情收尾**: 繼續加油 / 期待明天 / 今天辛苦了

---

## Daily template

```markdown
# YYYY-MM-DD

> [optional one-line headline — 今日主旋律]

## Numbers

(時間 Asia/Taipei +08:00)

\`\`\`
Sessions:  N (active ~Xh, longest <id-short>)
Prompts:   N
Commits:   N across <X> repos
  <repo>: <n> | <repo>: <m> | ...
Memory:    +N (<slug>, <slug>, ...)
\`\`\`

## Initiatives

### `<initiative-name>` <status-emoji>

**Progress**
- ...

**Next**
- ...

**Decisions**
- 選 X 不選 Y — 因為 Z
- ...

**Blocked** (如有)
- ...

### `<another-initiative>` <status-emoji>

(同上)

## Knowledge

- **<topic>** — fact. Why: context / source.
- ...

## Tomorrow

- ...
```

---

## Weekly template

```markdown
# YYYY · Wxx (MM/DD - MM/DD)

> [optional 週的 tag]

## Numbers

(時間 Asia/Taipei +08:00)

\`\`\`
Sessions: 14 (avg 2/day, peak Wed 5)             Δ vs W17: +3
Prompts:  287                                     Δ: +51
Commits:  98 across 9 repos                       Δ: +12
  journal: 18 | utils: 22 | outpost: 14 | ...
Memory:   +6 (Mon 0, Tue 5, Wed 0, Thu 1, Fri 0, Sat 0, Sun 0)
Reports:  7 daily + 1 weekly (this one)
\`\`\`

## Initiatives this week

### `<initiative>` <status>

**Progress arc**
[3-5 句敘事，這 initiative 這週的弧線。週一 X → 週三 Y → 週五 Z。]

**Top decisions** (cross-reference daily)
- (Mon) X over Y — Z
- (Wed) ...

**Open / next cycle**
- ...

### ...

## Knowledge (本週入庫)

[Aggregate daily Knowledge，挑最有複用價值的 3-5 條。重複出現的主題會浮上來。]

- ...

## Next cycle

**Continuing**
- ...

**Starting fresh**
- ...

**Parking** (可省)
- ...
```

---

## Tone calibration

### 範例 1

❌ Bad（人稱 + 修飾）：
> 今天展現了高度的生產力，完成多項任務。

❌ Bad（第二人稱）：
> 你今天大半在跟 auth middleware 拔河。

✓ Good（initiative + decision）：
> ### `auth middleware refactor` 🟢
>
> **Progress**
> - `auth/middleware.ts` 三次重寫
> - commit `fix: third time's the charm`
>
> **Decisions**
> - 選 JWT 而不選 session — 因為前端要支援多端 SSR

### 範例 2 (平淡的一天)

❌ Bad：
> 今天進度穩定，整理了一些待辦。

✓ Good：
> ## Numbers
> ```
> Sessions: 1 (active 35min)
> Prompts:  4
> Commits:  0
> Memory:   0
> ```
> Claude Code 開機時間 < 1h，可見範圍有限。剩下時間估計在讀 paper / IDE / 開會。
> 沒有 initiative-level 進展可記。

---

## 資料稀薄時

`Numbers` 段照寫（即使全 0）。
`Initiatives` 段如果沒任何 initiative 有實質進展，整段省略，**直接寫一句承認**：「Claude Code 可見範圍有限，無 initiative-level 進展」。
跳到 Knowledge + Tomorrow。

---

## Session template

```markdown
# Session <id-short> · YYYY-MM-DD HH:MM-HH:MM

> [optional headline — 這 session 的主軸]

## Numbers

(時間 Asia/Taipei +08:00)

\`\`\`
Started:     HH:MM
Last seen:   HH:MM (active ~Xh Ym)
cwd:         /Users/loki/<...>
git branch:  <branch>
Prompts:     N
Tool calls:  N (Bash: x | Edit: y | Read: z | Write: w | ...)
Files:       N edited
Commits:     N (during session window)
\`\`\`

## Initiatives (this session)

### `<initiative>` <status-emoji>

**Progress**
- ...

**Decisions** (如有)
- 選 X 不選 Y — 因為 Z

## Knowledge (本 session 學到)

- **<topic>** — fact. Why: context.

## Open threads

- [未閉合的問題 / 等下要做的事]
- ...
```

Session template 是 daily 的子集：**無** Tomorrow（per-session 不適合），**加** Open threads（捕捉中斷的脈絡）。`Initiatives` 段通常一兩個 initiative 就好，比 daily 精簡。

## 檔案存放

- Daily → `~/.claude/data/utils/journal/reports/YYYY/MM/DD.md`
- Weekly → `~/.claude/data/utils/journal/reports/YYYY/W<NN>.md`
- Session → `~/.claude/data/utils/journal/sessions/<session-id>.md`
- Monthly (TODO) → `~/.claude/data/utils/journal/reports/YYYY/MM.md`
- Quarterly (TODO) → `~/.claude/data/utils/journal/reports/YYYY/Q<N>.md`
- Yearly (TODO) → `~/.claude/data/utils/journal/reports/YYYY.md`

每寫一份，**完整覆蓋**該路徑。
