---
name: teaching-slides
description: Use when creating, editing, or reviewing slides for recorded courses / online teaching videos — 錄課 / 線上課程 / 磨課師 / MOOC 的投影片，NOT pitch or report decks (那是 keynote-style). 規範：一張一重點、6 行為限、字級 36–60pt、關鍵詞做重點提示、用圖取代文字。Triggers on "錄課", "教學投影片", "課程錄製", "線上課程投影片", "磨課師", "MOOC", "錄影課程", "teaching slides", "course video slides", "review 我的教學投影片".
---

# Teaching Slides — 錄課投影片規範

給**錄製課程影片**用的投影片，不是現場報告 / pitch。面向學生、用來搭配 6–10 分鐘的短影片，所以規範跟 [[keynote-style]] 剛好相反：那邊追求資訊密度（claim title、L0–L3 nested bullets、英文），這邊追求**低密度、一片一重點、好錄好懂**。

跟 `keynote-style` 的分工：

| | `keynote-style` | `teaching-slides`（本檔） |
|---|---|---|
| 場景 | 現場報告 / pitch / demo | 錄課 / 線上課程影片 |
| 語言 | 投影片英文 | **投影片中文**（面向學生） |
| 密度 | 高 — nested bullets 塞滿 | **低 — 一片一重點、≤ 6 行** |
| 標題 | claim / dash 句型 | 知識點名稱即可 |

## 五條投影片規範

每條 = **規範** + **怎麼落地**。

### 1. 一張投影片儘量是 1 個重點

最高原則，其他四條都服務它。一支影片只講一個知識點（見下方*影片切分脈絡*），投影片就跟著一片一概念。

- 一張塞兩個重點 → 拆成兩張
- 判準：這張的口白能不能用一句「這頁要講的是 ___」講完。講不完就是塞太多

### 2. 6 行為限

硬上限。一張投影片本文（不含標題）**最多 6 行**。

- 一個 bullet 算一行，折行也照算（所以短句優於長句）
- 超過就拆頁，不要縮字硬塞
- 落地：`utils keynote list-shapes` dump 出 body text，數換行數對照

### 3. 字級 36–60 pt

字要大，學生在小螢幕 / 手機上也看得清。

- 標題往上限（~54–60pt）、內文往下限（~36pt）
- **36pt 是內文下限**，再小就違規
- 落地：`utils keynote` 不開放讀字級，進 Keynote.app GUI 選 text box 看 Format → Font

### 4. 關鍵詞做重點提示

每張把該強調的詞用**顏色 / 粗體**標出來，不要整頁同一個灰度。

- 一張通常 1–2 個強調點，標太多等於沒標
- 落地：`utils keynote` 不開放 inline 上色，進 GUI 選字 → 改顏色 / 粗體

### 5. 用圖取代文字

能用圖、示意、流程、截圖講清楚的，就不要堆文字。

- 概念關係用圖（箭頭 / 方塊），步驟用流程圖，數據用圖表
- 圖進來通常自然滿足「6 行為限」「一片一重點」
- 落地：圖放進 master 的圖片區，文字降到一句 caption

## 影片切分脈絡（背景，不展開）

投影片之所以要「一片一重點、低密度」，是被**影片怎麼切**反過來驅動的。搭配的單元切分原則：

- 每單元影片 **6–10 分鐘**為限
- 每單元影片 = **1 個知識點**
- 每支影片設計 **1–2 個小 Quiz**

一支 6–10 分鐘影片只講一個知識點 → 那一節的投影片自然就該一片一重點。設計投影片時心裡放著「這是哪支影片、哪個知識點」即可；單元切分本身不在這個 skill 的範圍。

## Tooling

執行走 `utils keynote`（在 PATH，`utils keynote --help` 看 atom 列表），跟 [[keynote-style]] 同一套：

- `list-slides` / `list-shapes` — 先讀現況，`list-shapes` 等於 read-only dump 每個 shape 的 text（拿來數行數 / 看內容）
- `set-title` / `set-body` — 寫標題 / 本文
- `add-slide` / `delete-slide` — 拆頁 / 刪頁
- `preview` / `export` — 出 PDF 對排版字級

`utils keynote` 不開放的部分（字級、inline 上色、bullet 縮排）一律進 Keynote.app GUI 手動處理。atom 不夠用就走 `/utils:review` 升級成新 atom，別繞回 raw `osascript`（見 [[keynote-style]]）。

## Audit / Self-Review

review 既有 deck 或收尾前，一張一張對：

- [ ] 每張只有 **1 個重點**（口白一句講得完）
- [ ] 本文 **≤ 6 行**（折行照算）
- [ ] 內文字級 **≥ 36pt**，標題 ≤ 60pt
- [ ] 每張有 **1–2 個關鍵詞**用顏色 / 粗體標出
- [ ] 能用圖的地方沒有堆成純文字
- [ ] 投影片**中文**（面向學生），不是英文 pitch 風
- [ ] 心裡對得起來：這張屬於哪支 6–10 分鐘影片、哪個知識點

違規最常見的修法是**拆頁**——一張塞太多，拆成兩三張，每張回到一片一重點。
