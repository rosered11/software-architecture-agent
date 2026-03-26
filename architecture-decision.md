# Architecture Decision: GetSubOrder Timeout Under High Concurrency

🏗️ **Mode: Architecture Decision**

---

## Context

GetSubOrder is a read-path method in a .NET/EF Core service that assembles a complete sub-order view (header, payments, promotions, reward items). It currently executes ~30 sequential DB queries per request (N=10 sub-orders). Under high concurrent load, this exhausts the connection pool and causes timeouts.

## Problem

How should we restructure GetSubOrder to survive high request concurrency without timeouts, while keeping the change safe and incremental?

---

## Options

### Option A — Batch Query Refactor (Same Architecture)

Refactor the existing method in-place: eliminate N+1 loops, hoist shared resolution, add `AsNoTracking()`, collapse duplicate queries.

| Dimension | Assessment |
|-----------|-----------|
| **Query reduction** | ~30 -> ~6-8 per request |
| **Risk** | Low — same method signature, same response shape, no infrastructure change |
| **Effort** | 2-3 days |
| **Concurrency gain** | ~4x fewer connections held, ~5x shorter hold time |
| **Trade-off** | Method stays synchronous and monolithic. Doesn't solve the deeper coupling between sub-calls. Good enough for now, but ceiling is ~200-300 concurrent requests before connection pool pressure returns |

### Option B — Async + Parallel Independent Calls

Convert to `async`, run the 3 independent data fetches (`GetOrderHeader`, `GetOrderMessagePayments`, `GetOrderPromotion`) in parallel using `Task.WhenAll` with scoped DbContexts via `IDbContextFactory<T>`.

| Dimension | Assessment |
|-----------|-----------|
| **Query reduction** | ~30 -> ~6-8 (same batch fixes) + parallel execution |
| **Risk** | Medium — requires `IDbContextFactory`, async propagation up the call chain, each parallel branch needs its own DbContext (EF Core is not thread-safe) |
| **Effort** | 5-7 days (includes async migration of callers) |
| **Concurrency gain** | ~4x fewer queries + ~3x faster wall-clock time (parallel fetches) |
| **Trade-off** | Async migration is invasive — touches callers, controllers, possibly middleware. Risk of deadlock if mixed sync/async. Higher reward but larger blast radius. |

### Option C — CQRS Read Model (Denormalized View)

Create a pre-built `SubOrderReadModel` table (or materialized view) that contains the fully assembled sub-order data. Update it on write via Outbox/event. Read path becomes a single query.

| Dimension | Assessment |
|-----------|-----------|
| **Query reduction** | ~30 -> **1** |
| **Risk** | High — new infrastructure (read model table, event handler to maintain it), eventual consistency, data drift risk if updater has bugs |
| **Effort** | 2-3 weeks |
| **Concurrency gain** | Maximum — single indexed read, trivially cacheable |
| **Trade-off** | Adds operational complexity (read model updater, monitoring for drift). Per decision-rules: *"CQRS read model when read shape != write shape"* — this qualifies since the read assembles 5+ tables into one view. But premature if Option A solves the immediate problem. |

---

## Decision: Option A now, Option B as fast-follow

### Why

1. Option A eliminates the root cause (N+1, duplicate queries, lazy loading) with **minimal blast radius**. No signature changes, no infrastructure changes, no async migration. The connection pool math works:
   - Current: 100 concurrent x 30 queries x ~10ms each = 30s of DB time per burst -> pool exhaustion
   - After A: 100 concurrent x 7 queries x ~10ms each = 7s -> well within pool capacity

2. Option B is the right next step **after A is proven in production**. The async migration becomes lower-risk once the query count is already healthy — you're parallelizing 3 fast calls instead of 3 slow ones.

3. Option C is not justified yet. Per decision-rules: *"Read volume >> write volume (100:1+) -> CQRS with separate read store"*. Validate the read/write ratio first. If Option A brings latency under 300ms, CQRS adds complexity without proportional gain.

---

## Expected Outcome

| Metric | Before | After (Option A) |
|--------|--------|-------------------|
| Queries per request (N=10) | ~30 | ~7 |
| Connection hold time | ~300ms+ | ~70ms |
| P99 latency (100 concurrent) | timeout | < 300ms (target) |
| Connection pool utilization | saturated | ~25% |

---

## Watch Out For

1. **Regression in response shape** — the assembled ViewModel must be identical before/after. Write a snapshot test that captures the full JSON output for a known order, then assert it matches after refactoring.
2. **`Contains()` query plan** — EF Core translates `list.Contains(x)` to `WHERE x IN (...)`. If `SourceSubOrderIdList` exceeds ~2,000 items, PostgreSQL query planner may choose a seq scan. Add an index on `(SourceOrderId, SourceSubOrderId)` and monitor.
3. **`IsExistOrderReference` caller audit** — after hoisting resolution to the coordinator, ensure no other caller of `GetOrderHeader`/`GetOrderMessagePayments` still depends on the internal resolution. If they do, keep both paths (with/without skip flag).
4. **Measure before and after** — per decision-rules: *"A fix without a baseline is anecdotal."* Capture query count and elapsed time before deploying the fix.

---

## Implementation Order

```
Phase 1 (Day 1) — Zero-risk fixes:
  ├─ Collapse Any() + FirstOrDefault() in GetOrderHeader
  ├─ Collapse Any() + Where() in both IsExistOrderReference overloads
  ├─ Add AsNoTracking() to all read queries
  └─ Add .Include(op => op.Amount) in GetOrderPromotion, remove .Load() loop
  Expected: ~30 -> ~15 queries

Phase 2 (Day 2) — Coordinator refactor:
  ├─ Hoist IsExistOrderReference to GetSubOrder
  └─ Pass resolved ID to GetOrderHeader, GetOrderMessagePayments, GetOrderPromotion
  Expected: ~15 -> ~10 queries

Phase 3 (Day 3) — Batch loops:
  ├─ Batch GetRewardItem with Contains()
  └─ Batch GetSubOrderMessage with single query + in-memory mapping
  Expected: ~10 -> ~7 queries

Phase 4 (Follow-up PR) — Async migration:
  ├─ Introduce IDbContextFactory
  ├─ Convert to async
  └─ Parallel WhenAll for independent fetches
```

---

## Next Step

Instrument the current `GetSubOrder` with a `Stopwatch` and query count log **before changing any code**. Run it under realistic load (10+ concurrent calls with an order that has 5+ sub-orders). That baseline is the benchmark everything gets measured against.
