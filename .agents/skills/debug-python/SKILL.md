---
name: debug-python
description: >
  Python debugging skill. Use when diagnosing test failures, slow tests, type errors,
  or runtime exceptions in Python automation, testing, or backend scripts.
  Covers pytest recipes, pdb/ipdb interactive debugging, rich tracebacks, mypy,
  ruff, and agent-readable structured output.
---

# Debugging Python

## 1 — pytest recipes (run these in order of specificity)

```bash
# Stop on first failure, drop into pdb
uv run pytest -x --pdb

# Rerun only the last failing test(s), drop into pdb
uv run pytest --lf -x --pdb

# Short traceback + show locals
uv run pytest -l --tb=short

# Focused selection by keyword expression
uv run pytest -k "checkout and not slow"

# Find the slow tests
uv run pytest --durations=10

# Verbose output — see each test name
uv run pytest -v
```

## 2 — Agent-readable output formats

```bash
# JUnit XML — compatible with most CI parsers
uv run pytest --junitxml=.agent/report.xml

# JSON report — requires pytest-json-report
uv run pip install pytest-json-report
uv run pytest --json-report --json-report-file=.agent/report.json

# Basic summary for agent consumption
uv run pytest --tb=short -q 2>&1 | tee .agent/test-output.txt
```

## 3 — Interactive debugging

**`breakpoint()` builtin** (Python 3.7+) — always prefer over `import pdb; pdb.set_trace()`.

```python
def process_order(order_id: str) -> dict:
    data = fetch_order(order_id)
    breakpoint()       # drops into pdb here; type 'c' to continue, 'q' to quit
    return transform(data)
```

**Upgrade pdb to ipdb (richer REPL):**

```bash
uv pip install ipdb
export PYTHONBREAKPOINT=ipdb.set_trace
```

**pdb cheat sheet:**

| Command | Action |
|---|---|
| `n` | next line (step over) |
| `s` | step into |
| `c` | continue |
| `q` | quit |
| `l` | list source around current line |
| `p <expr>` | print expression |
| `pp <expr>` | pretty-print |
| `w` | show call stack |
| `u` / `d` | move up / down the stack |

## 4 — Rich tracebacks (human-readable locals)

```python
# At the top of conftest.py or your entry point
from rich.traceback import install
install(show_locals=True, max_frames=10)
```

Automatically pretty-prints all unhandled exceptions with syntax-highlighted locals.

## 5 — Type checking

```bash
# Strict mypy check
uv run mypy --strict src/

# For incremental runs in watch mode
uv run mypy --strict src/ --follow-imports=silent
```

Common mypy patterns:
```python
from typing import Any, cast
from collections.abc import Sequence

# Never use bare Any — annotate properly
def process(items: Sequence[str]) -> list[str]:
    return [item.upper() for item in items]

# IO boundaries — use TypedDict or dataclasses
from typing import TypedDict
class OrderResponse(TypedDict):
    id: str
    total: float
    status: str
```

## 6 — Linting and formatting

```bash
# Format
uv run ruff format

# Lint with auto-fix
uv run ruff check --fix

# Check only (for CI / agent verification)
uv run ruff check --output-format=json > .agent/lint.json
```

## 7 — Structured logging for agent consumption

```python
import logging
import json
import sys

# JSON handler so logs are grep-able and OpenObserve-ingestible
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'file': record.filename,
            'line': record.lineno,
        })

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.DEBUG, handlers=[handler])
```

## 8 — Parallel test execution

```bash
uv pip install pytest-xdist

# Run tests in parallel across 4 workers
uv run pytest -n 4

# Auto-detect CPU count
uv run pytest -n auto
```

## 9 — Stop-hook commands (AGENTS.md)

```bash
pnpm test:python   # uv run pytest -x --tb=short -q
pnpm typecheck:py  # uv run mypy --strict src/
pnpm lint:py       # uv run ruff check --output-format=json
pnpm format:py     # uv run ruff format
```

Run in this order before declaring done.

## 10 — Common gotchas

| Symptom | Likely cause | Fix |
|---|---|
| Test passes locally, fails in CI | Different Python version | Pin version in `.python-version` or `pyproject.toml` |
| `ModuleNotFoundError` in tests | Wrong working directory | `uv run pytest` from project root; check `pythonpath` in `pytest.ini` |
| pdb not triggering | `PYTHONBREAKPOINT=0` set | `unset PYTHONBREAKPOINT` |
| mypy `Any` explosion | Missing stubs | `uv pip install types-<package>` or add `# type: ignore` with comment |
| Slow test suite | No parallelism; heavy fixtures | `pytest-xdist -n auto`; scope fixtures to `session` where safe |
