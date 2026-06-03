# review-checklist — 對舊 Next.js 專案做 house-style audit

逐 dimension 對。每項給：**check（要看什麼）** / **pass（對齊長相）** / **flag（偏離就標）**。
反模式表在最後 — 那些是從舊 repo 實際撈到的、**確定不要傳播**的東西。

review 報告請按 dimension 分組，每個 finding 標 `[hard]`/`[soft]` + 一句修法。安全項（auth / RLS）即使全 repo 都沒做也要 flag — 那是 bug 不是風格。

---

## 1. 專案結構 [hard]

- [ ] App Router、無 `src/`、root-level？
- [ ] `tsconfig.json` 只有單一 `@/* → ./*` alias？
- [ ] 沒有殘留 Pages Router（`pages/` 目錄）？
- **flag**：用了 `src/`（除非整個 repo 一致且有理由）、多重雜亂 alias、app+pages 混用。

## 2. 命名 [hard]

- [ ] 檔名全 kebab-case（含元件、hook）？
- [ ] 元件識別字 PascalCase、hook `use-` 前綴 camelCase？route 資料夾小寫、`[id]` 動態段？
- **flag**：PascalCase 檔名（`LoginForm.tsx`）、typo 檔名、route 資料夾大寫。

## 3. 樣式 / Tailwind [hard]

- [ ] **沒有** `tailwind.config.*`？theme 在 `app/globals.css`（`@import "tailwindcss"` + `@theme inline`）？
- [ ] color tokens 用 oklch、有 `:root` + `.dark`？`postcss.config.mjs` 只掛 `@tailwindcss/postcss`？
- [ ] `cn()` 在 `lib/utils.ts` 且實際被 import 使用？`cva` 只在 `components/ui`？
- **flag**：還有 `tailwind.config.js`（= Tailwind v3 殘留或誤裝）、HEX 色硬寫、`clsx`/`tailwind-merge`/`cva` 裝了沒用（dead scaffold dep）、`cn` 缺失。

## 4. 元件組織 [soft]

- [ ] `components/ui/` 放 shadcn primitives、feature 元件平放或 colocate？
- [ ] `components.json` 的 alias 指向真實存在的檔（特別是 `@/lib/utils`）？
- [ ] headless 用 unified `radix-ui` / `@base-ui/react`，不是一堆 `@radix-ui/react-*` scoped 包？
- **flag**：`components.json` alias 指向不存在的檔、scoped radix 包散落（舊式，新專案收斂成 unified）、全平鋪沒有 `ui/` 分層（小站可接受）。

## 5. 資料層 / Supabase [hard 若用 Supabase]

- [ ] client 拆 `lib/supabase/{server,client}.ts` + proxy client？用 `@supabase/ssr`？
- [ ] server client 是 `async createClient()` + `await cookies()`？
- [ ] `createAdminClient()`（`SUPABASE_SECRET_KEY`）只在 server、有註解、沒被 client import？
- [ ] env 用 publishable-key 命名，不是 legacy `ANON_KEY`？
- **flag**：用 raw `@supabase/supabase-js` 在該用 SSR 的地方、admin client 可能被 client bundle、單一 client 檔卻宣稱三層。

## 6. 資料流 [hard 結構 / soft 選型]

- [ ] 寫入走 server action（`"use server"` + getUser + early-return `{error}` + revalidate）？
- [ ] 讀取走 async Server Component？
- [ ] 若用 react-query（OK，一等公民）：有集中 query-key factory（`hooks/query-keys.ts`）+ onSuccess invalidate？
- **flag [hard]**：**100% client-side 資料層、零 server component/action**（舊 cluster 反模式 — 見下表）。
- **flag [soft]**：react-query 散裝沒有 query-key factory、手刻 fetch + useEffect。

## 7. Auth [hard / 含 security]

- [ ] gate 在 `proxy.ts`（不是 `middleware.ts`）？呼叫 `getUser()`、有 `publicPaths` allowlist？
- [ ] **[security]** OAuth callback 有 open-redirect guard（`next.startsWith('/') && !startsWith('//')`）？
- [ ] 跨子網域：cookie 有加固（UTF-8 filter / size warn / domain / sameSite lax / secure）？
- **flag**：legacy `middleware.ts`（建議改名 `proxy.ts`）、**缺 open-redirect guard（一律 flag，這是漏洞）**、auth 只靠 RLS 沒有 app-layer 檢查。

## 8. RLS / migrations [hard / 含 security]

- [ ] **[security]** 沒有 `using(true)` / `with check(true)` 開放策略？
- [ ] migrations version-control 在 `supabase/migrations/*.sql`？
- [ ] DB 型別是 `supabase gen types` 產的 `types/supabase.ts`，不是手寫 interface？
- **flag**：`using(true)`（**一律 flag，PII 外洩風險**，要 `TODO(security):` + 時程）、schema 只在遠端沒進 repo、手寫 `types/database.ts`（drift 風險）。

## 9. 表單 [hard]

- [ ] native `<form>` + `FormData` + 手刻驗證？錯誤回傳 `{error}|{success}` / sonner？
- **flag**：app 表單用 `react-hook-form`/`zod`、validation throw exception 沒接住、錯誤用 `window.alert`（建議統一成 `{error}` + toast）。

## 10. Next 16 慣例 [hard]

- [ ] `params` 型別是 `Promise<{...}>` 且 `await`？
- [ ] auth/data 頁 `dynamic = 'force-dynamic'`、fs/cookie route handler `runtime = 'nodejs'`？
- **flag**：同步存取 `params`（Next 16 會壞）、該 pin dynamic/runtime 沒 pin。

## 11. Tooling [hard lint / soft format]

- [ ] ESLint 9 flat config（`eslint.config.mjs` + `eslint-config-next`）？沒有 `.eslintrc`？
- [ ] 套件管理用 bun（`bun.lock`）？
- [ ] **Prettier 3 + `prettier-plugin-tailwindcss`**，雙引號 + 分號，且 repo-wide 跑過、CI 有檢查？
- **flag**：legacy `.eslintrc`、npm/pnpm（除非有理由）、無 formatter 或引號/分號 drift、有 `.prettierrc` 但沒 repo-wide 跑。

## 12. 收尾衛生 [soft]

- [ ] 沒有 create-next-app 殘留（預設 README/metadata、`public/*.svg`、未動的 scaffold）？
- [ ] 有 `.env.example`？README 有 banner + 結構？serious app 有 Sentry + 測試？
- **flag**：scaffold 殘留、缺 `.env.example`、UI app 卻用 inline `style={{}}` 不用 Tailwind。

---

## 反模式表（確定不要傳播；review 撈到就標 + 給修法）

| 反模式 | 哪來的（evidence） | 修法 |
|---|---|---|
| **100% client-side 資料層**（browser client 包在 TanStack Query，零 server component/action） | bento, debit, directory, leave, temp（2026-04 cluster） | 新 app 用 RSC 讀 + server action 寫；react-query 留給真正 client-interactive 的，不是預設 |
| **手寫 DB 型別** `types/database.ts` | bento, directory, debit, 1909, leave | 改 `supabase gen types` → `types/supabase.ts` |
| **無 in-repo migrations**（schema/RLS 只在遠端或 TS 註解） | bento, debit, directory, leave, temp, link | schema/RLS 進 `supabase/migrations/*.sql` |
| **`using(true)` / 開放 RLS** | 1909 expenses UPDATE, directory members SELECT | 收斂成最小權限策略；暫時放寬要 `TODO(security):` + 時程 |
| **dead shadcn scaffold dep**（clsx/twMerge/cva 裝了沒 import、alias 指向不存在的檔） | link, zyx.tw | 移除 dead dep 或補上 `cn()`；修 `components.json` alias |
| **npm 不用 bun** | mediatek | 遷 bun（`bun install` 重生 lockfile） |
| **create-next-app 殘留**（預設 README/metadata、`public/*.svg`） | test, mcp.winlab, temp | ship 前清乾淨 |
| **`@media prefers-color-scheme` only、無 next-themes** | test, mcp.winlab | 改 `next-themes` class 策略 |
| **inline `style={{}}` 不用 Tailwind** | mcp.winlab page | 改 Tailwind utility（MCP backend UI 薄可放寬） |

---

## 強度速查（這條有多硬？）

- **universal（16/16）**：App Router 無 src、Tailwind v4 無 config、kebab 檔名、ESLint flat config。
- **dominant（多數 + 全部最新）**：bun、shadcn、Supabase `@supabase/ssr`、`proxy.ts` auth、next-themes。
- **emerging（只有最新幾個，但是該走的方向）**：RSC + server actions、unified/base-ui headless、Sentry + 測試、生成型別 + in-repo migrations。
- **security（無視 prevalence，一律對齊）**：open-redirect guard、不用 `using(true)`、admin client 不外洩。

> review 時：universal/dominant 偏離 → 直接 flag；emerging 沒跟上 → 標「可升級到新方向」；security → 當 bug 處理。
