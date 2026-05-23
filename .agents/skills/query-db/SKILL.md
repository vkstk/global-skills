---
name: query-db
description: >
  Read-only database querying skill. Use when debugging data issues, verifying state
  after a failed operation, checking foreign key relationships, or confirming what is
  actually in the database versus what the application thinks is there.
  Connects as a read-only role — cannot mutate data. Rejects non-SELECT queries.
  Works with PostgreSQL (psql) and can be adapted for MySQL/SQLite.
---

# Read-only Database Querying

Run `python psql_ro.py "<SQL>"`. Output is JSON (one object per row).

## Setup

```bash
# Set these in your shell or .env — use a dedicated read-only service account
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_NAME="myapp"
export DB_READONLY_USER="ro_agent"
export DB_READONLY_PASS="readonly-password"
```

**Create the read-only role (run once as superuser):**

```sql
-- Create role
CREATE ROLE ro_agent WITH LOGIN PASSWORD 'readonly-password';

-- Grant read access to all current and future tables
GRANT CONNECT ON DATABASE myapp TO ro_agent;
GRANT USAGE ON SCHEMA public TO ro_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ro_agent;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ro_agent;

-- Explicitly revoke write access (defense in depth)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM ro_agent;
```

## Usage examples

```bash
# Check order state
python psql_ro.py "SELECT id, status, total, created_at FROM orders WHERE id = 'abc123'"

# Recent failed payments
python psql_ro.py "SELECT id, user_id, amount, error_code, created_at FROM payments WHERE status = 'failed' ORDER BY created_at DESC LIMIT 20"

# User's session tokens (verify auth state)
python psql_ro.py "SELECT token_hash, expires_at, revoked FROM sessions WHERE user_id = 'xyz'"

# Check for orphaned records (no matching parent)
python psql_ro.py "SELECT o.id FROM order_items oi LEFT JOIN orders o ON o.id = oi.order_id WHERE o.id IS NULL LIMIT 10"

# Count by status (health check)
python psql_ro.py "SELECT status, count(*) FROM orders WHERE created_at > NOW() - INTERVAL '1 hour' GROUP BY 1 ORDER BY 2 DESC"

# Schema inspection — see available columns
python psql_ro.py "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'orders' ORDER BY ordinal_position"

# Slow query identification (requires pg_stat_statements extension)
python psql_ro.py "SELECT query, mean_exec_time, calls FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10"
```

## Rules

- Only SELECT queries are permitted. The script rejects anything else.
- Requires Python 3.8+ and `psql` (PostgreSQL client tools) on PATH.
- Never query for raw passwords, PII (email, phone, address) unless explicitly investigating a data issue — prefer querying IDs and counts.
- For large result sets, always add `LIMIT` to avoid flooding the agent context.
- Use `WHERE` clauses with indexed columns (id, created_at, status) for performance.

## Prisma-specific queries

When using Prisma, table names follow the `@map` convention — check your schema if unsure.

```bash
# Check Prisma migration history
python psql_ro.py "SELECT migration_name, finished_at, applied_steps_count FROM _prisma_migrations ORDER BY finished_at DESC LIMIT 10"

# Identify failed migrations
python psql_ro.py "SELECT migration_name, started_at, finished_at FROM _prisma_migrations WHERE finished_at IS NULL"
```
