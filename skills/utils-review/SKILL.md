---
name: utils-review
description: Review the utils observation log to surface candidates for new scripts in zyx1121/utils or fixes to existing ones. Use when the user runs `/utils:review` or asks "any new utils candidates?", "what should utils learn next?", "review my utils log", or similar. Reads `~/.claude/data/utils/observations.jsonl`, clusters repeated ad-hoc scripts, flags failing utils-script invocations, presents a candidate table, and hands approved candidates to the `utils-promoter` agent.
---

# /utils:review — find what utils should grow into

Three kinds of candidates come out of the log:

1. **New script candidates** — `write-script` and `script-run` records that repeat semantically (same task pattern, same libraries, same input/output type). Two or more = candidate.
2. **Existing script issues** — `utils-usage` records where `interrupted=true` or `stderr_tail` is non-empty. Recurring failures = fix candidate.
3. **Missed-atom hits** — single `script-run` records that drop to a raw API for a domain `utils` already covers (e.g. `osascript tell application "Keynote"` when `utils keynote` exists). Even count=1 counts here — the signal is "agent skipped a known atom", not repetition.

## Schema

Both log files key each record by a `kind` field — different value spaces for different files.

**`observations.jsonl`** (written by the `observe.py` hook):

```jsonc
{"ts":"…","session":"…","cwd":"…","kind":"write-script","path":"…","content_hash":"…","content_preview":"…"}
{"ts":"…","session":"…","cwd":"…","kind":"script-run","command":"…","interrupted":false,"stderr_tail":""}
{"ts":"…","session":"…","cwd":"…","kind":"utils-usage","script":"…","command":"…","interrupted":false,"stderr_tail":""}
```

**`reviewed.jsonl`** (written by this skill at Step 9):

```jsonc
{"ts":"…","cluster_key":"…","name":"…","kind":"new-script","action":"promoted"}
{"ts":"…","cluster_key":"…","kind":"fix-existing","action":"promoted"}
{"ts":"…","cluster_key":"…","kind":"missed-atom","action":"surfaced"}
{"ts":"…","cluster_key":"…","kind":"new-script","action":"dismissed"}
```

(Historical note: `observations.jsonl` used `"type"` instead of `"kind"` before 2026-05. Migrate old logs with `jq -c '.kind = .type | del(.type)' obs.jsonl | sponge obs.jsonl` if needed.)

## Steps

### 1. Check log exists

```bash
LOG=~/.claude/data/utils/observations.jsonl
test -s "$LOG" || { echo "no observations yet — go write some throwaway scripts first"; exit 0; }
wc -l "$LOG"
```

### 2. Pull the last 30 days

```bash
python3 - <<'PY'
import json, datetime as dt, pathlib
log = pathlib.Path.home() / ".claude/data/utils/observations.jsonl"
cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
for line in log.read_text().splitlines():
    try:
        rec = json.loads(line)
        ts = dt.datetime.fromisoformat(rec["ts"])
        if ts >= cutoff:
            print(line)
    except Exception:
        continue
PY
```

### 3. Cluster `write-script` and `script-run`

Look for semantic similarity, not byte-equal:
- Same library imports (PIL, requests, pandas, ...)
- Same task shape (parse X → transform → emit Y)
- Same shell command skeleton (e.g. `python -c "from PIL ..."`)
- Same input/output type (image, JSON, URL, ...)

Cluster of size ≥ 2 = new script candidate. Suggest a kebab-case name.

### 3.5 Detect missed-atom hits

The clusterer in Step 3 needs ≥2 occurrences. Misses where the agent dropped to a raw API once, when an existing `utils <atom>` already covers the domain, slip past. Catch them explicitly here.

For each `script-run` record in the window: does the command shape fall in a domain that an existing `utils <atom>` already covers? Use `utils --list` as ground truth — don't hardcode a domain table that will rot.

Common shapes to check:

- `osascript tell application "<App>"` → `utils <app-lower>` if listed (`keynote` / `safari` / `mail` / `reminders` / `calendar` / `notify` / `clipboard` / `screenshot`)
- `sqlite3 <macOS-app-db>` → check for matching atom
- `ssh pve` / `ssh gateway` → `utils pve`
- `gh api` / `curl https://api.github.com` → check for `utils gh-*`

Hit counts even at count=1 — the existence of the atom is the signal, not repetition. Strong bonus signal: same session also has a `utils-usage` record for that atom — meaning the agent knew about the atom and still dropped to raw.

Cluster key: `missed-atom:<atom>` (one row per atom per session, even if multiple raw calls).

### 4. Aggregate `utils-usage`

Each record's `script` field holds the subcommand name (e.g. `uuid`, `ssl-check`). Group by it. Track:
- total calls
- failures: `interrupted=true` OR `stderr_tail` non-empty

If failures ≥ 30% AND total ≥ 3, flag as a fix candidate.

### 5. De-dupe against reviewed

```bash
REVIEWED=~/.claude/data/utils/reviewed.jsonl
test -f "$REVIEWED" || touch "$REVIEWED"
```

Skip clusters whose key is already in `reviewed.jsonl`.

### 6. Present candidate tables

```
## New script candidates

| # | Pattern                       | Count | Sample (truncated)         | Suggested name |
|---|-------------------------------|-------|-----------------------------|----------------|
| 1 | PIL convert + resize          |   3   | `python -c "from PIL ..."`  | image-resize   |
| 2 | JSON path extract             |   2   | `python -c "import json..."` | json-extract  |

## Existing script issues

| # | Script       | Calls | Failures | Recent stderr                |
|---|--------------|-------|----------|-------------------------------|
| 3 | ssl-check    |   5   |    3     | `connection refused`         |

## Missed-atom hits

| # | Domain   | Existing atom    | Sample raw call                 | Same-session atom use |
|---|----------|------------------|----------------------------------|-------------------------|
| 4 | Keynote  | utils keynote    | `osascript tell application …`   | yes                     |
```

If all three empty: say so plainly. Don't fabricate.

### 7. Ask which to promote

> "Promote which? Reply with numbers (e.g. `1,3`), `all`, or `none`."

### 8. Hand off

For `new-script` / `fix-existing` candidates, dispatch the `utils-promoter` agent. Provide:
- `pattern_description` — one paragraph
- `samples` — 2-3 example observations
- `suggested_name` — kebab-case
- `kind` — `new-script` or `fix-existing`

For `missed-atom` hits, **do not** dispatch utils-promoter — the fix isn't in `utils`, it's in whatever skill/memory should have pointed the agent at the atom. Surface the gap with the recommended fix shape:

- "Skill `<name>` should mention `utils <atom>` in its Tooling section"
- "Save a `feedback_*` memory: when working in domain X, prefer `utils <atom>`"

The user decides; this skill doesn't auto-edit other skills.

### 9. Append to reviewed.jsonl

After dispatch (don't wait for merge), record:

```bash
echo '{"ts":"<now>","cluster_key":"<key>","name":"<suggested>","kind":"new-script","action":"promoted"}' >> ~/.claude/data/utils/reviewed.jsonl
```

For `missed-atom` hits the user acknowledged, record `"action":"surfaced"` so the same `(atom, session)` pair doesn't keep surfacing.

For `none` answers, record `"action":"dismissed"` so the same cluster doesn't reappear.

## Quality bar

- Counts ARE the signal — always show them
- Don't promote single-occurrence patterns, no matter how clean
- Be honest when nothing meets the bar
- Skip clusters where every sample is trivial (`echo`, `cat`, ...) — they slipped past the noise filter
