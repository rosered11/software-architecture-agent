# Incident Analysis: EF Core Connection Pool Exhaustion

**Symptom:** `Timeout expired. The timeout period elapsed prior to obtaining a connection from the pool.`
**Context:** .NET API, EF Core, pool size 100, no traffic spike, started at 3pm yesterday.

---

## What This Error Means

ADO.NET's connection pool is full (100 connections are checked out) and no connection was returned within the `ConnectionTimeout` window (default 15 seconds). The pool is not being exhausted by traffic volume — it is being held by connections that are not being returned promptly or at all.

---

## Likely Root Causes (Ranked by Frequency)

### 1. Leaked DbContext / Unclosed Connections (Most Common)

EF Core's `DbContext` holds an open connection for the duration of its lifetime. If a `DbContext` is instantiated manually and not disposed, injected as a singleton instead of scoped, or captured in a background thread that outlives the request scope, the connection is never returned to the pool.

### 2. Long-Running Transactions

An open `BeginTransaction()` that is never committed or rolled back holds the connection for its entire lifetime.

### 3. Async Deadlock / Thread Pool Starvation

Mixing `async/await` with `.Result` or `.GetAwaiter().GetResult()` can cause thread pool starvation.

### 4. Missing CancellationToken Propagation

Long-running EF Core queries without `CancellationToken` will not be cancelled when the HTTP request is aborted.

### 5. Slow Query / Query Plan Regression

A query that previously ran in milliseconds now runs for seconds — data growth, missing index, plan regression.

---

## Diagnostic Steps

### Step 1: Check Active Connections in PostgreSQL

```sql
SELECT pid, usename, state, wait_event_type, now() - query_start AS duration, LEFT(query, 120) AS query_preview
FROM pg_stat_activity
WHERE datname = '<your_db_name>'
ORDER BY query_start ASC;

-- Count by state
SELECT state, COUNT(*) FROM pg_stat_activity WHERE datname = '<your_db_name>' GROUP BY state;
```

Key signals: `state = 'idle in transaction'` = leak. `state = 'active'` with duration > 5s = slow query.

### Step 2: Check DbContext Lifetime in DI

```csharp
// CORRECT
services.AddDbContext<AppDbContext>(options => ...);
// WRONG — singleton
services.AddSingleton<AppDbContext>(new AppDbContext(...));
```

### Step 3: Search for Sync-over-Async

```bash
grep -rn "\.Result\b\|\.GetAwaiter()\.GetResult()\|\.Wait()" --include="*.cs" .
```

### Step 4: Check Application Logs Around 3pm

Look for: deployment just before 3pm, which endpoint threw first pool error, scheduled jobs at 3pm.

---

## Immediate Mitigation

1. Restart API pods to release held connections.
2. Kill idle-in-transaction connections on DB:
```sql
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = '<your_db_name>' AND state = 'idle in transaction'
  AND now() - query_start > interval '30 seconds';
```

---

## Fix by Root Cause

| Root Cause | Fix |
|---|---|
| DbContext not disposed | Use DI scoped lifetime |
| Singleton DbContext | Change to `AddDbContext<T>()` |
| DbContext in singleton service | Use `IDbContextFactory<T>` |
| Open transactions | `try/catch/finally` with rollback |
| Sync-over-async | Make entire call chain async |
| Slow query | Add missing index; check `pg_stat_statements` |

---

## Summary

Pool exhaustion at constant traffic almost always means a new slow query, a code deployment introducing a DbContext leak, or a background job triggered at 3pm holding connections. Check `pg_stat_activity` for `idle in transaction` connections first — that's the fastest diagnostic signal.
