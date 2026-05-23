#!/usr/bin/env python3
"""
o2_search.py — Query OpenObserve logs or traces via the REST API.

Usage:
    python o2_search.py <logs|traces> "<SQL>" <minutes_back>

Required env vars:
    O2_URL   — e.g. https://openobserve.example.com
    O2_ORG   — e.g. default
    O2_USER  — e.g. admin@example.com
    O2_PASS  — your password (use a read-only service account)

Output: JSON array of result rows, printed to stdout.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: python o2_search.py <logs|traces> \"<SQL>\" <minutes_back>", file=sys.stderr)
        sys.exit(1)

    query_type = sys.argv[1].lower()
    sql = sys.argv[2]
    try:
        minutes_back = int(sys.argv[3])
    except ValueError:
        print(f"Error: minutes_back must be an integer, got '{sys.argv[3]}'", file=sys.stderr)
        sys.exit(1)

    # Validate query type
    if query_type not in ("logs", "traces"):
        print(f"Error: type must be 'logs' or 'traces', got '{query_type}'", file=sys.stderr)
        sys.exit(1)

    # Reject non-SELECT queries
    if not re.match(r"^\s*SELECT", sql, re.IGNORECASE):
        print("Error: Only SELECT queries are permitted.", file=sys.stderr)
        sys.exit(1)

    # Read required env vars
    missing = [v for v in ("O2_URL", "O2_ORG", "O2_USER", "O2_PASS") if not os.environ.get(v)]
    if missing:
        for var in missing:
            print(f"Error: {var} is not set.", file=sys.stderr)
        sys.exit(1)

    o2_url = os.environ["O2_URL"].rstrip("/")
    o2_org = os.environ["O2_ORG"]
    o2_user = os.environ["O2_USER"]
    o2_pass = os.environ["O2_PASS"]

    # Compute time range in microseconds
    now_us = int(time.time() * 1_000_000)
    start_us = now_us - (minutes_back * 60 * 1_000_000)

    payload = {
        "query": {
            "sql": sql,
            "start_time": start_us,
            "end_time": now_us,
            "size": 500,
            "search_type": "others",
        }
    }

    endpoint = f"{o2_url}/api/{o2_org}/_search?type={query_type}"
    credentials = b64encode(f"{o2_user}:{o2_pass}".encode()).decode()

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {credentials}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"Error: HTTP {exc.code} from OpenObserve — {exc.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Error: Could not reach OpenObserve — {exc.reason}", file=sys.stderr)
        sys.exit(1)

    hits = body.get("hits", body)
    print(json.dumps(hits, indent=2))


if __name__ == "__main__":
    main()
