---
name: utils-review
description: Review the utils observation log to surface candidates for new scripts in zyx1121/utils or fixes to existing ones. Use when the user runs `/utils:review` or asks "any new utils candidates?", "what should utils learn next?", "review my utils log", or similar. Reads `~/.claude/data/utils/observations.jsonl`, clusters repeated ad-hoc scripts, flags failing utils-script invocations, presents a candidate table, and hands approved candidates to the `utils-promoter` agent.
---

# /utils:review — find what utils should grow into

Two kinds of candidates come out of the log:

1. **New script candidates** — `write-script` and `script-run` records that repeat semantically (same task pattern, same libraries, same input/output type). Two or more = candidate.
2. **Existing script issues** — `utils-usage` records where `interrupted=true` or `stderr_tail` is non-empty. Recurring failures = fix candidate.

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
```

If both empty: say so plainly. Don't fabricate.

### 7. Ask which to promote

> "Promote which? Reply with numbers (e.g. `1,3`), `all`, or `none`."

### 8. Hand off to utils-promoter

For each approved candidate, dispatch the `utils-promoter` agent. Provide:
- `pattern_description` — one paragraph
- `samples` — 2-3 example observations
- `suggested_name` — kebab-case
- `kind` — `new-script` or `fix-existing`

### 9. Append to reviewed.jsonl

After dispatch (don't wait for merge), record:

```bash
echo '{"ts":"<now>","cluster_key":"<key>","name":"<suggested>","kind":"new-script","action":"promoted"}' >> ~/.claude/data/utils/reviewed.jsonl
```

For `none` answers, record `"action":"dismissed"` so the same cluster doesn't reappear.

## Quality bar

- Counts ARE the signal — always show them
- Don't promote single-occurrence patterns, no matter how clean
- Be honest when nothing meets the bar
- Skip clusters where every sample is trivial (`echo`, `cat`, ...) — they slipped past the noise filter
