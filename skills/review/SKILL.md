---
name: review
description: Review what's drifting in Loki's agent setup — runtime (utils observation log) and static (SKILL.md files). Surfaces new script candidates, fix candidates for failing utils atoms, missed-atom hits (agent skipped a known atom), and lint issues across personal skills. Use when the user runs `/utils:review`, asks "any new utils candidates?", "lint my skills", "what should utils learn next?", "which skills are broken?", "review my agent setup". Reads `~/.claude/data/utils/observations.jsonl` for usage, walks `~/skills/` for static lint.
---

# /utils:review — find what's drifting in the agent setup

Two layers, one entry point:

- **Usage review** — read the observation log, surface ad-hoc patterns, failing atoms, and missed-atom hits
- **Static review** — lint SKILL.md files for malformed frontmatter, weak descriptions, drift

They share a frame: *observe what the agent is actually doing, find the gap, propose a fix.* Run both by default; user can scope to one.

## Scope by request

- "lint my skills" / "any stale SKILL.md" → only Section 2
- "new utils candidates" / "review my log" → only Section 1
- bare `/utils:review` or unclear → run both

## Cross-link between sections

When Section 1 finds a `missed-atom` hit (agent dropped to raw API in a domain `utils <atom>` covers), the fix lives in a skill that should have pointed at the atom. Run Section 2 against that skill specifically (or include it in the broader static pass) and merge findings: a missed-atom hit + `description-short` on the candidate skill is a high-signal pair.

---

# Section 1 — Usage review

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

**`reviewed.jsonl`** (written at Step 9):

```jsonc
{"ts":"…","cluster_key":"…","name":"…","kind":"new-script","action":"promoted"}
{"ts":"…","cluster_key":"…","kind":"fix-existing","action":"promoted"}
{"ts":"…","cluster_key":"missed-atom:keynote:abc-123","kind":"missed-atom","action":"surfaced"}
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

Cluster key: `missed-atom:<atom>:<session>` — per session, so the same atom miss re-surfaces in a later session if the upstream skill still hasn't been fixed.

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

| # | Domain   | Existing atom    | Sample raw call                 | Same-session atom use | Likely upstream skill |
|---|----------|------------------|----------------------------------|-------------------------|--------------------------|
| 4 | Keynote  | utils keynote    | `osascript tell application …`   | yes                     | keynote-style            |
```

The "Likely upstream skill" column is best-effort — match the raw call's session against any skill that was active and could plausibly have routed to the atom. If unclear, leave blank.

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

- "Skill `<name>` should mention `utils <atom>` in its Tooling section" — and if Section 2 also flagged `<name>` with `description-short` or `empty-body`, mention both together
- "Save a `feedback_*` memory: when working in domain X, prefer `utils <atom>`"

The user decides; this skill doesn't auto-edit other skills.

### 9. Append to reviewed.jsonl

After dispatch (don't wait for merge), record:

```bash
echo '{"ts":"<now>","cluster_key":"<key>","name":"<suggested>","kind":"new-script","action":"promoted"}' >> ~/.claude/data/utils/reviewed.jsonl
```

For `missed-atom` hits the user acknowledged, record `"action":"surfaced"` with the session-scoped cluster key so it doesn't re-surface within the same session.

For `none` answers, record `"action":"dismissed"` so the same cluster doesn't reappear.

---

# Section 2 — Static review

Static linter for SKILL.md files under `~/skills/`. Catches issues you'd otherwise only discover when a skill fails to trigger or shows up half-broken mid-conversation.

## What it checks

| Rule | Why it matters |
|------|----------------|
| `no-frontmatter` | Claude Code won't load this skill at all |
| `yaml-parse-error` | Same — frontmatter broken |
| `missing-name` / `missing-description` | Required fields |
| `description-short` (<50 chars) | Probably won't trigger reliably — Claude matches on description keywords |
| `description-long` (>500 chars) | Some hosts truncate the trigger surface |
| `name-mismatch` (frontmatter `name:` ≠ parent dir name) | Convention break; tools that map by dir name get confused |
| `stale` (>90 days unmodified) | Maybe obsolete — review and either freshen or archive |
| `empty-body` | Frontmatter exists, no actual instructions |

## Steps

### 1. Run the linter

```bash
utils skill-lint                    # defaults to ~/skills/
utils skill-lint ~/.claude/skills   # different path
utils skill-lint --verbose          # also list clean skills
utils skill-lint -r                 # recurse (off by default to skip sync artifacts)
```

### 2. Read the output

The table groups by skill with all its issues. The footer shows scan total / with-issues / clean counts. Take the table at face value — don't fabricate explanations.

### 3. Decide per category

- `no-frontmatter` / `yaml-parse-error` — **fix now**, the skill is broken
- `missing-name` / `missing-description` — fix now, required fields
- `description-short` — rewrite. Sweet spot is ~150–400 chars with concrete trigger keywords (verbs the user might say, file types, app names)
- `description-long` — trim; pick the highest-signal trigger phrases, drop redundant restatement
- `name-mismatch` — pick one (usually directory name wins) and align both
- `stale` — open the skill, ask the user "still useful?" — freshen mtime by editing, or archive (move out of `~/skills/`)
- `empty-body` — write actual instructions or delete

### 4. Apply fixes

Edit skill files directly. Use [[feedback-personal-skills-repo]] reminder — `~/skills/` is the source repo, push to GitHub after editing or the next sync wipes the changes.

After fixes, re-run `utils skill-lint` to confirm zero issues for the skills you touched.

## Future — when SkillUse hook lands

Section 2 today is **static only**. It can't tell which skills *should* trigger but don't, or which are triggering inappropriately. When Claude Code adds a `SkillUse` hook event, Section 1's observation log absorbs the new event type and the two sections converge further:

- **Zero triggers in 30+ days** → archive candidate (becomes a Section 1 finding, not Section 2)
- **Frequent trigger but agent overrides** → description too generic (cross-link to Section 2's `description-short` check)
- **High trigger + failure rate** → skill body missing key info (already mirrors missed-atom Step 3.5 in shape)

For now, Section 1 covers runtime via `utils-usage` / `script-run` records, Section 2 covers static lint. Missed-atom hits are the bridge.

---

## Quality bar

- Counts ARE the signal — always show them
- Don't promote single-occurrence patterns from Section 1 unless they're `missed-atom` hits (those are explicitly count=1 OK)
- Don't auto-fix — the linter reports, the human decides
- Be honest when nothing meets the bar — say so plainly, don't fabricate
- Skip clusters where every sample is trivial (`echo`, `cat`, ...) — they slipped past the noise filter
- Stale ≠ delete — many correct skills don't need to change
- `name-mismatch` is convention not safety — Claude Code uses the `name:` field at runtime, not the dir name
