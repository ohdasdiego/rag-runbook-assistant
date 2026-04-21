# Runbook: Database Connection Pool Exhaustion

**Severity:** P1 (customer-facing impact is immediate)
**Owner:** Platform Infrastructure + owning service team
**Related alerts:** `db_connections_saturated`, `connection_pool_exhausted`

## Overview

When an application exhausts its database connection pool, new queries block or fail. Users see 500 errors or slow page loads. The root cause is almost always one of: slow queries holding connections, a sudden traffic surge, or a connection leak in the application code.

## Initial Triage

1. Identify the database and the service making too many connections
2. Open the database dashboard (`grafana.internal/d/postgres-overview` or equivalent)
3. Note the connection count trend — sudden spike vs gradual climb tells a different story

## Diagnostic Queries (PostgreSQL)

```sql
-- Current connections by state
SELECT state, count(*)
FROM pg_stat_activity
GROUP BY state
ORDER BY count(*) DESC;

-- Longest-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC
LIMIT 20;

-- Idle-in-transaction connections (these are the usual culprits)
SELECT pid, now() - state_change AS idle_duration, query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY idle_duration DESC;
```

## Common Root Causes

### Idle-in-transaction connections
An application opened a transaction and never committed/rolled back. Connections are held hostage.

**Fix:**
1. Identify the culprit application from connection metadata
2. Restart the offending service to release connections:
   ```bash
   kubectl rollout restart deployment/<service> -n <namespace>
   ```
3. File a bug against that service for the transaction leak

### Slow queries
A query is taking minutes instead of milliseconds, holding connections for the duration.

**Fix:**
1. Identify the slow query from `pg_stat_activity`
2. If it is safe, terminate it:
   ```sql
   SELECT pg_terminate_backend(<pid>);
   ```
3. Investigate missing indexes or a bad query plan as follow-up

### Traffic surge
Legitimate traffic increase has exceeded the pool size.

**Fix:**
1. Scale the application horizontally — each pod has its own pool:
   ```bash
   kubectl scale deployment/<n> -n <namespace> --replicas=+3
   ```
2. If the database itself is saturated, consider temporarily increasing `max_connections` with DBA approval

### Application-side connection leak
Connections are acquired but never returned to the pool due to a code bug.

**Fix:**
1. Rolling restart of the affected service buys time
2. File an urgent bug — this will recur

## Emergency Kill of All Connections

Only if there is no safer option and with team lead approval:

```sql
-- Kill all connections from a specific app user (use with caution)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = '<app_user>'
  AND state = 'idle in transaction';
```

## Post-Incident

- If a connection leak was identified in application code, it must be tracked and fixed before incident is closed
- Review whether pool size should be increased based on the actual traffic pattern observed
- Check whether connection timeout settings are appropriate
