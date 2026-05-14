---
name: skills-review
description: Lint Claude Code skills for staleness, malformed frontmatter, weak descriptions, name mismatch, empty bodies. Use when the user runs `/skills:review`, asks "any stale skills?", "lint my skills", "which skills are broken?", or "skills review". Reads `~/skills/` by default (Loki's source-of-truth), reports issues by category, and helps decide what to fix or archive. v1 is static analysis only — usage-side review (zero-trigger detection, false-positive flags) waits for a Claude Code SkillUse hook event.
---

# /skills:review — lint personal skills

Static linter for SKILL.md files under `~/skills/`. Catches issues you'd otherwise only discover when a skill fails to trigger or shows up half-broken mid-conversation. Pairs with `/utils:review` — same "observe → review → act" loop, but for the skills layer.

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

## v1 limits

This is **static analysis only**. It can't tell which skills *should* trigger but don't, or which are triggering inappropriately. The usage-side view needs a `SkillUse` hook event in Claude Code, which isn't available as of this writing. When it lands, v2 of this skill adds:

- **Zero triggers in 30+ days** → archive candidate
- **Frequent trigger but agent overrides** → description too generic
- **High trigger + failure rate** → fix candidate (skill body missing key info)

For now, static lint catches drift between sessions.

## Quality bar

- Don't auto-fix — the linter reports, the human decides
- Stale ≠ delete — many correct skills don't need to change
- Description length thresholds are heuristic; occasionally longer is genuinely necessary
- `name-mismatch` is convention not safety — Claude Code uses the `name:` field at runtime, not the dir name
