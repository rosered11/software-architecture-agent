## 🔍 Mode: Incident Analysis

**Incident:** `.NET API — "Timeout expired. The timeout period elapsed prior to obtaining a connection from the pool."`
**Stack:** EF Core, pool size 100, no traffic spike | **Date:** 2026-04-12

---

### 1. SYMPTOMS

- API throws connection pool timeout — not a query timeout, not an HTTP timeout
- Pool size is 100 — adequate for normal traffic
- No traffic spike — eliminates volume as root cause
- Started at 3pm — suggests a time-triggered cause (cron job, batch process, specific user action)
- **Conclusion:** something is *holding connections too long*, not requesting too many

---

### 2. ROOT CAUSE HYPOTHESES (ranked by probability)

| # | Root Cause | Mechanism |
|---|-----------|-----------|
| RC-1 | Long-held connections / slow queries | Query takes seconds; connection stays checked out while query runs |
| RC-2 | DbContext or connection not disposed | `DbContext` never `Dispose()`d — connection leaks permanently until GC |
| RC-3 | N+1 inside a loop × moderate concurrency | 30 concurrent × 15 queries × 200ms = 90s hold/sec → pool exhausted |
| RC-4 | Long transaction wrapping a batch | One connection held open for entire batch duration (minutes) |
| RC-5 | Lock contention | Row/table lock causes queries to wait — each waiter holds a connection while blocked |
| RC-6 | 3pm background job | Scheduled job runs at 3pm, consumes pool slice, starves API |

---

### 3. BACK-OF-ENVELOPE (mandatory)

```
📊 Back-of-Envelope

[3] DB / Connection Pool — pool_size = 100

Formula: concurrent_requests × queries_per_request × avg_hold_time_s < pool_size

Scenario A — N+1 at moderate traffic:
  concurrent = 30 | queries = 15 | hold = 0.2s
  Total hold = 30 × 15 × 0.2 = 90s/s → pool = 90%  →  EXHAUSTED

Ceiling (15q × 0.2s): 100 ÷ (15 × 0.2) = 33 concurrent requests max

Scenario B — One slow query per request:
  concurrent = 34 | queries = 1 | hold = 3.0s
  Total hold = 34 × 1 × 3.0 = 102 → pool exhausted at just 34 concurrent

Scenario C — Undisposed DbContext:
  1 connection leaked per request → pool drains after request #100
  Matches "works fine at startup, degrades gradually" pattern

[5] Latency Budget
  Target:  <200ms P99
  Symptom: >30s (connection acquisition timeout default)
  Gap:     ~30,000ms — entirely in waiting to acquire connection, not in query execution
```

**Key insight:** No traffic spike + pool size 100 + timeout = hold time problem, not capacity problem. The fix is never "increase pool size."

---

### 4. DIAGNOSIS STEPS (run in this order)

**Step 1 — Long-running queries (run NOW)**

```sql
SELECT pid, now() - query_start AS duration, query, state, wait_event_type
FROM pg_stat_activity
WHERE (now() - query_start) > interval '5 seconds' AND state != 'idle'
ORDER BY duration DESC;
```

Look for: queries > 5s → RC-1. `wait_event_type = 'Lock'` → RC-5.

**Step 2 — Idle-in-transaction (connection held, no work)**

```sql
SELECT pid, state, now() - query_start AS idle_duration, query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY idle_duration DESC;
```

Any row here = an open transaction never committed/rolled back → RC-2 or RC-4.

**Step 3 — Total connection count**

```sql
SELECT count(*) FROM pg_stat_activity WHERE datname = 'your_db_name';
```

**Step 4 — Lock contention**

```sql
SELECT blocked.pid, blocked.query, blocking.pid AS blocker, blocking.query AS blocker_query
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocking ON blocking.pid = ANY(pg_blocking_pids(blocked.pid))
WHERE cardinality(pg_blocking_pids(blocked.pid)) > 0;
```

---

### 5. FIXES BY ROOT CAUSE

**RC-1/RC-3 — Slow query or N+1:**

```csharp
// BEFORE: tracking + N+1
foreach (var id in ids)
    var item = await _context.Orders.FirstOrDefaultAsync(o => o.Id == id); // N queries

// AFTER: batch + AsNoTracking
var items = await _context.Orders
    .AsNoTracking()
    .Where(o => ids.Contains(o.Id))
    .ToListAsync(); // 1 query
```

**RC-2 — Undisposed DbContext:**

```csharp
// WRONG: Singleton → connection never released
services.AddSingleton<AppDbContext>();

// CORRECT: Scoped (default)
services.AddDbContext<AppDbContext>(options => ...);

// CORRECT: Factory for background jobs
services.AddDbContextFactory<AppDbContext>(options => ...);
await using var ctx = await _factory.CreateDbContextAsync();
```

**RC-4 — Long transaction:**

```csharp
// AFTER: per-batch transactions (connection held milliseconds per batch)
foreach (var batch in data.Chunk(1000))
{
    await using var tx = await _context.Database.BeginTransactionAsync();
    // process batch
    await _context.SaveChangesAsync();
    await tx.CommitAsync();
    _context.ChangeTracker.Clear();
}
```

**Universal guardrail:**

```sql
ALTER ROLE your_api_role SET statement_timeout = '10s';
```

---

### 6. PREVENTION

| Control | Action |
|---------|--------|
| Pool math gate | Code review: `queries × hold_time × concurrency < pool_size`. If >80%, fix before merge. |
| AsNoTracking | All read-only EF queries must have `.AsNoTracking()` |
| No DB in loop | Flag any `await _context.X` inside `foreach` at code review |
| Statement timeout | `statement_timeout = '10s'` at DB role level |
| Job isolation | Background jobs use a separate connection string with reserved pool slice |
| Prometheus alert | Alert on P99 connection wait time > 500ms |

---

### 7. LESSON

> **Pool exhaustion formula: `queries × hold_time_s × concurrent > pool_size`. No traffic spike needed.**
>
> At 15 queries × 200ms per request, your pool ceiling is 33 concurrent users — with a pool of 100. The fix is to reduce query count and hold time, not increase pool size. Increasing pool size moves the ceiling but doesn't fix the root cause.
>
> Always start diagnosis with `pg_stat_activity`. The database sees the truth; application logs only see the symptom.

---

### 8. DECISION RULE

```
If pool exhaustion + flat traffic:
  → pg_stat_activity first (idle-in-transaction or long-running)
  → idle-in-transaction → fix DbContext disposal or transaction scope
  → long-running query → EXPLAIN ANALYZE → index or query rewrite
  → N+1 (query count > 10/request) → batch with WHERE IN
  → 3pm timing → check cron job → isolate with separate pool slice
  → Never increase MaxPoolSize as first response
  → Add statement_timeout = '10s' at DB role level regardless of root cause found
```

---

### 9. KOS RECORDS GENERATED

**I7** — EF Core Connection Pool Exhaustion — Flat Traffic, Pool Size 100
**K34** — EF Core Connection Pool Exhaustion: Causes, Math, and Diagnostic Path
**P27** — Connection Pool Exhaustion Diagnosis and Fix Pattern
**D19** — Connection Pool Exhaustion Response — Diagnosis Order and Fix Strategy
**TA23** — Connection Pool Exhaustion Diagnostic Queries (PostgreSQL + .NET)

---

**Next Step:** Run the `pg_stat_activity` query from Step 1 right now. Paste the results here and I'll identify the exact root cause from your specific database state.
