#!/usr/bin/env python3
"""
generate_agents_md.py — Generate a dense, router-based AGENTS.md for any repo.

Detects frameworks from package.json / pyproject.toml, reads available skills
from .agents/skills/, and outputs a command-first AGENTS.md ready to commit.

Usage:
    python generate_agents_md.py <repo_path> [--dry-run] [--filename AGENTS.md]

Requires Python 3.8+. No third-party dependencies.
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── framework detection ───────────────────────────────────────────────────────

def detect_frameworks(repo: Path) -> set[str]:
    """Return a set of detected framework/tool identifiers."""
    detected: set[str] = set()

    # --- Node.js / package.json ---
    pkg_path = repo / "package.json"
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text())
        except json.JSONDecodeError:
            pkg = {}
        all_deps: dict = {}
        all_deps.update(pkg.get("dependencies", {}))
        all_deps.update(pkg.get("devDependencies", {}))

        if "@nestjs/core" in all_deps:
            detected.add("nestjs")
        if "next" in all_deps:
            detected.add("nextjs")
        if "@remix-run/react" in all_deps or "@remix-run/node" in all_deps:
            detected.add("remix")
        if "express" in all_deps and "nestjs" not in detected:
            detected.add("express")
        if "vitest" in all_deps or "@vitest/core" in all_deps:
            detected.add("vitest")
        if "jest" in all_deps:
            detected.add("jest")
        if "playwright" in all_deps or "@playwright/test" in all_deps:
            detected.add("playwright")
        if "prisma" in all_deps or "@prisma/client" in all_deps:
            detected.add("prisma")
        if "typescript" in all_deps or "ts-node" in all_deps:
            detected.add("typescript")

    # --- Python ---
    if (repo / "pyproject.toml").exists() or (repo / "requirements.txt").exists():
        detected.add("python")
    if (repo / "uv.lock").exists():
        detected.add("uv")

    # --- Docker ---
    if (repo / "Dockerfile").exists() or (repo / "docker-compose.yml").exists() or (repo / "docker-compose.yaml").exists():
        detected.add("docker")

    # --- Prisma schema ---
    if (repo / "prisma" / "schema.prisma").exists():
        detected.add("prisma")

    # --- Kubernetes ---
    if any(repo.glob("k8s/**/*.yaml")) or any(repo.glob("kubernetes/**/*.yaml")):
        detected.add("kubernetes")

    return detected


def read_pkg_scripts(repo: Path) -> dict[str, str]:
    """Return package.json scripts dict, or empty dict."""
    pkg_path = repo / "package.json"
    if not pkg_path.exists():
        return {}
    try:
        pkg = json.loads(pkg_path.read_text())
        return pkg.get("scripts", {})
    except json.JSONDecodeError:
        return {}


def read_available_skills(repo: Path) -> list[dict[str, str]]:
    """Read skill name + first description line from .agents/skills/ in the repo."""
    skills_dir = repo / ".agents" / "skills"
    if not skills_dir.exists():
        return []

    skills = []
    for skill_dir in sorted(skills_dir.iterdir()):
        # Resolve symlinks to read the actual SKILL.md
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        meta = _parse_frontmatter(skill_md)
        name = meta.get("name", skill_dir.name)
        desc = meta.get("description", "")
        first = desc.split(". ")[0].rstrip(".")
        skills.append({"name": name, "description": first})

    return skills


def _parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    front = text[3:end]
    result: dict[str, str] = {}
    name_m = re.search(r"^name:\s*(.+)$", front, re.MULTILINE)
    if name_m:
        result["name"] = name_m.group(1).strip()
    desc_m = re.search(r"^description:\s*>?\s*\n((?:[ \t]+.+\n?)+)", front, re.MULTILINE)
    if desc_m:
        lines = [l.strip() for l in desc_m.group(1).splitlines() if l.strip()]
        result["description"] = " ".join(lines)
    else:
        inline = re.search(r"^description:\s*(.+)$", front, re.MULTILINE)
        if inline:
            result["description"] = inline.group(1).strip()
    return result


# ── section builders ──────────────────────────────────────────────────────────

def build_commands_section(frameworks: set[str], scripts: dict[str, str]) -> str:
    lines = ["## Commands (run in this order before declaring done)"]
    lines.append("")

    # Map common script name patterns to canonical labels
    LABEL_MAP = [
        (["typecheck", "tsc", "type-check"], "Typecheck"),
        (["lint", "lint:fix"], "Lint"),
        (["test", "test:unit", "test:ci"], "Test"),
        (["build"], "Build"),
        (["test:e2e", "e2e"], "E2E"),
        (["prisma:validate", "db:validate"], "DB validate"),
    ]

    found_any = False
    for keys, label in LABEL_MAP:
        for k in keys:
            if k in scripts:
                lines.append(f"- {label}: `pnpm {k}`")
                found_any = True
                break

    if not found_any:
        # Fallback — generic placeholders
        if "typescript" in frameworks or "nestjs" in frameworks or "nextjs" in frameworks or "remix" in frameworks:
            lines.append("- Typecheck: `pnpm typecheck`     # tsc --noEmit")
            lines.append("- Lint:      `pnpm lint`")
            lines.append("- Test:      `pnpm test`          # vitest run --reporter=basic --no-watch")
        if "python" in frameworks:
            runner = "uv run" if "uv" in frameworks else "python -m"
            lines.append(f"- Test:      `{runner} pytest -x --tb=short -q`")
            lines.append(f"- Typecheck: `{runner} mypy --strict src/`")
            lines.append(f"- Lint:      `{runner} ruff check --fix`")

    if "prisma" in frameworks:
        lines.append("- DB:        `pnpm prisma:validate`  # prisma validate && prisma format")

    lines.append("")
    return "\n".join(lines)


def build_skill_router_section(frameworks: set[str], skills: list[dict]) -> str:
    skill_names = {s["name"] for s in skills}
    lines = [
        "## Skill Router — load the matching skill before guessing",
        "",
        "| Scenario | Skill |",
        "|---|---|",
    ]

    routes: list[tuple[str, str]] = []

    # Framework-specific routes (only include if skill is available)
    if "nestjs" in frameworks and "debug-nestjs" in skill_names:
        routes.append(("NestJS API error, DI failure, slow endpoint, missing OTel spans", "`debug-nestjs`"))
    if "nextjs" in frameworks and "debug-nextjs" in skill_names:
        routes.append(("Next.js hydration mismatch, App Router OTel, Edge runtime, fetch spans", "`debug-nextjs`"))
    if "remix" in frameworks and "debug-remix" in skill_names:
        routes.append(("Remix hydration, ErrorBoundary without styles, loader errors", "`debug-remix`"))
    if "python" in frameworks and "debug-python" in skill_names:
        routes.append(("Python test failure, type error, runtime exception", "`debug-python`"))

    # Node.js core — applies to any Node project
    if any(f in frameworks for f in ("nestjs", "nextjs", "remix", "express")) and "debug-nodejs" in skill_names:
        routes.append(("Memory leak, CPU hotspot, event loop lag, crash, remote attach", "`debug-nodejs`"))

    # Runtime signal routes
    if "query-observability" in skill_names:
        routes.append(("Need logs, traces, or metrics from OpenObserve", "`query-observability`"))
    if "inspect-browser" in skill_names:
        routes.append(("Client-side error, network failure, visual regression", "`inspect-browser`"))
    if "query-db" in skill_names and "prisma" in frameworks:
        routes.append(("Data state wrong, foreign key issue, verify DB contents", "`query-db`"))
    elif "query-db" in skill_names:
        routes.append(("Verify database state, check data integrity", "`query-db`"))

    # Workspace skills
    if "sync-skills" in skill_names:
        routes.append(("Sync global skills to other repos", "`sync-skills`"))
    if "create-agents-md" in skill_names:
        routes.append(("Generate or update AGENTS.md for a repo", "`create-agents-md`"))

    if not routes:
        routes.append(("No framework-specific routes detected — add manually", "—"))

    for scenario, skill in routes:
        lines.append(f"| {scenario} | {skill} |")

    lines.append("")
    return "\n".join(lines)


def build_debug_sources_section(skills: list[dict]) -> str:
    skill_names = {s["name"] for s in skills}
    lines = [
        "## Debug feedback sources (use the skill — don't guess)",
        "",
    ]

    if "query-observability" in skill_names:
        lines.append("- Logs/traces:  skill `query-observability` — smallest time window that contains evidence")
    if "inspect-browser" in skill_names:
        lines.append("- Browser:      skill `inspect-browser` — console errors + failed network requests")
    if "query-db" in skill_names:
        lines.append("- DB state:     skill `query-db` — read-only SELECTs only")
    if "debug-nodejs" in skill_names:
        lines.append("- Perf/leak:    skill `debug-nodejs` — clinic doctor first, then flame/heapprofiler")

    if len(lines) == 2:  # only header
        lines.append("- No runtime skills available — run sync-skills to add them")

    lines.append("")
    return "\n".join(lines)


def build_conventions_section(frameworks: set[str]) -> str:
    lines = [
        "## Conventions",
        "",
    ]

    if any(f in frameworks for f in ("nestjs", "nextjs", "remix", "typescript")):
        lines += [
            "- No `any` — use `unknown` + narrowing; Zod at every IO boundary",
            "- No `JSON.parse` without try/catch or `safeParse`",
            "- No floating promises — always `await` or `.catch()`",
            "- No sequential `await` for independent work — use `Promise.all`",
        ]
    if "nestjs" in frameworks:
        lines += [
            "- Every controller method sets `span.setAttribute('user.id', ...)` on the active span",
            "- Logs are structured Pino: `logger.info({ userId, traceId }, 'message')`",
            "- Correlation IDs (`trace_id`/`span_id`) injected by OTel — do not set manually",
            "- One Prisma query per function; flag N+1 explicitly with a comment",
        ]
    if "python" in frameworks:
        lines += [
            "- Type all function signatures; no bare `Any`",
            "- Use `breakpoint()` not `import pdb`",
            "- Format with ruff before committing",
        ]
    if not any(f in frameworks for f in ("nestjs", "nextjs", "remix", "typescript", "python")):
        lines.append("- Add project conventions here")

    lines.append("")
    return "\n".join(lines)


def build_recipes_section(frameworks: set[str]) -> str:
    lines = [
        "## Common recipes",
        "",
    ]

    if "query-observability" in {f for f in frameworks}:
        pass  # handled below per framework

    if "nestjs" in frameworks:
        lines += [
            '- Slow endpoint: `query-observability` → `SELECT operation_name, approx_percentile_cont(duration,0.99) p99 FROM default WHERE service_name=\'api\' GROUP BY 1 ORDER BY 2 DESC`',
            "- Missing spans: check instrumentation.ts loads before main.ts (`node -r ./instrumentation.js`)",
            "- N+1 Prisma: `query-observability` → filter `operation_name LIKE 'prisma:%'` grouped by `trace_id`",
        ]
    if "nextjs" in frameworks:
        lines += [
            "- Hydration mismatch: `pnpm build && pnpm start` → curl server HTML → diff against DevTools `copy(document.body.innerHTML)`",
            "- Missing fetch spans: add `@opentelemetry/instrumentation-undici` to `instrumentation.node.ts`",
        ]
    if "remix" in frameworks:
        lines += [
            "- ErrorBoundary without styles: add `HydrateFallback` export to the route",
            "- Locale mismatch: format dates in loader with explicit `Intl.DateTimeFormat` locale",
        ]
    if "python" in frameworks:
        runner = "uv run" if "uv" in frameworks else "python -m"
        lines += [
            f"- First failure debug: `{runner} pytest -x --pdb`",
            f"- Rerun last failure: `{runner} pytest --lf -x --pdb`",
            f"- Slow tests: `{runner} pytest --durations=10`",
        ]
    if "docker" in frameworks:
        lines += [
            "- Attach debugger to running container: `docker exec <container> kill -SIGUSR1 1`",
            "- Then forward: `kubectl port-forward pod/<pod> 9229:9229` (K8s) or map `127.0.0.1:9229:9229` (Docker)",
        ]

    if len(lines) == 2:  # only header
        lines.append("- Add project-specific recipes here")

    lines.append("")
    return "\n".join(lines)


def build_skills_registry_section(skills: list[dict]) -> str:
    if not skills:
        return ""
    lines = [
        "## Available skills",
        "",
    ]
    for s in skills:
        lines.append(f"- `{s['name']}` — {s['description']}")
    lines.append("")
    return "\n".join(lines)


# ── main generator ────────────────────────────────────────────────────────────

def generate(repo: Path) -> str:
    frameworks = detect_frameworks(repo)
    scripts = read_pkg_scripts(repo)
    skills = read_available_skills(repo)

    detected_str = ", ".join(sorted(frameworks)) if frameworks else "none detected"

    parts: list[str] = [
        f"# AGENTS.md",
        f"",
        f"<!-- Generated by create-agents-md skill. Detected: {detected_str} -->",
        f"<!-- Customise conventions and recipes; keep under 150 lines. -->",
        f"",
    ]

    parts.append(build_commands_section(frameworks, scripts))
    parts.append(build_skill_router_section(frameworks, skills))
    parts.append(build_debug_sources_section(skills))
    parts.append(build_conventions_section(frameworks))
    parts.append(build_recipes_section(frameworks))
    if skills:
        parts.append(build_skills_registry_section(skills))

    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AGENTS.md for a repo.")
    parser.add_argument("repo", type=Path, help="Path to the target repo.")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing.")
    parser.add_argument("--filename", default="AGENTS.md", help="Output filename (default: AGENTS.md)")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    if not repo.is_dir():
        print(f"Error: {repo} is not a directory.", file=sys.stderr)
        sys.exit(1)

    content = generate(repo)
    out_path = repo / args.filename

    if args.dry_run:
        print(f"--- DRY RUN: would write to {out_path} ---\n")
        print(content)
        return

    if out_path.exists():
        print(f"Warning: {out_path.name} already exists — overwriting.")

    out_path.write_text(content)
    print(f"Wrote {out_path}")
    print(f"\nNext steps:")
    print(f"  1. Review and customise the Conventions section")
    print(f"  2. Add project-specific recipes")
    if args.filename != "CLAUDE.md":
        print(f"  3. For Claude Code: ln -s {args.filename} CLAUDE.md")
    print(f"  4. git add {out_path.name} && git commit -m 'chore: add AGENTS.md'")


if __name__ == "__main__":
    main()
