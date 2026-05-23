---
name: query-observability
description: >
  Query OpenObserve logs and traces when debugging a production or staging error,
  slow request, or failed deploy. Use when a trace_id, error message, or service
  name is known and you need runtime evidence. Works against OSS OpenObserve —
  no Enterprise license required. Run o2_search.sh directly; output is JSON.
---

# Querying OpenObserve (logs + traces)

Run `python o2_search.py <logs|traces> "<SQL>" <minutes_back>`. Output is JSON.

## Setup

```bash
# Set these in your shell or .env (never commit secrets)
export O2_URL="https://your-openobserve-instance.example.com"
export O2_ORG="default"
export O2_USER="admin@example.com"
export O2_PASS="your-password"
```

## SQL recipes

```bash
# Recent errors (last 15 min)
python o2_search.py logs \
  "SELECT _timestamp, service_name, message, trace_id FROM default WHERE level='error' ORDER BY _timestamp DESC" \
  15

# Follow a specific trace
python o2_search.py traces \
  "SELECT operation_name, duration, status_code FROM default WHERE trace_id='<id>' ORDER BY start_time" \
  60

# Slowest endpoints (p99 latency)
python o2_search.py traces \
  "SELECT operation_name, approx_percentile_cont(duration, 0.99) p99 FROM default GROUP BY 1 ORDER BY 2 DESC" \
  60

# Error burst after deploy (histogram)
python o2_search.py logs \
  "SELECT histogram(_timestamp) t, count(*) c FROM default WHERE level='error' GROUP BY t ORDER BY t" \
  30

# Slow Prisma queries
python o2_search.py traces \
  "SELECT operation_name, approx_percentile_cont(duration, 0.99) p99 FROM default WHERE operation_name LIKE 'prisma:%' GROUP BY 1 ORDER BY 2 DESC" \
  15

# Error volume by service
python o2_search.py logs \
  "SELECT service_name, count(*) c FROM default WHERE level='error' GROUP BY 1 ORDER BY 2 DESC" \
  60

# Unique error fingerprinting (top recurring messages)
python o2_search.py logs \
  "SELECT message, count(*) c FROM default WHERE level='error' GROUP BY 1 ORDER BY 2 DESC LIMIT 20" \
  60

# N+1 detection — same Prisma operation appearing many times per trace
python o2_search.py traces \
  "SELECT trace_id, operation_name, count(*) c FROM default WHERE operation_name LIKE 'prisma:%' GROUP BY 1,2 HAVING count(*) > 10 ORDER BY 3 DESC" \
  30

# Cold-start identification
python o2_search.py traces \
  "SELECT operation_name, duration FROM default WHERE operation_name='init' ORDER BY duration DESC LIMIT 20" \
  60

# Dependency hotspots
python o2_search.py traces \
  "SELECT service_name, avg(duration) avg_ms FROM default GROUP BY 1 ORDER BY 2 DESC" \
  60
```

## Rules

- Always pass the smallest time window that could contain the evidence.
- Timestamps are auto-converted to microseconds by the script. Do not compute them manually.
- Only use SELECT. The script rejects non-SELECT queries.
- Requires Python 3.8+. No third-party dependencies — uses stdlib `urllib` only.
- For full-text search, use `match_all('keyword')` — faster than `LIKE` on `message`.
- For case-insensitive equality, use `str_match_ignore_case(field, 'value')` — cheaper than regex.
- For regex, use `re_match(field, 'pattern')` e.g. `re_match(k8s_container_name, 'api|worker')`.
- To inspect available fields first: run with SQL `DESCRIBE default` (logs) or `DESCRIBE default` (traces).

## OpenObserve SQL functions reference

| Function | Use |
|---|---|
| `histogram(_timestamp)` | Time-series bucketing for error/request volume charts |
| `match_all('keyword')` | Full-text search (uses index — much faster than LIKE) |
| `approx_percentile_cont(col, 0.99)` | p99 latency — use for performance queries |
| `re_match(field, 'regex')` | Regex filter |
| `str_match_ignore_case(field, 'val')` | Case-insensitive equality |
