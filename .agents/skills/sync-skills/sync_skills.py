#!/usr/bin/env python3
"""
sync_skills.py — Symlink global skills into target repos.

Reads SYNC_TARGETS from .env at the global-skills root (the directory three
levels above this script: .agents/skills/sync-skills/sync_skills.py).

For each target repo:
  1. Creates .agents/skills/ if absent.
  2. Symlinks each skill directory from global-skills into the target.
     - Skips if the target slot already points to the same source (idempotent).
     - Skips if the target slot is a real directory (local skill — never overwrite).
     - Replaces stale symlinks (pointing to a non-existent path).
  3. Injects (or refreshes) a skills registry block in the target's
     .github/copilot-instructions.md, clearly delimited by marker comments so
     all other content in that file is left untouched.

Usage:
    python sync_skills.py [--dry-run]

Requires Python 3.8+. No third-party dependencies.
"""

import argparse
import os
import re
import sys
from pathlib import Path


# ── constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
GLOBAL_SKILLS_ROOT = SCRIPT_DIR.parent.parent.parent   # repo root
GLOBAL_SKILLS_DIR = GLOBAL_SKILLS_ROOT / ".agents" / "skills"

ENV_FILE = GLOBAL_SKILLS_ROOT / ".env"
ENV_EXAMPLE_FILE = GLOBAL_SKILLS_ROOT / ".env.example"

SYNC_MARKER_START = "<!-- global-skills:sync-start -->"
SYNC_MARKER_END = "<!-- global-skills:sync-end -->"

# Skills to exclude from syncing (e.g. this skill itself to avoid confusion)
EXCLUDE_SKILLS: set[str] = set()


# ── helpers ───────────────────────────────────────────────────────────────────

def load_env(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Ignores blank lines and comments."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Strip optional surrounding quotes
        value = value.strip().strip("\"'")
        env[key.strip()] = value
    return env


def parse_skill_frontmatter(skill_md: Path) -> dict[str, str]:
    """Extract name and description from a SKILL.md YAML frontmatter block."""
    text = skill_md.read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    front = text[3:end]
    result: dict[str, str] = {}
    # name: single line
    name_match = re.search(r"^name:\s*(.+)$", front, re.MULTILINE)
    if name_match:
        result["name"] = name_match.group(1).strip()
    # description: may be multi-line (block scalar starting with >)
    desc_match = re.search(r"^description:\s*>?\s*\n((?:[ \t]+.+\n?)+)", front, re.MULTILINE)
    if desc_match:
        # Collapse indented block into a single line
        lines = [l.strip() for l in desc_match.group(1).splitlines() if l.strip()]
        result["description"] = " ".join(lines)
    else:
        # Inline description
        inline = re.search(r"^description:\s*(.+)$", front, re.MULTILINE)
        if inline:
            result["description"] = inline.group(1).strip()
    return result


def build_skills_registry_block(skills_dir: Path) -> str:
    """Generate the copilot-instructions.md block from all skills in skills_dir."""
    skill_dirs = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    lines: list[str] = [
        SYNC_MARKER_START,
        "## Skills (synced from global-skills — do not edit this block manually)",
        "",
    ]

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        meta = parse_skill_frontmatter(skill_md)
        name = meta.get("name", skill_dir.name)
        desc = meta.get("description", "")
        # Truncate description to first sentence for brevity
        first_sentence = desc.split(". ")[0].rstrip(".")
        lines.append(f"- `{name}` — {first_sentence}")

    lines.extend(["", SYNC_MARKER_END])
    return "\n".join(lines)


def update_copilot_instructions(target_repo: Path, registry_block: str, dry_run: bool) -> None:
    """Inject or refresh the skills registry block in copilot-instructions.md."""
    github_dir = target_repo / ".github"
    instructions_path = github_dir / "copilot-instructions.md"

    if dry_run:
        action = "would update" if instructions_path.exists() else "would create"
        print(f"    [dry] {action} {instructions_path.relative_to(target_repo)}")
        return

    github_dir.mkdir(exist_ok=True)

    if instructions_path.exists():
        existing = instructions_path.read_text()
        if SYNC_MARKER_START in existing and SYNC_MARKER_END in existing:
            # Replace between markers
            pattern = re.escape(SYNC_MARKER_START) + r".*?" + re.escape(SYNC_MARKER_END)
            updated = re.sub(pattern, registry_block, existing, flags=re.DOTALL)
        else:
            # Append block with a blank line separator
            updated = existing.rstrip("\n") + "\n\n" + registry_block + "\n"
        instructions_path.write_text(updated)
        print(f"    updated {instructions_path.relative_to(target_repo)}")
    else:
        instructions_path.write_text(registry_block + "\n")
        print(f"    created {instructions_path.relative_to(target_repo)}")


def sync_skills_to_repo(
    target_repo: Path,
    skills_dir: Path,
    registry_block: str,
    dry_run: bool,
) -> None:
    """Sync skills from skills_dir into target_repo."""
    target_skills_dir = target_repo / ".agents" / "skills"

    if dry_run:
        print(f"  [dry] would create {target_skills_dir.relative_to(target_repo)}/")
    else:
        target_skills_dir.mkdir(parents=True, exist_ok=True)

    skill_dirs = sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name not in EXCLUDE_SKILLS
    )

    for skill_src in skill_dirs:
        skill_link = target_skills_dir / skill_src.name

        if skill_link.exists() and not skill_link.is_symlink():
            # Real directory — local skill in this repo; leave it alone
            print(f"    skip  {skill_src.name}/ (local directory — not overwriting)")
            continue

        if skill_link.is_symlink():
            current_target = Path(os.readlink(skill_link))
            # Resolve relative symlinks
            if not current_target.is_absolute():
                current_target = (skill_link.parent / current_target).resolve()
            if current_target == skill_src:
                # Already points to the right place
                print(f"    ok    {skill_src.name}/ (symlink up-to-date)")
                continue
            if dry_run:
                print(f"    [dry] would replace stale symlink {skill_src.name}/ → {current_target}")
                continue
            # Stale symlink — replace it
            skill_link.unlink()
            print(f"    fixed {skill_src.name}/ (replaced stale symlink)")

        if dry_run:
            print(f"    [dry] would link {skill_src.name}/ → {skill_src}")
            continue

        skill_link.symlink_to(skill_src)
        print(f"    linked {skill_src.name}/ → {skill_src}")

    update_copilot_instructions(target_repo, registry_block, dry_run)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync global skills to target repos.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes.")
    args = parser.parse_args()
    dry_run: bool = args.dry_run

    if dry_run:
        print("DRY RUN — no changes will be made\n")

    # Load .env
    env = load_env(ENV_FILE)
    raw_targets = env.get("SYNC_TARGETS", "").strip()
    if not raw_targets:
        print(
            f"Error: SYNC_TARGETS not set in {ENV_FILE}\n"
            f"Copy {ENV_EXAMPLE_FILE} to {ENV_FILE} and configure your target repos.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Support both comma-separated and colon-separated values
    targets = [p.strip() for p in re.split(r"[,:]", raw_targets) if p.strip()]

    if not GLOBAL_SKILLS_DIR.is_dir():
        print(f"Error: skills directory not found: {GLOBAL_SKILLS_DIR}", file=sys.stderr)
        sys.exit(1)

    registry_block = build_skills_registry_block(GLOBAL_SKILLS_DIR)

    print(f"Source: {GLOBAL_SKILLS_DIR}")
    print(f"Targets: {len(targets)} repos\n")

    ok = skipped = 0
    for raw_path in targets:
        target = Path(raw_path).expanduser().resolve()
        print(f"→ {target}")

        if not target.exists():
            print(f"  WARNING: path does not exist — skipping")
            skipped += 1
            continue

        if not target.is_dir():
            print(f"  WARNING: not a directory — skipping")
            skipped += 1
            continue

        sync_skills_to_repo(target, GLOBAL_SKILLS_DIR, registry_block, dry_run)
        ok += 1
        print()

    print(f"Done. {ok} synced, {skipped} skipped.")
    if dry_run:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
