# 📋 Incident Log

> Read this file when the user references a past incident by name, asks to analyze a similar problem,
> or when Incident Analysis mode needs a real example to ground the response.

---

## Index

| # | Incident | System | Severity | Pattern Applied |
|---|----------|--------|----------|-----------------|
| 1 | [GetSubOrder API Latency Spike](#1-getsuborder-api-latency-spike) | SubOrder Processing | High | Batch Query + AsNoTracking |
| 2 | [PostgreSQL Dead Tuple Bloat — stockadjustments](#2-postgresql-dead-tuple-bloat--stockadjustments) | spc_inventory | High | Per-Table Autovacuum Tuning + REINDEX CONCURRENTLY |

---

## 1. GetSubOrder API Latency Spike

### Overview

| Field | Value |
|-------|-------|
| **Title** | GetSubOrder API Latency Spike — Timeout Under High Concurrency |
| **Severity** | High |
| **System** | SubOrder Processing |
| **Status** | Fixed — Applied 2026-03-27 |
| **Source File** | `incident2.cs` — `GetSubOrder()` (line 1) |
| **Date Identified** | 2026-03-25 |
| **Date Fixed** | 2026-03-27 |

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

| Metric | Baseline (measured) | After Phase 1 (measured) | After Phase 2 (measured) | After Phase 3 (measured) | After Indexes (measured) | After P0+P1 (measured) | After Phase 4 (est.) |
|--------|---------------------|--------------------------|--------------------------|--------------------------|--------------------------|------------------------|----------------------|
| ElapsedMs (P50) | **5,048ms** | **2,836ms (-44%)** | **~2,730ms (-46%)** | **~1,505ms (-70%)** | **~1,579ms (+5% noise)** | **1,224ms (-76%)** | ~400ms |
| ElapsedMs (best) | 3,193ms | **2,792ms (-13%)** | **2,634ms (-17%)** | **1,481ms (-54%)** | **1,539ms** | **1,198ms** | — |
| ElapsedMs (cold start) | 8,283ms | 12,533ms | **6,309ms (-24%)** | **4,521ms (-45%)** | **9,014ms (plan recompile)** | **5,849ms (compiled query init)** | — |
| CpuMs (steady) | 15-62ms | **0-46ms** | **0-46ms** | **0-109ms** | **0-110ms** | **0-62ms** | ~15ms |
| AllocatedKB per call | 2,668 KB | **2,697 KB (~same)** | **~2,655 KB (~same)** | **~2,470 KB (~same)** | **~1,808 KB (-27%)** | **~1,536 KB (-42%)** | ~1,500 KB |
| GC0 per 10 calls | 1 | **0.2 (-80%)** | **0.03 (-97%)** | **~5 (GC cycling)** | **0.3 (-94%)** | **0.42 (1/24 calls)** | ~0.1 |
| GC1 per 10 calls | 1 | **0.1 (-90%)** | **0.03 (-97%)** | **~5** | **0 (-100%)** | **0 (-100%)** | 0 |
| GC2 per 10 calls | 0 (cold only) | — | — | — | — | **0 (-100%)** | 0 |
| ThreadPool IO | 0 (sync) | **0** | **0** | **0** | **0** | **0** | > 0 (async) |
| DB queries per request | ~33 | **~22** | **~18** | **~50 (20+3N)** | **~50 (unchanged)** | **~20+N (PackageTb 4→1)** | ~20 |
| Max concurrent before pool exhaustion | ~20 | **~35** | **~40** | **~140+** | **~200+ (lower I/O hold time)** | **~200+** | ~400+ |

**Phase 1 notes (2026-03-26):**
- Latency dropped 44% — duplicate query collapse + Include(Amount) working
- GC pressure dropped 80-90% — AsNoTracking reducing tracking object churn
- MemDelta flat because N+1 loops still dominate (20 queries still loading full entities)
- Cold start worse due to new Include() query plan compilation — one-time cost
- **Remaining bottleneck: N+1 loops** in GetSubOrderMessage (N queries) and GetRewardItem (N queries) — Phase 2-3 target

**Phase 2 notes (2026-03-26):**
- Marginal latency improvement (2,836ms → ~2,730ms, -4%) — expected since hoisted queries were individually fast (~25ms each)
- Cold start dramatically improved (12,533ms → 6,309ms, -50%) — fewer query plan compilations at startup
- GC nearly eliminated — only 1 GC0 + 1 GC1 across 30 calls (at call #21 when heap reached ~80MB)
- MemDelta still flat — N+1 loops remain the dominant memory consumer
- **Remaining bottleneck: N outer loop** — 10 sequential GetSubOrderMessage calls at ~270ms each ≈ ~2,700ms

**Phase 3 notes (2026-03-26):**
- **Include chain expansion FAILED (attempt 1)** — replaced 21 Entry().Load() with mega-Include + AsSplitQuery. Result: ~0% latency change, +19% worse cold start. Reverted.
- **Root cause of failure**: AsSplitQuery generates the same number of queries as Entry().Load() — split queries replaced lazy loads 1:1. No net reduction.
- **Lesson**: The bottleneck is the N outer loop (10 sequential per-sub-order calls), not the per-item lazy loads inside each call.
- **Phase 3 revised (batch outer loop) — MEASURED 2026-03-26:**
  - Replaced `GetSubOrderMessage` list method with bulk-load-then-map: one `AsSplitQuery` with 16 Include paths loads ALL sub-orders, all supporting queries batched, mapping in memory
  - P50: 2,730ms → **1,505ms (-45%)** | Cold start: 6,309ms → **4,521ms (-28%)**
  - GC cycling healthy at ~5 GC0/10 calls — 2.5 MB allocated per call, collected before accumulation
  - **Remaining bottleneck**: per-sub-order calls kept as-is: `GetStoreLocation`, `getPackageInfoByOrderAndSubOrder`, `GetPackageTb` — 3×N sequential calls (~900ms for N=10)

**P0+P1 notes (2026-03-31) — GC management fixes:**
- **P0 — EF.CompileQuery applied** (`_bulkSubOrderQuery` static field): bulk SubOrder query with 16 Include paths compiled once at first call. Cold start: 5,849ms / 106 MB allocated (one-time IL compilation). Steady-state: AllocatedKB drops to ~1,536 KB by call #5.
- **P1 — GetPackageTb 4→1 query**: collapsed `Any()` + `Max(CreatedDate)` + `Max(UpdatedDate)` + `ToList()` into single `ToList()` + in-memory Max. Removes 3N DB round-trips per request.
- **AsNoTracking added**: `GetStoreLocation`, `getPackageInfoByOrderAndSubOrder`, `GetPackageTb` all now use `AsNoTracking()`.
- **Heap load test (Order.API-11.dmp)**: DynamicMethod 17,557 → 7,356 (-58%); total heap 112 MB → 90 MB (-20%); SubOrderMessageViewModel 836 → 50 (-94% — confirms no ChangeTracker leak under concurrency). Remaining 7,356 DynamicMethod = service-wide stable query footprint (no longer growing).
- **Remaining bottleneck**: 3 × N sequential per-sub-order calls (GetStoreLocation + getPackageInfoByOrderAndSubOrder + GetPackageTb) = ~1,200ms for N=10. Phase 4 target.

**Phase 4 notes (2026-03-27) — Applied to incident2.cs:**
- **Implemented**: `GetSubOrderAsync` coordinator using `Task.WhenAll` with `IDbContextFactory`
- **New async private methods**: `GetOrderHeaderAsync`, `GetOrderMessagePaymentsInternalAsync`, `GetOrderPromotionInternalAsync`, `GetRewardItemsBatchedAsync` — each accepts its own `DbContext` from the factory
- **Map functions extracted**: `MapPayments`, `MapPromotions`, `MapRewardItems` — pure in-memory, shared by sync and async paths
- **Execution model**: Step 1 = `GetSubOrderMessage` (serial, produces suborder list) → Step 2 = resolve reference once → Step 3 = 4 DB calls fired in parallel via `Task.WhenAll` → Step 4 = assemble in memory (zero DB)
- **Expected latency**: `max(t_header, t_payments, t_promotions, t_rewards)` instead of `t1+t2+t3+t4`
- **Thread safety**: EF Core DbContext is not thread-safe — each parallel task gets its own `DbContext` instance from `IDbContextFactory`
- **Migration**: sync `GetSubOrder` preserved unchanged; callers migrate to `GetSubOrderAsync` one at a time
- **Wire-up required**: `services.AddDbContextFactory<YourDbContext>(...)` in Program.cs + inject `IDbContextFactory` in constructor
- **BotE impact**: latency ceiling drops from `~1,500ms (sequential)` to `~max(400ms, 300ms, 250ms, 200ms) = ~400ms` — estimated 73% reduction from Phase 3 baseline

---

### Heap Dump Analysis — Order.API-3.dmp (2026-03-31)

**Dump taken after Phase 3 (AsNoTracking applied). Total: 1,327,781 objects, ~112 MB.**

```
Top heap consumers:
  System.Byte[]                              94,262 objects   19.8 MB  (17.6%)  → HTTP/JSON buffers — normal
  System.String                             157,652 objects   17.7 MB  (15.7%)  → SQL text, log strings — normal
  System.Char[]                              20,709 objects    7.5 MB  (6.7%)   → String internals — normal
  System.Reflection.Emit.DynamicILGenerator  17,557 objects    2.67 MB          ← NON-RECLAIMABLE
  Microsoft.Data.SqlClient._SqlMetaData      13,663 objects    2.19 MB          ← SqlDataReader column descriptors
  System.Reflection.Emit.DynamicMethod       17,557 objects    2.25 MB          ← NON-RECLAIMABLE
  System.Int32[]                             22,641 objects    1.50 MB
  System.Reflection.Emit.DynamicResolver     17,539 objects    1.26 MB          ← NON-RECLAIMABLE
  Microsoft.Data.SqlClient.SqlBuffer          8,188 objects    524 KB           ← SqlDataReader raw data
```

**Finding 1 — EF compiled query cache: 17,557 entries (~6 MB non-reclaimable)**

Each unique LINQ expression tree compiled at runtime = 1 DynamicMethod + 1 DynamicILGenerator + 1 DynamicResolver. With 16 Include paths via `AsSplitQuery()` in the bulk query (Pattern #13), and no static precompilation, the cache grows with each unique parameter combination. These objects live in static cache — GC cannot collect them.

- Threshold: < 500 = healthy, > 2,000 = action required. 17,557 = critical.
- Fix: extract `GetSubOrderMessage` bulk query as `static readonly Func<>` using `EF.CompileAsyncQuery` (Pattern #28)

**Finding 2 — SqlClient buffers: 2.7 MB alive at snapshot**

13,663 `_SqlMetaData` objects = column schema descriptors for ~13,663 columns of open result sets. 8,188 `SqlBuffer` objects = raw column data still held. The 3 per-sub-order calls kept as-is (`GetStoreLocation`, `getPackageInfoByOrderAndSubOrder`, `GetPackageTb`) each use raw ADO.NET — verify all use `await using` on `DbCommand` and `SqlDataReader`.

**Finding 3 — ChangeTracker entities ABSENT (confirms AsNoTracking working)**

Domain objects in heap:
- `SubOrderMessageAddressViewModel`: 836 objects, 234 KB
- `SubOrderItemDeliveryWindowModel`: ~50 objects, 14 KB

No large EF proxy entity clusters. Phase 3 `AsNoTracking()` fully effective — the sawtooth pattern from the live log is gone.

**GC improvement action plan (priority order)**:

| Priority | Action | Expected Impact |
|----------|--------|-----------------|
| P0 | Add `EF.CompileAsyncQuery` static field for bulk GetSubOrderMessage query | Reduce DynamicMethod 17,557 → < 50; free ~6 MB static heap |
| P1 | Verify `await using` on all ADO.NET calls in GetStoreLocation, getPackageInfoByOrderAndSubOrder, GetPackageTb | Eliminate SqlBuffer/SqlMetaData accumulation |
| P2 | Phase 4 async parallel execution (Task.WhenAll) | Reduce request duration → heap released faster per request |
| P3 | IMemoryCache on GetStoreLocation (5-min TTL, key = BU+SourceBU+SourceLoc) | Eliminate N identical queries per request |

---

### Heap Dump Analysis — Order.API-11.dmp (Load Test, 2026-03-31)

**Dump taken after P0+P1 fixes under load test. Total: 782,396 objects, ~90 MB.**

```
Top heap consumers (heapstat-4.txt):
  System.Byte[]                              42,251 objects    8.9 MB  → HTTP buffers — normal
  System.String                              80,399 objects    6.3 MB  → SQL text, logs — normal
  System.Char[]                              10,813 objects    1.7 MB  → normal
  System.Reflection.Emit.DynamicILGenerator   7,356 objects    1.1 MB  ← stable (was 17,557)
  System.Reflection.Emit.DynamicMethod        7,356 objects    942 KB  ← stable (was 17,557)
  Microsoft.Data.SqlClient._SqlMetaData       6,242 objects    1.0 MB  ← concurrent load, GC-reclaimable
  System.Reflection.Emit.DynamicResolver      7,335 objects    528 KB  ← stable (was 17,539)
  Microsoft.Data.SqlClient.SqlBuffer          5,442 objects    348 KB  ← concurrent load, GC-reclaimable
  Free                                        8,458 objects   32.6 MB  ← post-GC fragmentation, normal
  SubOrderMessageViewModel                       50 objects   17.2 KB  ← only active requests (was 836)
```

**Side-by-side vs heapstat-3 (pre-fix):**

| Metric | heapstat-3 | heapstat-4 | Change |
|--------|-----------|-----------|--------|
| Total objects | 1,327,781 | 782,396 | -41% |
| Total heap | 112 MB | 90 MB | -20% |
| DynamicMethod | 17,557 | **7,356** | **-58%** |
| DynamicILGenerator | 17,557 | **7,356** | **-58%** |
| DynamicResolver | 17,539 | **7,335** | **-58%** |
| _SqlMetaData | 13,663 | 6,242 | -54% (load-proportional) |
| SqlBuffer | 8,188 | 5,442 | -34% (load-proportional) |
| SubOrderMessageViewModel | 836 | **50** | **-94%** |

**Finding 1 — EF compiled query cache stabilised**

Before: 17,557 DynamicMethod — same queries recompiled on every unique call variation → unbounded growth.
After: 7,356 DynamicMethod — represents entire service's unique query footprint across all endpoints compiled once during load test. **Stable ceiling: will not grow further unless new query shapes are added.**

7,356 × all Reflection.Emit types ≈ 3.2 MB total static cache. Acceptable for a service this size.

**Finding 2 — No ChangeTracker leak under concurrency**

SubOrderMessageViewModel: 836 → 50 (only active in-flight requests at snapshot time). `AsNoTracking()` confirmed effective under concurrent load. The sawtooth pattern and 260 MB concurrency risk from baseline are eliminated.

**Finding 3 — Heap fragmentation (32.6 MB free)**

Post-load-test GC fragmented the heap but all 32.6 MB is reusable without growing the process. Fragmented blocks: String (624 KB), Int32[] (1 MB), CancellationTokenSource (1.1 MB), Byte[] (790 KB). Normal pattern — no action needed.

**Finding 4 — SqlBuffer / _SqlMetaData load-proportional (not a leak)**

Under concurrent load, multiple SqlDataReaders are open simultaneously. These objects are GC-reclaimable and scale with concurrent request count. Confirmed not a leak: count is proportional to load, not growing between requests.

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
| **Knowledge (KOS)** | K25, K28, K29 |
| **Pattern** | Batch Query → `references/patterns.md` #1 |
| **Pattern** | Eager Graph Loading → `references/patterns.md` #11 |
| **Pattern** | Coordinator-Level Resolution → `references/patterns.md` #12 |
| **Pattern** | Bulk Load Then Map → `references/patterns.md` #13 |
| **Pattern** | Async Parallel DB Coordinator (new) → `references/patterns.md` #26 |
| **Pattern** | EF Compiled Query Cache Management → `references/patterns.md` #28 |
| **Pattern (KOS)** | P7, P16, P17, P18, P19, P20, P22 |
| **Decision** | Eager load via Include() chain over lazy Entry().Load() on hot-path read methods |
| **Decision** | Resolve canonical OrderId once at coordinator level — not inside each sub-call |
| **Decision** | Option A (Batch Refactor) Phase 1-3 complete; Option B (Async Parallel) Phase 4 applied 2026-03-27 |
| **Decision** | Use IDbContextFactory over shared _context for parallel async paths — thread safety |
| **Knowledge** | EF Core DbContext is not thread-safe → IDbContextFactory required for parallel tasks |
| **Decision (KOS)** | D8, D9, D10, D11, D13, D14 |
| **Tech Assets** | Stopwatch + GC instrumentation snippet, Prometheus histogram snippet, EF LogTo config snippet |
| **Tech Assets** | `GetSubOrderAsync` + `MapPayments` + `MapPromotions` + `MapRewardItems` snippets (incident2.cs) |
| **Tech Assets (KOS)** | TA7, TA8, TA9, TA10, TA11, TA15, TA16 |
| **Heap Dump** | `heapstat-3.txt` — Order.API-3.dmp (2026-03-31, pre-fix): 17,557 DynamicMethod, SqlClient buffers, ChangeTracker absent |
| **Heap Dump** | `heapstat-4.txt` — Order.API-11.dmp (2026-03-31, load test post-fix): DynamicMethod stable at 7,356 (-58%), heap 90 MB (-20%), SubOrderMessageViewModel 50 (-94%), no ChangeTracker leak under concurrency |

---

## 2. PostgreSQL Dead Tuple Bloat — stockadjustments

### Overview

| Field | Value |
|-------|-------|
| **Title** | PostgreSQL Dead Tuple Bloat — stockadjustments (spc_inventory) |
| **Severity** | High |
| **System** | spc_inventory — stockadjustments table |
| **Status** | Fixed — All critical actions complete 2026-03-30. Monitoring job deferred to next phase. |
| **Date Identified** | 2026-03-30 |
| **Date Fixed** | 2026-03-30 |
| **Knowledge (KOS)** | K26, K27 |
| **Pattern (KOS)** | P21 |
| **Decision (KOS)** | D12 |
| **Tech Assets (KOS)** | TA12, TA13, TA14 |

---

### Symptoms

- `stockadjustments` table: 702,783 dead rows (14.50% dead ratio) out of 4,144,411 live rows
- `last_autovacuum` was NULL — autovacuum had **never run** on this table
- Index scans degraded: sparse B-tree traversal due to high dead index page ratio
- No explicit errors — silent performance degradation (slower range queries, bloated storage)
- Other tables: `StockSyncTracker` 72.73% dead ratio (32 dead / 12 live) — tiny table, autovacuum caught it

---

### Root Cause

**PostgreSQL default autovacuum scale factor (0.20) is too high for large tables — autovacuum trigger was never reached.**

```
Autovacuum trigger formula:
  threshold = autovacuum_vacuum_threshold + autovacuum_vacuum_scale_factor × n_live_tup
            = 50 + 0.20 × 4,144,411
            = 828,932 dead rows required to trigger

Actual dead rows at incident: 702,783 — still 126,149 below trigger
Result: autovacuum never fired, dead tuples accumulated silently
```

Secondary problem: even after manual VACUUM, **index bloat remained** — VACUUM marks index pages as "reusable" but does not compact or shrink the index files.

---

### VACUUM Output Analysis (2026-03-30)

```
Pages removed:        6,975 pages (54 MB freed from heap)
Dead index entries:   702,347 removed across 6 indexes
Heap tuples removed:  2,492 (partial scan — 32.23% of heap pages)
Duration:             41.72 seconds (non-blocking)
Dead remaining:       0 — heap is clean
```

**Index bloat after VACUUM (critical finding):**

| Index | Total Pages | Reusable Pages | Bloat % | Est. Wasted |
|---|---|---|---|---|
| `stockadjustments_pkey` | 76,838 | 65,465 | **85%** | ~510 MB |
| `stockadjustments_adjusted_at_idx` | 22,297 | 18,906 | **85%** | ~148 MB |
| `stockadjustments_sync_stock_seq_idx` | 22,296 | 18,904 | **85%** | ~148 MB |
| `stockadjustments_adjustment_type_idx` | 26,502 | 20,227 | **76%** | ~158 MB |
| `stockadjustments_product_id_idx` | 35,093 | 9,267 | **26%** | ~72 MB |
| `stockadjustments_stock_id_idx` | 34,327 | 4,631 | **13%** | ~36 MB |
| **TOTAL** | **217,353** | **137,400** | **63%** | **~1.07 GB** |

VACUUM marks pages "reusable" — B-tree index files do not shrink. Index scans traverse a 63% sparse B-tree = 2.7× more I/O than a clean index.

---

### Back-of-Envelope

```
Table heap bloat:
  702,783 dead rows × ~200 bytes/row = ~140 MB wasted heap storage
  Sequential scan: +14.5% extra I/O per full scan

Index bloat:
  Total index: 217,353 pages × 8KB = ~1.7 GB
  Dead/reusable: 137,400 pages × 8KB = ~1.07 GB wasted
  Effective index data: ~630 MB — everything else is traversed for nothing

B-tree traversal overhead:
  pkey index: 76,838 total pages, only ~11,373 contain live data (15%)
  Every PK lookup traverses 6.7× more pages than needed
  Every FK join resolving stockadjustments_pkey hits ~85% empty pages
```

---

### Fix

**Step 1 — Immediate: Manual VACUUM (applied 2026-03-30)**
```sql
VACUUM (ANALYZE, VERBOSE) stockadjustments;
VACUUM (ANALYZE) "StockSyncTracker";
ANALYZE "ShipAdjustment";  -- 6,076 n_mod_since_analyze, stale stats
```

**Step 2 — Prevent recurrence: Per-Table Autovacuum Tuning**
```sql
-- Trigger vacuum at 1% dead rows (~41K) instead of 20% (~828K)
ALTER TABLE stockadjustments SET (
  autovacuum_vacuum_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 1000,
  autovacuum_analyze_scale_factor = 0.005,
  autovacuum_analyze_threshold = 500
);

ALTER TABLE stock SET (
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.01
);
```

**Step 3 — Reclaim index space: REINDEX CONCURRENTLY (pending)**
```sql
-- Rebuilds index from scratch — no table lock, reads/writes continue
-- Run one at a time. Each takes 5–15 minutes on 4M rows.
REINDEX INDEX CONCURRENTLY stockadjustments_pkey;
REINDEX INDEX CONCURRENTLY stockadjustments_adjusted_at_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_sync_stock_seq_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_adjustment_type_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_product_id_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_stock_id_idx;
-- Expected: ~1.7 GB → ~630 MB index size; 2-3× faster index scans
```

---

### Prevention

```
[✅] VACUUM (ANALYZE) stockadjustments              — heap clean, 702K dead tuples removed
[✅] ALTER TABLE autovacuum_vacuum_scale_factor=0.01 — triggers at ~41K dead rows going forward
[✅] REINDEX CONCURRENTLY all 6 indexes             — ~1.7 GB → 251 MB (-85%), B-tree density restored
[✅] VACUUM ANALYZE ShipAdjustment                  — stale stats refreshed
[✅] StockSyncTracker                               — autovacuum handling it, no manual action needed
[ ] Add dead_ratio monitoring to external scheduler — DEFERRED to next phase
    Query: see TA12 — Dead Tuple Health Monitor
    Alert threshold: dead_ratio > 5% on tables > 100K rows
    Tool: pg_cron / Grafana / external cron — choose based on available infra
```

**Ongoing prevention rules:**
```
[ ] Every table > 500K rows must have autovacuum_vacuum_scale_factor = 0.01
[ ] Every table > 5M rows must have autovacuum_vacuum_scale_factor = 0.005
[ ] After heavy DELETE/UPDATE migrations: check pg_stat_user_tables before and after
[ ] After manual VACUUM on large tables: check index bloat and run REINDEX CONCURRENTLY
[ ] Long-running transactions block VACUUM — monitor pg_stat_activity for idle-in-transaction
```

---

### Lesson Learned

> **PostgreSQL default autovacuum is calibrated for small tables. For large tables (> 500K rows), the default scale_factor = 0.20 means hundreds of thousands of dead rows accumulate before vacuum fires. This is silent: no errors, no alerts, just steadily degrading query performance.**

> **VACUUM cleans the heap but does not shrink index files. After a high-churn period, REINDEX CONCURRENTLY is needed to recover the index space. VACUUM alone is not enough.**

**Architectural rules extracted:**
- Dead tuple ratio > 5% on a table > 100K rows = performance incident
- Per-table autovacuum tuning is mandatory for any table expected to exceed 500K rows
- After VACUUM, always check index bloat separately — they are independent problems
- `REINDEX CONCURRENTLY` is safe for production (no lock) and should be used whenever index bloat > 30%
- "Autovacuum never ran" + large table = almost certainly a scale_factor configuration problem

---

### KOS Links

| Type | Record |
|------|--------|
| **Knowledge** | PostgreSQL MVCC and Dead Tuples (K26) |
| **Knowledge** | Autovacuum Scale Factor Trap for Large Tables (K27) |
| **Pattern** | Per-Table Storage Hygiene — Autovacuum Tuning (P27) |
| **Decision** | REINDEX CONCURRENTLY vs VACUUM FULL vs Accept Reusable Pages (D12) |
| **Tech Assets** | Dead Tuple Health Monitor Query (TA12) |
| **Tech Assets** | Per-Table Autovacuum Configuration SQL (TA13) |
| **Tech Assets** | REINDEX CONCURRENTLY Script (TA14) |

---

### Results (Measured 2026-03-30)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Heap dead_ratio | 14.50% (702,783 dead rows) | **0.00%** (0 dead rows) | -100% |
| Total index size | ~1.7 GB (est. from page counts) | **251 MB** (measured) | **-85% (~1.45 GB reclaimed)** |
| `stockadjustments_pkey` | ~600 MB | **89 MB** | -85% |
| `stockadjustments_stock_id_idx` | ~268 MB | **44 MB** | -84% |
| `stockadjustments_product_id_idx` | ~274 MB | **35 MB** | -87% |
| `stockadjustments_adjusted_at_idx` | ~174 MB | **28 MB** | -84% |
| `stockadjustments_sync_stock_seq_idx` | ~174 MB | **28 MB** | -84% |
| `stockadjustments_adjustment_type_idx` | ~207 MB | **27 MB** | -87% |
| B-tree density | ~15% live pages (pkey) | **~100% live pages** | fully restored |

**Actual outcome exceeded estimate**: predicted ~630 MB post-REINDEX, actual = 251 MB. Effective index data was smaller than the reusable-page estimate suggested — original bloat was ~85%, not 63%.

**Additional finding from idx_scan data:**

| Index | idx_scan | Assessment |
|---|---|---|
| `stockadjustments_pkey` | 3,006 | Active — FK joins + PK lookups |
| `stockadjustments_adjusted_at_idx` | 2 | Occasional range queries |
| `stockadjustments_stock_id_idx` | 0 | Potentially unused |
| `stockadjustments_product_id_idx` | 0 | Potentially unused |
| `stockadjustments_sync_stock_seq_idx` | 0 | Potentially unused |
| `stockadjustments_adjustment_type_idx` | 0 | Potentially unused |

4 of 6 indexes show zero scans. Each unused index adds write overhead on every INSERT/UPDATE/DELETE with no read benefit. Monitor over 30 days — if still 0, consider dropping to reduce write amplification.