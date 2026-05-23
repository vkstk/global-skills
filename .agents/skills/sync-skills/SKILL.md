---
name: sync-skills
description: >
  Sync global skills to all configured target repos. Use when you've added or updated
  a skill in global-skills and want it immediately available in your other projects.
  Symlinks each skill directory into the target repo's .agents/skills/ folder and
  injects a skills registry block into the repo's copilot-instructions.md.
  Safe — never deletes files; skips any skill directory that already exists as a
  local (non-symlink) folder in the target repo.
---

# Syncing Global Skills to Target Repos

## Setup (one-time)

1. Copy `.env.example` to `.env` at the global-skills root and fill in your target repo paths:

```bash
cp /Users/vikas/Code/global-skills/.env.example /Users/vikas/Code/global-skills/.env
# then edit .env — add / remove SYNC_TARGETS entries as needed
```

2. The `.env` is gitignored (machine-local paths).

## Running the sync

```bash
cd /Users/vikas/Code/global-skills

# Dry run — see what would change without touching anything
python .agents/skills/sync-skills/sync_skills.py --dry-run

# Live sync
python .agents/skills/sync-skills/sync_skills.py
```

## What it does per target repo

| Step | Action | Safe? |
|---|---|---|
| Check repo exists | Skip with warning if path absent | Yes |
| Create `.agents/skills/` | Creates dir if missing | Yes |
| Symlink each skill dir | Skips if already correct symlink; skips if local dir exists | Yes — never overwrites |
| Update `copilot-instructions.md` | Injects/refreshes a marked block; leaves all other content untouched | Yes |

## What "available in the repo" means

Each skill dir is symlinked:
```
target-repo/.agents/skills/debug-nestjs  →  global-skills/.agents/skills/debug-nestjs
target-repo/.agents/skills/debug-nextjs  →  global-skills/.agents/skills/debug-nextjs
...
```

VS Code Copilot scans the workspace for `SKILL.md` files and auto-discovers them. Because
the symlinks are inside the workspace, the skills appear in the skills list automatically —
no further configuration required.

Updates to global skills are reflected instantly in all repos (symlinks always point to the
live files). Re-run sync only when adding new skills.

## Adding a new target repo

Edit `.env` and add the path to `SYNC_TARGETS`, then re-run the sync:

```bash
# .env
SYNC_TARGETS=/Users/vikas/Code/existing-repo,/Users/vikas/Code/new-repo
```

## Protecting local skills

If a target repo has its own skill at `.agents/skills/my-local-skill/`, the sync will
never touch it — it only creates symlinks for skills that don't already exist as a
real directory or differently-targeted symlink in the target repo.
