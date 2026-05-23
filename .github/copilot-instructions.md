---
description: "Default rules for all Copilot agents in global-skills workspace"
applyTo: "**"
---

## Communication

Terse. No filler. No pleasantries. Fragments OK. Technical terms exact. Code unchanged.

## Code Changes

Read file before editing. Only change what was asked. No bonus refactors, no added comments, no docstrings on untouched code. No over-engineering. No helpers for one-off ops.

## Safety

Ask before: deleting files/branches, rm -rf, git push --force, git reset --hard, dropping tables, amending published commits, pushing code, commenting on PRs, modifying shared infra.
Local reversible edits: proceed freely.

## Security

Code must be free of OWASP Top 10 vulns. Catch and fix insecure code immediately. Never generate/guess URLs unless helping with programming.

## Copywriting (when writing content for Vikas Thakur brands)

See `.cursor/rules/copywriting.mdc` for full rules. Key: AIDA structure, benefits not features, Australian English, no em dashes, no banned words.

## Skills Available

- `caveman` — ultra-compressed comms, invoke with "caveman mode" or `/caveman`
- `copywriting` — Brian Dean style content for rockingweb / selfcareshop / invoicr / Vikas Thakur

### Debugging skills (framework-specific — load only when task needs it)

- `debug-nestjs` — OTel bootstrap, Pino correlation, manual spans, Prisma tracing, DI errors, remote attach
- `debug-nextjs` — App Router OTel, undici fetch tracing, hydration diff workflow, Edge runtime
- `debug-remix` — Hydration mismatches, ErrorBoundary/HydrateFallback, loader errors, @sentry/remix
- `debug-nodejs` — Inspector attach (Docker/K8s/SSH), clinic.js perf, heap profiling, event loop lag, bisect
- `debug-python` — pytest recipes, pdb/ipdb, rich tracebacks, mypy, ruff, structured output

### Runtime signal skills (on-demand — no MCP server required)

- `query-observability` — Query OpenObserve logs/traces via `o2_search.py`; OSS-compatible
- `inspect-browser` — Playwright headless capture: console errors, network failures, screenshot, page HTML
- `query-db` — Read-only PostgreSQL via `psql_ro.py`; rejects non-SELECT; safe for agent use

### Workspace sync skill

- `sync-skills` — Symlink all global skills into target repos; configured via `.env` at repo root
