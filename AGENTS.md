# AGENTS.md — global-skills

This repo is a library of reusable AI agent skills. It is **not an application**.
Read this file to understand how to work in, extend, and sync this repo.

## What lives here

```
.agents/skills/<skill-name>/
  SKILL.md          # frontmatter (name, description) + instructions for the agent
  *.py / *.mjs      # supporting scripts the agent runs on demand
.github/
  copilot-instructions.md   # registers all skills; VS Code Copilot reads this
.env                        # gitignored; SYNC_TARGETS for sync-skills
.env.example                # template — copy to .env and fill in paths
```

## Commands

- Sync skills to all repos:  `python .agents/skills/sync-skills/sync_skills.py`
- Dry run sync:              `python .agents/skills/sync-skills/sync_skills.py --dry-run`
- Generate AGENTS.md:        `python .agents/skills/create-agents-md/generate_agents_md.py <repo>`
- Query logs:                `python .agents/skills/query-observability/o2_search.py <logs|traces> "<SQL>" <minutes>`
- Query DB:                  `python .agents/skills/query-db/psql_ro.py "<SQL>"`
- Inspect browser:           `node .agents/skills/inspect-browser/capture.mjs <url>`

## Skill Router

| Task | Skill / action |
|---|---|
| Add a new skill | Create `.agents/skills/<name>/SKILL.md` + script; run sync |
| Propagate skills to other repos | `sync-skills` → run `sync_skills.py` |
| Bootstrap AGENTS.md in a target repo | `create-agents-md` → run `generate_agents_md.py` |
| Debug NestJS app | `debug-nestjs` |
| Debug Next.js app | `debug-nextjs` |
| Debug Remix app | `debug-remix` |
| Debug Node.js (perf, memory, attach) | `debug-nodejs` |
| Debug Python tests / types | `debug-python` |
| Query OpenObserve logs/traces | `query-observability` |
| Inspect browser console/network | `inspect-browser` |
| Query Postgres read-only | `query-db` |

## Adding a new skill

1. Create `.agents/skills/<skill-name>/SKILL.md` with YAML frontmatter:
   ```yaml
   ---
   name: my-skill
   description: >
     One sentence: when to use this skill.
   ---
   ```
2. Add any supporting scripts alongside the SKILL.md.
3. Update `.github/copilot-instructions.md` — add one bullet to the Skills Available section.
4. Run `python .agents/skills/sync-skills/sync_skills.py` to propagate to all target repos.
5. Commit and push.

## Syncing skills to other repos

Target repos are listed in `.env` (gitignored):
```
SYNC_TARGETS=/path/to/repo1,/path/to/repo2,...
```
The sync script symlinks each skill dir into `<target>/.agents/skills/` and injects a
skills registry block into `<target>/.github/copilot-instructions.md`.
It never deletes anything; local skill dirs in target repos are left untouched.

## Conventions

- SKILL.md description: one compound sentence, action-oriented. Keep frontmatter `description` under 3 lines.
- Supporting scripts: Python 3.8+, no third-party deps unless absolutely necessary.
- Scripts must be safe by default: SELECT-only guards, dry-run flags, no destructive defaults.
- Keep each SKILL.md under 200 lines. Dense. Command-first. No prose introductions.

## Research

Underlying strategy documented in `research/`:
- `debugging-strategies.md` — full research report on agent feedback loops, MCP, OTel
- `full-chat-debugging-strategy.md` — distilled summary with tier list
