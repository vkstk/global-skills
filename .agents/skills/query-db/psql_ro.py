#!/usr/bin/env python3
"""
psql_ro.py — Read-only PostgreSQL query runner.

Usage:
    python psql_ro.py "<SQL>"

Required env vars:
    DB_HOST           — e.g. localhost
    DB_PORT           — e.g. 5432
    DB_NAME           — e.g. myapp
    DB_READONLY_USER  — read-only service account
    DB_READONLY_PASS  — password for read-only account

Output: JSON array of result rows, printed to stdout.
"""

import json
import os
import re
import subprocess
import sys


# Keywords that indicate mutation attempts — blocked even inside CTEs
_MUTATION_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# Only SELECT and WITH ... SELECT are permitted
_SELECT_PATTERN = re.compile(
    r"^\s*(SELECT|WITH\s+\w+\s+AS)",
    re.IGNORECASE,
)


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python psql_ro.py "<SQL>"', file=sys.stderr)
        sys.exit(1)

    sql = sys.argv[1]

    # Guard: must start with SELECT or WITH ... AS
    if not _SELECT_PATTERN.match(sql):
        print("Error: Only SELECT (and WITH ... SELECT) queries are permitted.", file=sys.stderr)
        sys.exit(1)

    # Guard: reject mutation keywords anywhere in the query
    match = _MUTATION_PATTERN.search(sql)
    if match:
        print(f"Error: Mutation keyword '{match.group()}' detected. Query rejected.", file=sys.stderr)
        sys.exit(1)

    # Read required env vars
    missing = [v for v in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_READONLY_USER", "DB_READONLY_PASS")
               if not os.environ.get(v)]
    if missing:
        for var in missing:
            print(f"Error: {var} is not set.", file=sys.stderr)
        sys.exit(1)

    host = os.environ["DB_HOST"]
    port = os.environ["DB_PORT"]
    dbname = os.environ["DB_NAME"]
    user = os.environ["DB_READONLY_USER"]
    password = os.environ["DB_READONLY_PASS"]

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    cmd = [
        "psql",
        f"--host={host}",
        f"--port={port}",
        f"--dbname={dbname}",
        f"--username={user}",
        "--no-password",
        "--tuples-only",
        "--no-align",
        "-c", r"\pset format json",
        "-c", sql,
    ]

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        print("Error: psql not found. Install PostgreSQL client tools.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: Query timed out after 30 seconds.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"Error: psql exited {result.returncode} — {result.stderr.strip()}", file=sys.stderr)
        sys.exit(result.returncode)

    # psql JSON output may be preceded by the \pset confirmation line — strip it
    raw = result.stdout.strip()
    # Find the first '[' which is the start of the JSON array
    json_start = raw.find("[")
    if json_start == -1:
        # Empty result set
        print("[]")
        return

    try:
        rows = json.loads(raw[json_start:])
        print(json.dumps(rows, indent=2))
    except json.JSONDecodeError:
        # Fallback: print raw output so the agent can still read it
        print(raw)


if __name__ == "__main__":
    main()
