---
name: create-agents-md
description: >
  Generate a dense, router-based AGENTS.md (or CLAUDE.md) for any repo.
  Use when bootstrapping a new project, onboarding a repo to agent-assisted
  development, or refreshing an outdated AGENTS.md. Detects frameworks from
  package.json / pyproject.toml, maps scenarios to the right skills via a
  router table, and lists all available skills with when-to-load guidance.
  Run generate_agents_md.py targeting any repo; outputs a ready-to-commit file.
---

# Creating AGENTS.md / CLAUDE.md

## What a good AGENTS.md contains

Based on research findings (see `/research/debugging-strategies.md`):

- **Commands** — exact shell commands to run before declaring done (typecheck, lint, test, build)
- **Skill router** — maps diagnostic scenarios to the skill that handles them
- **Debug feedback sources** — which skill to load for logs/traces/browser/db/perf
- **Conventions** — coding rules the agent must follow (no `any`, Zod at IO boundaries, etc.)
- **Recipes** — common debug patterns specific to this stack

The file should be **dense and command-first** — no prose introductions. Every section
should be actionable. Keep under 150 lines; nested AGENTS.md files in subdirs override
the root file for that subtree.

## Usage

```bash
# Generate AGENTS.md for the current repo
python /path/to/global-skills/.agents/skills/create-agents-md/generate_agents_md.py .

# Generate for a specific target repo
python /path/to/global-skills/.agents/skills/create-agents-md/generate_agents_md.py /Users/vikas/Code/my-repo

# Preview without writing
python /path/to/global-skills/.agents/skills/create-agents-md/generate_agents_md.py . --dry-run

# Write CLAUDE.md instead (symlinked by Claude Code)
python /path/to/global-skills/.agents/skills/create-agents-md/generate_agents_md.py . --filename CLAUDE.md
```

## What the script detects

| Signal | Result |
|---|---|
| `package.json` deps: `@nestjs/core` | Adds NestJS skill route + OTel bootstrap reminder |
| `package.json` deps: `next` | Adds Next.js skill route + hydration recipe |
| `package.json` deps: `@remix-run/react` | Adds Remix skill route + HydrateFallback reminder |
| `pyproject.toml` or `requirements.txt` | Adds Python skill route + pytest commands |
| `prisma/schema.prisma` | Adds Prisma N+1 recipe + query-db skill route |
| `Dockerfile` or `docker-compose.yml` | Adds remote attach pattern |
| `package.json` scripts | Populates Commands section with actual script names |
| `.agents/skills/` in repo | Lists all available skills in the skills registry |

## After generating

1. Review and customise the Conventions section for your project.
2. Add project-specific recipes to the Recipes section.
3. Symlink to CLAUDE.md if using Claude Code: `ln -s AGENTS.md CLAUDE.md`
4. Commit the file — every agent reads it at session start.

## Nested AGENTS.md (service-specific overrides)

Per OpenAI Codex docs: "more deeply nested files take precedence in case of conflicting
instructions." Use this for monorepos:

```
apps/api/AGENTS.md       # NestJS-specific overrides
apps/web/AGENTS.md       # Next.js-specific overrides
packages/shared/AGENTS.md  # Shared library conventions
```

The root AGENTS.md sets global conventions; nested files add or override for their subtree.
