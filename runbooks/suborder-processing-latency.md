# Runbook: SubOrder Processing — GetSubOrder API Timeout Under High Concurrency

## Header

| Field | Value |
|-------|-------|
| System | SubOrder Processing |
| Severity | High |
| Owner | Backend Platform Team |
| Last Updated | 2026-03-25 |
| Last Tested | Never — test on next occurrence |
| Related Incident | `references/incident-log.md` → #1 GetSubOrder API Latency Spike |
| Related KOS | Knowledge: N+1 Query Problem, Batch Query Pattern, Connection Pool Math |
| Related Pattern | `references/patterns.md` → #1 Batch Query, #11 Eager Graph Loading, #12 Coordinator-Level Resolution |
| Related ADR | `architecture-decision.md` → Option A (Batch Refactor) now, Option B (Async) follow-up |

---

## Overview

This runbook covers API timeouts in the GetSubOrder endpoint caused by excessive DB query generation (N+1 loops, duplicate reference resolution, lazy loading) that exhausts the connection pool under concurrent load. It applies to the SubOrder Processing service when response time exceeds 500ms, DB query count per request exceeds 30, or connection pool utilization exceeds 80%.

---

## Alert Condition

**Trigger this runbook when:**

- [ ] `suborder_api_p99_latency_seconds > 0.5` for 5 consecutive minutes
- [ ] `suborder_db_query_count_per_request > 30` (if instrumented)
- [ ] `suborder_db_connection_pool_utilization > 80%`
- [ ] On-call receives report: "order loading is timing out" or "GetSubOrder returning 500/timeout"
- [ ] DB connection errors in logs: "timeout waiting for connection from pool"

**Do NOT trigger for:**

- Cold start latency spike after deployment (first request, resolves within 60s)
- Single outlier request > 500ms with no sustained pattern
- Downstream Kafka consumer lag (different runbook)
- Slow response on a single specific malformed OrderId (investigate data, not system)

---

## Detection

**Step 1 — Confirm the alert is real (not a fluke)**

```bash
# Check current P99 latency (last 10 min)
# Prometheus:
histogram_quantile(0.99, rate(getsuborder_duration_seconds_bucket[10m]))
# Expected healthy: < 100ms
# Unhealthy: > 500ms sustained

# Check DB query count per request (if EF Core logging enabled)
# Search structured logs for trace ID with highest query count:
# Look for "Executed DbCommand" count grouped by TraceId
# Expected healthy: < 10 queries
# Unhealthy: > 30 queries
```

**Step 2 — Scope the blast radius**

- [ ] Is this affecting all requests or a specific OrderId / SubOrderId?
  - If specific: check how many sub-orders that order has (`SELECT COUNT(*) FROM SubOrder WHERE SourceOrderId = 'X'`)
  - Orders with 10+ sub-orders are most likely to trigger this
- [ ] Is this affecting one instance or all instances?
- [ ] When did it start? Check deployment log for recent releases
- [ ] Is there a correlated spike in traffic volume?
  - If traffic spike: connection pool math may be exceeded — check `concurrent_requests × 33 queries × 0.01s` vs pool size

**Step 3 — Identify which component**

- [ ] Check service logs for `OnError ---- GetSubOrder` entries
- [ ] Check for DB connection pool exhaustion:
  ```sql
  SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
  -- If close to max_connections → pool exhaustion confirmed
  ```
- [ ] Check for long-running queries holding connections:
  ```sql
  SELECT pid, now() - query_start AS duration, query, state
  FROM pg_stat_activity
  WHERE state != 'idle'
  ORDER BY duration DESC
  LIMIT 20;
  ```

---

## Diagnosis Tree

```
START: Alert triggered — timeout / latency spike confirmed
│
├─► Recent deployment in last 2 hours?
│   ├─► YES → Go to Fix A: Rollback Deploy
│   └─► NO  → Continue
│
├─► DB query count > 30 per request?
│   ├─► YES → Is it the GetSubOrder endpoint?
│   │   ├─► YES → Go to Fix B: N+1 Query Fix (known root cause)
│   │   └─► NO  → Investigate other endpoint — enable EF Core logging
│   └─► NO  → Continue
│
├─► DB connection pool exhausted? (errors: "timeout waiting for connection")
│   ├─► YES → Is traffic volume unusually high?
│   │   ├─► YES → Go to Fix C: Scale Out + Pool Relief
│   │   └─► NO  → Go to Fix B (likely N+1 causing long hold times)
│   └─► NO  → Continue
│
├─► Specific OrderId with many sub-orders?
│   ├─► YES → Check sub-order count. If > 20 → query count scales O(n)
│   │         Go to Fix B: N+1 Query Fix
│   └─► NO  → Continue
│
├─► EF Core tracking memory pressure? (high GC.Gen0/Gen1 in logs)
│   ├─► YES → Go to Fix D: AsNoTracking Quick Mitigation
│   └─► NO  → Continue
│
└─► None of the above match → Escalate + open new incident
```

---

## Fix Procedures

### Fix A: Rollback Deploy

**When**: Recent deployment coincides with alert start time.

```bash
# 1. Identify the previous stable version
kubectl rollout history deployment/suborder-api

# 2. Roll back
kubectl rollout undo deployment/suborder-api

# 3. Confirm rollback completed
kubectl rollout status deployment/suborder-api

# 4. Verify alert clears within 5 minutes
# Check Prometheus: histogram_quantile(0.99, rate(getsuborder_duration_seconds_bucket[5m]))
```

**Expected time to resolve**: 5-10 minutes
**Risk**: Rolling back may reintroduce a previous bug — check the rollback target's known issues first.

---

### Fix B: N+1 Query Fix (Primary — Known Root Cause)

**When**: DB query count per request is elevated (> 30) on GetSubOrder endpoint.

**Known root cause from target.cs analysis (2026-03-25):**

| Bug | Location | Impact |
|-----|----------|--------|
| GetSubOrderMessage N+1 loop | target.cs:518-540 | N queries (1 per sub-order) |
| GetRewardItem N+1 loop | target.cs:69-77 | N queries (1 per sub-order) |
| GetOrderPromotion lazy load | target.cs:209 | P queries (1 per promotion) |
| IsExistOrderReference 3x redundant | target.cs:55-57 | 6-9 redundant queries |
| GetOrderHeader Any+FirstOrDefault | target.cs:483-494 | 2 queries where 1 needed |
| IsExistOrderReference Any+Where | target.cs:497-510 | 2 queries where 1 needed |
| Missing AsNoTracking everywhere | all queries | Memory/GC overhead |

**Short-term mitigation (15-30 min) — apply Phase 1 only:**

```csharp
// 1. Add AsNoTracking() to the heaviest queries (immediate memory relief)
// In GetOrderHeader (line 488):
return _context.Order
    .AsNoTracking()  // ADD THIS
    .Include(o => o.Customer)
    .Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId))
    .FirstOrDefault();

// 2. Collapse Any() + FirstOrDefault() in GetOrderHeader (lines 483-494):
// Remove the if (_context.Order.Where(...).Any()) wrapper entirely
// FirstOrDefault() returns null if not found — no Any() check needed

// 3. Add .Include(op => op.Amount) in GetOrderPromotion (line 194):
OrderPromotionModel[] datalist = _context.OrderPromotion
    .Include(op => op.Amount)  // ADD THIS — eliminates lazy load loop
    .AsNoTracking()            // ADD THIS
    .Where(op => op.SourceOrderId == SourceOrderId)
    .ToArray();
// Then DELETE line 209: _context.Entry(datalist[i]).Reference(x => x.Amount).Load();
```

Redeploy. Verify query count drops from ~33 to ~15.

**Permanent fix (2-3 days) — apply all 3 phases:**

```
Phase 1: Collapse duplicates + AsNoTracking + Include(Amount) → ~33 to ~15 queries
Phase 2: Hoist IsExistOrderReference to GetSubOrder coordinator → ~15 to ~10 queries
Phase 3: Batch GetRewardItem and GetSubOrderMessage with Contains() → ~10 to ~7 queries
```

See `architecture-decision.md` for full implementation plan with before/after code.

**Verify fix:**

```csharp
// Enable EF Core query logging temporarily:
// In appsettings.json:
"Logging": {
  "LogLevel": {
    "Microsoft.EntityFrameworkCore.Database.Command": "Information"
  }
}
// Run a test request for an order with 10+ sub-orders
// Count "Executed DbCommand" lines per trace ID
// Expected after Phase 1: <= 15
// Expected after Phase 3: <= 7
```

**Measured results (2026-03-26)**:
- Phase 1: P50 5,048ms → 2,836ms (-44%)
- Phase 2: P50 2,836ms → 2,730ms (-46% vs baseline)
- Phase 3 (batch outer loop): P50 2,730ms → **1,505ms (-70% vs baseline)**
- Phase 4 (planned): async parallel per-sub-order calls → target < 300ms

**Expected time to resolve**:
- Phase 1 (short-term): 15-30 min coding + redeploy
- Full fix (all phases): 2-3 days

**Risk**: AsNoTracking disables change tracking — safe for this read-only path. Verify GetSubOrder never writes after reading.

---

### Fix C: Scale Out + Connection Pool Relief

**When**: DB connection pool is exhausted AND traffic volume is unusually high.

```bash
# 1. Check current connection usage
psql -c "SELECT count(*) as active FROM pg_stat_activity WHERE state = 'active';"

# 2. Kill long-running queries if safe (> 30 seconds)
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '30 seconds';"

# 3. Scale out service instances to distribute connection load
kubectl scale deployment/suborder-api --replicas=3

# 4. If pool size is under-configured, increase temporarily
# In connection string: Max Pool Size=200 (check current value first)

# 5. Verify connections are distributed
psql -c "SELECT client_addr, count(*) FROM pg_stat_activity GROUP BY client_addr;"
```

**Expected time to resolve**: 5-15 minutes
**Risk**: Killing queries may leave partial operations — verify data consistency after. Scaling out multiplies total connections across the cluster.

**Important**: This is a band-aid. If Fix B (N+1) is not applied, the problem will recur at the next traffic spike. Connection pool math: `concurrent_requests × queries_per_request × hold_time` must be less than pool capacity.

---

### Fix D: AsNoTracking Quick Mitigation

**When**: GC pressure is high (Gen0/Gen1 deltas elevated in logs) but query count is not the primary issue.

```csharp
// Add AsNoTracking() to every query in the GetSubOrder call chain:
// - GetOrderHeader (line 488)
// - GetOrderMessagePayments (line 136)
// - GetOrderPromotion (line 194)
// - GetRewardItem (line 366)
// - GetSubOrderMessage (line 518)

// This eliminates EF change tracking overhead on every entity loaded.
// Expected impact: ~40% reduction in memory allocation per call,
// significant GC.Gen0 pressure relief.
```

**Expected time to resolve**: 10-15 min coding + redeploy
**Risk**: Minimal — this is a read-only path. AsNoTracking is always correct for GET endpoints.

---

## Rollback

**If any fix procedure makes things worse:**

```bash
# 1. Revert the code change immediately
git revert HEAD
# Or rollback the deployment:
kubectl rollout undo deployment/suborder-api

# 2. If connection pool was modified, restore original value
# Revert connection string Max Pool Size to original

# 3. If instances were scaled, restore original replica count
kubectl scale deployment/suborder-api --replicas=<original-count>

# 4. Notify team of rollback
# Post in #incidents Slack channel:
# "Rolled back GetSubOrder fix — latency did not improve / got worse. Investigating."

# 5. Do NOT attempt a second fix without returning to Diagnosis Tree
# Return to Detection Step 1 with new information
```

**Rollback decision rule**: If latency/error rate does not improve within 10 minutes of applying a fix, rollback and escalate.

---

## Post-Incident Checklist

Complete this after the issue is fully resolved:

```
[ ] Alert cleared and stable for 30+ minutes
[ ] Root cause confirmed (not just symptoms resolved)
[ ] Fix deployed and verified in production
[ ] Before/after metrics captured:
    [ ] Query count per request: before ___ → after ___
    [ ] P99 latency: before ___ → after ___
    [ ] Connection pool utilization: before ___ → after ___
    [ ] GC.Gen0 delta: before ___ → after ___
[ ] KOS updated:
    [ ] Incident record updated in references/incident-log.md with actual Results
    [ ] Knowledge record created if new concept learned
    [ ] Pattern record updated if pattern was applied
    [ ] decision-rules.md updated if new threshold discovered
[ ] This runbook updated with any new diagnosis steps found during this incident
[ ] Prevention tasks created:
    [ ] Add EF Core query count metric to standard API dashboard (permanent)
    [ ] Add "DB call in loop" to PR checklist gate
    [ ] Add connection pool utilization alert
[ ] Team communication sent:
    [ ] Summary of what happened
    [ ] What was done to fix it
    [ ] ETA for permanent fix (if short-term mitigation was applied)
    [ ] What monitoring was added to catch this earlier
```
