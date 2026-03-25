# 📋 Incident Log

> Read this file when the user references a past incident by name, asks to analyze a similar problem,
> or when Incident Analysis mode needs a real example to ground the response.

---

## Index

| # | Incident | System | Severity | Pattern Applied |
|---|----------|--------|----------|-----------------|
| 1 | [GetSubOrder API Latency Spike](#1-getsuborder-api-latency-spike) | SubOrder Processing | High | Batch Query + AsNoTracking |

---

## 1. GetSubOrder API Latency Spike

### Overview

| Field | Value |
|-------|-------|
| **Title** | GetSubOrder API Latency Spike — Timeout Under High Concurrency |
| **Severity** | High |
| **System** | SubOrder Processing |
| **Status** | Analysed — Fix Pending |
| **Source File** | `target.cs` — `GetSubOrder()` (line 1) |
| **Date Identified** | 2026-03-25 |

---

### Symptoms

- API response time: **timeout** under high concurrent request load
- Estimated **~30 DB queries** per call for an order with 10 sub-orders (coordinator-level methods only)
- Under 100 concurrent requests × 30 queries each = **3,000 DB round-trips** competing for the connection pool
- Connection pool exhaustion → new requests queue → cascading timeouts
- Latency scaled as O(n) with sub-order count, not O(1)
- No infrastructure issue — problem is entirely in the data access layer

---

### Root Cause

**N+1 query patterns across 3 loops, redundant reference resolution called 3× per request, duplicate Any()+FirstOrDefault() queries, and lazy loading inside a loop — all without AsNoTracking() on a pure read path.**

Query count breakdown for 10 sub-orders, 3 promotions (`target.cs`):

| Source | Pattern | Location | Queries |
|--------|---------|----------|---------|
| `IsExistOrderReference` called independently by Header + Payments + Promotions | 3 calls × 2 queries each (`.Any()` + `.FirstOrDefault()`) | lines 55-57 → lines 497-510 | 6 |
| `GetOrderHeader` double query | `.Any()` then `.FirstOrDefault()` on same predicate | lines 483-494 | 2 |
| `GetOrderMessagePayments` | Single query with Include chain | lines 136-139 | 1 |
| `GetSubOrderMessage` loop (N sub-orders) | Calls `GetSubOrderMessage()` per sub-order in foreach | lines 518-540 (called from line 12) | N (10) |
| `GetOrderPromotion` N+1 on Amount | `Entry(datalist[i]).Reference(Amount).Load()` per promotion in for loop | line 209 | 1 + P (4) |
| `GetRewardItem` loop (N sub-orders) | Calls `GetRewardItem()` per SourceSubOrderId | lines 69-77 → lines 358-394 | N (10) |
| **Total (N=10, P=3)** | | | **~33** |

Per `decision-rules.md`: `10–30 queries = acceptable, monitor` but `30–100 = investigate`.
Under concurrency: 100 requests × 33 queries × ~10ms each = **33s of total DB time per burst → pool exhaustion**.

**7 specific bugs found in `target.cs` (ranked by impact):**

**BUG-1 — `GetSubOrderMessage` N+1: DB call inside a loop (lines 518-540)**
```csharp
// target.cs:523-531 — called from line 12 when SourceSubOrderId == "All"
foreach (SubOrderModel data1 in subOrderModel)
{
    SubOrderMessageViewModel suborder = GetSubOrderMessage(data1.SourceOrderId, data1.SourceSubOrderid);
    // 1 DB query per sub-order
}
```

**BUG-2 — `GetRewardItem` N+1: DB call inside a loop (lines 69-77)**
```csharp
// target.cs:69-77 — called when SourceSubOrderId == "All" and IsGetRewardPromotion == true
for (int i = 0; i < results.SourceSubOrderIdList.Count; i++)
{
    string sourceSubOrderId1 = results.SourceSubOrderIdList[i] + "";
    GetRewardItem(SourceOrderId, sourceSubOrderId1, ref rewardItemMessageTmp);
    // Each call queries _context.PromotionItemTb (line 366-369)
}
```

**BUG-3 — `IsExistOrderReference` called 3× independently for same SourceOrderId (lines 55-57)**
```csharp
// target.cs:55-57 — each of these internally calls IsExistOrderReference
var orderHeader = GetOrderHeader(SourceOrderId);          // → resolves reference internally (line 479)
var orderPayments = GetOrderMessagePayments(SourceOrderId); // → resolves reference again (line 131)
results.OrderPromotion = GetOrderPromotion(SourceOrderId);  // → resolves reference again (line 185)
```

**BUG-4 — `IsExistOrderReference` itself has duplicate queries (lines 497-510)**
```csharp
// target.cs:499 — first overload (2-param)
if (_context.Order.Where(w => w.SourceOrderId.Equals(SourceOrderId)).Any())          // query 1
    // returns false
if (_context.OrderReference.Where(w => w.NewSourceOrderId.Equals(SourceOrderId)).Any()) // query 2
{
    var OrderRef = _context.OrderReference.Where(w => w.NewSourceOrderId.Equals(SourceOrderId))
        .OrderByDescending(o => o.CreatedDate).FirstOrDefault();                      // query 3 (duplicate filter)
}
```

**BUG-5 — `GetOrderHeader` double-query (lines 483-494)**
```csharp
// target.cs:483-494
if (_context.Order.Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId)).Any()) // query 1
{
    return _context.Order
        .Include(Order => Order.Customer)
        .Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId))
        .FirstOrDefault();  // query 2 — identical predicate
}
```

**BUG-6 — `GetOrderPromotion` N+1 on Amount via lazy load in loop (line 209)**
```csharp
// target.cs:199-214
for (int i = 0; i < datalist.Length; i++)
{
    _context.Entry(datalist[i]).Reference(x => x.Amount).Load(); // 1 query per promotion row
    CLResult rchk = model2ViewModel(datalist[i], ref viewModel);
}
```

**BUG-7 — Missing `AsNoTracking()` on all read-only queries**
```csharp
// Every _context query in target.cs lacks AsNoTracking():
// - GetOrderHeader (line 488)
// - GetOrderMessagePayments (line 136)
// - GetOrderPromotion (line 194)
// - GetRewardItem (line 366)
// - GetSubOrderMessage (line 518)
// Risk: EF change tracker allocates memory per entity — 100% waste on read path
```

---

### Fix

**Phase 1 (Day 1) — Zero-risk fixes: collapse duplicate queries + AsNoTracking**

```csharp
// FIX BUG-5: GetOrderHeader — collapse Any() + FirstOrDefault() (lines 483-494)
// BEFORE: 2 queries
if (_context.Order.Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId)).Any())
{
    return _context.Order.Include(Order => Order.Customer)
        .Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId)).FirstOrDefault();
}

// AFTER: 1 query
return _context.Order
    .AsNoTracking()
    .Include(o => o.Customer)
    .Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId))
    .FirstOrDefault(); // returns null if not found
```

```csharp
// FIX BUG-4: IsExistOrderReference — collapse Any() + Where() (lines 497-510)
// BEFORE: 2-3 queries
if (_context.Order.Where(w => w.SourceOrderId.Equals(SourceOrderId)).Any()) { ... }
if (_context.OrderReference.Where(w => w.NewSourceOrderId.Equals(SourceOrderId)).Any())
{
    var OrderRef = _context.OrderReference.Where(w => w.NewSourceOrderId.Equals(SourceOrderId))...
}

// AFTER: 1 query
var orderRef = _context.OrderReference
    .AsNoTracking()
    .Where(w => w.NewSourceOrderId.Equals(SourceOrderId))
    .OrderByDescending(o => o.CreatedDate)
    .FirstOrDefault();
if (orderRef == null) { RefSourceOrderId = null; return false; }
RefSourceOrderId = orderRef.RefSourceOrderId;
return true;
```

```csharp
// FIX BUG-6: GetOrderPromotion — eager load Amount (line 194 + 209)
// BEFORE: load promotions then Entry.Load() per item
OrderPromotionModel[] datalist = (from op in _context.OrderPromotion
    where op.SourceOrderId == SourceOrderId select op).ToArray();
// then per item: _context.Entry(datalist[i]).Reference(x => x.Amount).Load();

// AFTER: eager load in initial query
OrderPromotionModel[] datalist = _context.OrderPromotion
    .Include(op => op.Amount)
    .AsNoTracking()
    .Where(op => op.SourceOrderId == SourceOrderId)
    .ToArray();
// Remove the Entry().Reference(Amount).Load() line entirely
```

```csharp
// FIX BUG-7: Add AsNoTracking() to ALL read queries
// Apply to every _context query in: GetOrderHeader, GetOrderMessagePayments,
// GetOrderPromotion, GetRewardItem, GetSubOrderMessage
```

**Expected result Phase 1: ~30 → ~15 queries**

---

**Phase 2 (Day 2) — Coordinator refactor: resolve reference once**

```csharp
// FIX BUG-3: Hoist IsExistOrderReference to GetSubOrder (lines 55-57)
// BEFORE: each sub-call resolves independently
var orderHeader = GetOrderHeader(SourceOrderId);
var orderPayments = GetOrderMessagePayments(SourceOrderId);
results.OrderPromotion = GetOrderPromotion(SourceOrderId);

// AFTER: resolve once, pass resolved ID down
string resolvedOrderId = SourceOrderId;
string refSourceOrderId = string.Empty;
if (IsExistOrderReference(SourceOrderId, ref refSourceOrderId))
    resolvedOrderId = refSourceOrderId;

var orderHeader = GetOrderHeader(resolvedOrderId, skipRefCheck: true);
var orderPayments = GetOrderMessagePayments(resolvedOrderId, skipRefCheck: true);
results.OrderPromotion = GetOrderPromotion(resolvedOrderId, skipRefCheck: true);
```

**Expected result Phase 2: ~15 → ~10 queries**

---

**Phase 3 (Day 3) — Batch the N+1 loops**

```csharp
// FIX BUG-2: Batch GetRewardItem — replace per-sub-order loop (lines 69-77)
// BEFORE: N queries in a loop
for (int i = 0; i < results.SourceSubOrderIdList.Count; i++)
{
    GetRewardItem(SourceOrderId, results.SourceSubOrderIdList[i], ref rewardItemMessageTmp);
}

// AFTER: 1 query
var allRewardItems = _context.PromotionItemTb
    .AsNoTracking()
    .Where(p => p.SourceOrderId == SourceOrderId
        && results.SourceSubOrderIdList.Contains(p.SourceSubOrderId)
        && !p.IsDelete)
    .ToList();

// Map to ViewModels in memory
foreach (var reward in allRewardItems)
{
    RewardItemPromotionViewModel viewModel = new();
    Databind(reward, ref viewModel, false);
    rewardItemMessage.Add(viewModel);
}
```

```csharp
// FIX BUG-1: Batch GetSubOrderMessage — replace per-sub-order loop (lines 518-540)
// BEFORE: foreach calling GetSubOrderMessage() one by one
foreach (SubOrderModel data1 in subOrderModel)
{
    SubOrderMessageViewModel suborder = GetSubOrderMessage(data1.SourceOrderId, data1.SourceSubOrderid);
}

// AFTER: single query for all sub-orders, map in memory
var allSubOrders = _context.SubOrder
    .AsNoTracking()
    .Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId))
    .Include(/* all needed navigations */)
    .AsSplitQuery()
    .ToList();
// Map each to SubOrderMessageViewModel in memory loop (zero DB calls)
```

**Expected result Phase 3: ~10 → ~7 queries**

---

**Phase 4 (Follow-up PR) — Async migration**

```csharp
// Convert to async + parallel independent calls using IDbContextFactory
var headerTask = Task.Run(async () => {
    using var ctx = _contextFactory.CreateDbContext();
    return await GetOrderHeaderAsync(ctx, resolvedOrderId);
});
var paymentsTask = Task.Run(async () => {
    using var ctx = _contextFactory.CreateDbContext();
    return await GetOrderMessagePaymentsAsync(ctx, resolvedOrderId);
});
var promotionTask = Task.Run(async () => {
    using var ctx = _contextFactory.CreateDbContext();
    return await GetOrderPromotionAsync(ctx, resolvedOrderId);
});
await Task.WhenAll(headerTask, paymentsTask, promotionTask);
// Note: requires IDbContextFactory — EF Core DbContext is NOT thread-safe
```

---

### Observability — Before/After Measurement Plan

**Instrument before changing any code. Record baseline. Compare after each phase.**

**Step 1 — EF Core query logging (zero code change)**
```csharp
// In Startup / Program.cs — counts every SQL round-trip
options.LogTo(
    (eventId, _) => eventId == RelationalEventId.CommandExecuted,
    eventData => _logger.LogInformation(
        "EF Query | {ElapsedMs}ms | {Sql}",
        ((CommandExecutedEventData)eventData).Duration.TotalMilliseconds,
        ((CommandExecutedEventData)eventData).Command.CommandText[..200]
    )
);
```

**Step 2 — Stopwatch + GC instrumentation in `GetSubOrder`**
```csharp
var sw        = Stopwatch.StartNew();
var memBefore = GC.GetTotalMemory(false);
var gen0Before = GC.CollectionCount(0);
var gen1Before = GC.CollectionCount(1);

try { /* existing logic */ }
finally
{
    sw.Stop();
    _logger.LogInformation(
        "GetSubOrder | OrderId: {OrderId} | ElapsedMs: {Ms} | " +
        "MemAllocatedKB: {Kb} | GC.Gen0: {Gen0} | GC.Gen1: {Gen1}",
        SourceOrderId,
        sw.ElapsedMilliseconds,
        (GC.GetTotalMemory(false) - memBefore) / 1024,
        GC.CollectionCount(0) - gen0Before,
        GC.CollectionCount(1) - gen1Before
    );
}
```

**Step 3 — Prometheus metrics (permanent, production-grade)**
```csharp
private static readonly Histogram GetSubOrderDuration = Metrics
    .CreateHistogram("getsuborder_duration_seconds",
        "Duration of GetSubOrder calls",
        new HistogramConfiguration
        {
            LabelNames = new[] { "result" },
            Buckets = new[] { .05, .1, .25, .5, 1.0, 2.5, 5.0 }
        });

// Query after fix:
// histogram_quantile(0.99, rate(getsuborder_duration_seconds_bucket[5m]))
```

**Baseline captured 2026-03-25** — 30 sequential calls, single-user, OrderId `TWDCDS2602122610025068`, SubOrderId `All`:

| Metric | Baseline (measured) | Target (after Phase 3) | Target (after Phase 4) | Actual (after) |
|--------|---------------------|------------------------|------------------------|----------------|
| ElapsedMs (P50) | **5,048ms** | < 300ms | < 100ms | — |
| ElapsedMs (P99) | **8,283ms** | < 500ms | < 200ms | — |
| ElapsedMs (best) | 3,193ms | — | — | — |
| CpuMs (steady state) | **15-62ms** | ~15ms (unchanged) | ~15ms | — |
| I/O wait % | **99%** | < 80% | < 70% | — |
| MemDelta per call (steady) | **2,676 KB** | < 1,500 KB | < 1,500 KB | — |
| AllocatedKB per call (steady) | **2,668 KB** | < 1,500 KB | < 1,500 KB | — |
| MemDelta (cold start, call #1) | 22,237 KB | one-time | one-time | — |
| GC0 per 10 calls | **1** | 0 | 0 | — |
| GC1 per 10 calls | **1** | 0 | 0 | — |
| GC2 (cold start only) | 1 | 0 | 0 | — |
| ThreadPool IO used | **0** (all sync) | 0 (still sync) | > 0 (async) | — |
| DB query count per request | ~33 (estimated) | ~7 | ~7 (parallel) | — |

**Key findings from baseline:**
- **99% of wall-clock time is waiting on DB I/O** — CpuMs=15-62ms vs ElapsedMs=5,000ms. DB round-trip reduction is the only lever that matters.
- **2.6 MB of EF tracked entities per call** — under 100 concurrent requests = 260MB simultaneous tracked entities → GC pressure.
- **ThreadPool IO = 0** — all DB calls are synchronous, blocking a thread for 5s per request.
- **GC pattern**: heap grows ~2.6MB per call until ~80MB, then GC reclaims ~44MB. Under concurrency, GC frequency will increase significantly.
- **Cold start penalty**: first call is 8.3s with 22MB allocation (EF model compilation + JIT). One-time cost.

---

### Results

| Metric | Baseline (measured) | After Phase 1 | After Phase 3 (est.) | After Phase 4 (est.) |
|--------|---------------------|---------------|----------------------|----------------------|
| ElapsedMs (P50) | **5,048ms** | — | < 300ms | < 100ms |
| ElapsedMs (P99) | **8,283ms** | — | < 500ms | < 200ms |
| CpuMs (steady) | 15-62ms | ~15ms | ~15ms | ~15ms |
| MemDelta per call | 2,676 KB | ~1,600 KB | ~1,500 KB | ~1,500 KB |
| GC0 per 10 calls | 1 | 0 | 0 | 0 |
| ThreadPool IO | 0 (sync) | 0 | 0 | > 0 (async) |
| DB queries per request | ~33 | ~15 | ~7 | ~7 |
| Max concurrent before pool exhaustion | ~20 | ~40 | ~100+ | ~300+ |

> Fill in Phase 1/3/4 actual numbers after each fix deployment.

---

### Prevention

```
[ ] Any DB call inside a foreach or for loop?                    → BLOCK immediately
[ ] Any Entry().Reference().Load() or Entry().Collection().Load()?  → Replace with Include() chain
[ ] Any Any() followed by FirstOrDefault() on same predicate?    → Collapse to one query
[ ] Same ID resolved by IsExistOrderReference multiple times?    → Resolve once at coordinator, pass down
[ ] All GET endpoint queries using AsNoTracking()?               → Required on every read path
[ ] Query count logged before merging?                           → Use EF Core LogTo or MiniProfiler
[ ] Stopwatch + GC baseline captured before and after fix?       → Required for hot-path changes
[ ] Connection pool math validated for expected concurrency?     → queries × hold_time × concurrent_requests < pool_size
```

---

### Lesson Learned

> **Connection pool math**: timeout under concurrency is not about a single slow query — it's about `query_count × hold_time × concurrent_requests > pool_size`. Reducing query count from 33 to 7 alone increases the concurrency ceiling by ~4×.

> **Lazy load accumulation**: each `Entry().Load()` looks harmless in isolation. The problem only appears when you trace the full call graph — not just the method. Architects review call graphs, not individual methods.

> **Shared context resolution**: when a sub-call resolves the same data the parent already knows (e.g. `IsExistOrderReference` called 3× for same ID), the design has a hidden coupling gap. Fix: resolve shared context at the coordinator level and inject the result.

> **Latency ≈ DB query count × average round-trip time.** EF Core does not batch automatically. Every `.Load()` inside a loop is a performance bug waiting for enough data to detonate.

**Architectural rules extracted:**
- Never trust EF Core to batch automatically — it doesn't
- Every `.Load()` inside a loop is a block, not a warning
- Resolve shared context (order reference lookups, header data) once at the coordinator and pass it down — never re-resolve independently in each sub-call
- Instrument before you fix — a fix without a baseline is anecdotal
- Always calculate connection pool math: `concurrent_requests × queries_per_request × avg_hold_time` must be < pool capacity
- `AsNoTracking()` is mandatory on every read path — EF tracking overhead is never free

---

### Architecture Decision

**Decision**: Option A (Batch Query Refactor) now, Option B (Async + Parallel) as fast-follow.

| Option | Query Reduction | Risk | Effort |
|--------|----------------|------|--------|
| A. Batch Query Refactor | ~33 → ~7 | Low — same signatures, no infra change | 2-3 days |
| B. Async + Parallel Calls | ~7 queries run in parallel | Medium — requires IDbContextFactory, async migration | 5-7 days |
| C. CQRS Read Model | ~33 → 1 | High — new infra, eventual consistency | 2-3 weeks |

**Rationale**: Option A fixes the root cause with minimal blast radius. After A is proven in production, Option B further reduces wall-clock time. Option C is premature until read/write ratio exceeds 100:1.

See `architecture-decision.md` for full ADR.

---

### KOS Links

| Type | Record |
|------|--------|
| **Knowledge** | N+1 Query Problem, Batch Query Pattern, EF Core Best Practices, Connection Pool Math, GC pressure from EF tracking |
| **Pattern** | Batch Query → `references/patterns.md` #1 |
| **Pattern** | Eager Graph Loading → `references/patterns.md` #11 |
| **Pattern** | Coordinator-Level Resolution (new) → `references/patterns.md` #12 |
| **Decision** | Eager load via Include() chain over lazy Entry().Load() on hot-path read methods |
| **Decision** | Resolve canonical OrderId once at coordinator level — not inside each sub-call |
| **Decision** | Option A (Batch Refactor) now, Option B (Async) as follow-up — see `architecture-decision.md` |
| **Tech Assets** | Stopwatch + GC instrumentation snippet, Prometheus histogram snippet, EF LogTo config snippet |