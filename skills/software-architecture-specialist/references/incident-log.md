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
| **Title** | GetSubOrder API Latency Spike |
| **Severity** | High |
| **System** | SubOrder Processing |
| **Status** | Resolved |

---

### Symptoms

- API response time: timeout on large requests (orders with many sub-orders × items)
- Estimated ~560 DB queries per call on a realistic order (10 sub-orders × 5 items, 3 promotions)
- Latency scaled as O(n×m) — sub-orders × items, not O(1)
- No infrastructure issue — problem is entirely in the data access layer
- Hot path: called from large batch requests, so any per-request cost is multiplied

---

### Root Cause

**N+1 query pattern stacked 7 levels deep across EF Core lazy loads, redundant reference resolution, and double-query patterns.**

Query count breakdown for 10 sub-orders × 5 items:

| Source | Pattern | Queries |
|--------|---------|---------|
| `IsExistOrderReference` — called once per sub-order | `.Any()` + `.FirstOrDefault()` — 2 hits per call | 20 |
| `GetLatestOrder` — called per sub-order | `.Any()` + `.FirstOrDefault()` | 20 |
| SubOrder EF `AsSplitQuery` per sub-order | 4–5 round-trips × 10 sub-orders | ~50 |
| `GetOrderItemOtherInfo` per item (line 805) | `.Count()` + `.FirstOrDefault()` = 2 queries per item | 100 |
| Amount lazy loads per item (Normal, Paid, RetailPrice + Taxes) | 4 × `Entry.Reference/Collection.Load()` per item | 200 |
| FulFillment.DeliveryWindow + Promotion + Promotions per item | 3 × `Entry.Collection/Reference.Load()` per item | 150 |
| `GetOrderPromotion` N+1 on Amount (line 167) | `Entry(datalist[i]).Reference(Amount).Load()` per promotion | 3 |
| `GetOrderHeader` double query (line 441–451) | `.Any()` then `.FirstOrDefault()` | 2 |
| `IsExistOrderReference` called independently for Header + Payments + Promotions | 3 separate calls to same table | 9 |
| Reward items loop for `SourceSubOrderId == "All"` | 1 query per sub-order | 10 |
| **Total** | | **~564** |

Per `decision-rules.md`: `> 100 queries per request = CRITICAL, must fix before merge.`

**7 specific bugs found (ranked by impact):**

**BUG-1 — `GetOrderItemOtherInfo` double-query inside item loop (line 805)**
```csharp
// Called per item — .Count() > 0 then .FirstOrDefault() = 2 round-trips per item
var itemOtherInfo = GetOrderItemOtherInfo(orderId, subOrderId, itemModel.SourceItemId, itemModel.SourceItemNumber);
```

**BUG-2 — 7 lazy `Entry().Load()` calls inside item loop (lines 819–982)**
```csharp
// Inside foreach (SubOrderItemModel itemModel in subOrderModel.Items):
_context.Entry(itemModel.Amount).Reference(p => p.Normal).Query().Include(i => i.Taxes).Load();
_context.Entry(itemModel.Amount).Reference(p => p.Paid).Query().Include(i => i.Taxes).Load();
_context.Entry(itemModel.Amount).Reference(p => p.RetailPrice).Load();
_context.Entry(itemModel.Amount.RetailPrice).Collection(p => p.Taxes).Load();
_context.Entry(itemModel.FulFillment).Collection(p => p.DeliveryWindow).Load();
_context.Entry(itemModel).Reference(p => p.Promotion).Load();
_context.Entry(itemModel).Collection(p => p.Promotions).Load();
// = 7 DB calls × N items
```

**BUG-3 — `IsExistOrderReference` called 3 times independently for same `SourceOrderId`**
```csharp
var orderHeader   = GetOrderHeader(SourceOrderId);        // → resolves reference internally
var orderPayments = GetOrderMessagePayments(SourceOrderId); // → resolves reference again
results.OrderPromotion = GetOrderPromotion(SourceOrderId);  // → resolves reference again
```

**BUG-4 — `IsExistOrderReference` itself is 2–3 queries (lines 455–468)**
```csharp
if (_context.Order.Where(...).Any())                       // query 1
if (_context.OrderReference.Where(...).Any())              // query 2
var OrderRef = _context.OrderReference.Where(...).FirstOrDefault(); // query 3
```

**BUG-5 — `GetOrderHeader` double-query (lines 441–451)**
```csharp
if (_context.Order.Where(...).Any())                       // query 1 — existence check
    return _context.Order.Include(...).Where(...).FirstOrDefault(); // query 2
```

**BUG-6 — `GetOrderPromotion` N+1 on Amount (line 167)**
```csharp
for (int i = 0; i < datalist.Length; i++)
{
    _context.Entry(datalist[i]).Reference(x => x.Amount).Load(); // 1 query per promotion
}
```

**BUG-7 — `GetLatestOrder` double-query (lines 590–596)**
```csharp
if (_context.OrderReference.Where(...).Any())              // query 1
var orderRef = _context.OrderReference.Where(...).FirstOrDefault(); // query 2
```

---

### Fix

**Phase 1 — Move all lazy loads into Include() chain (highest impact)**

```csharp
// BEFORE: bare SubOrder load + 7 lazy loads per item inside loop
SubOrderModel subOrderModel = _context.SubOrder
    .Include(s => s.Addresses)
    .Include(s => s.Items).ThenInclude(i => i.Amount)
    .Include(s => s.Items).ThenInclude(i => i.FulFillment)
    .AsSplitQuery()
    .Where(...).FirstOrDefault();

// AFTER: full graph loaded in one shot — delete all Entry().Load() calls
SubOrderModel subOrderModel = _context.SubOrder
    .Include(s => s.Addresses)
    .Include(s => s.Items)
        .ThenInclude(i => i.Amount)
            .ThenInclude(a => a.Normal).ThenInclude(n => n.Taxes)
    .Include(s => s.Items)
        .ThenInclude(i => i.Amount)
            .ThenInclude(a => a.Paid).ThenInclude(p => p.Taxes)
    .Include(s => s.Items)
        .ThenInclude(i => i.Amount)
            .ThenInclude(a => a.RetailPrice).ThenInclude(r => r.Taxes)
    .Include(s => s.Items)
        .ThenInclude(i => i.FulFillment).ThenInclude(f => f.DeliveryWindow)
    .Include(s => s.Items).ThenInclude(i => i.Promotion)
    .Include(s => s.Items).ThenInclude(i => i.Promotions)
    .AsSplitQuery()
    .AsNoTracking()
    .Where(...).FirstOrDefault();
```

**Phase 2 — Batch `ItemOtherInfo` per sub-order**

```csharp
// BEFORE: 2 queries per item inside loop
var itemOtherInfo = GetOrderItemOtherInfo(orderId, subOrderId, itemModel.SourceItemId, itemModel.SourceItemNumber);

// AFTER: 1 query before loop, O(1) lookup inside
var otherInfoMap = _context.ItemOtherInfo
    .Where(w => w.SourceOrderId == orderId && w.SourceSubOrderId == subOrderId)
    .AsNoTracking()
    .ToDictionary(w => (w.SourceItemId, w.SourceItemNumber));

// Inside loop:
if (otherInfoMap.TryGetValue((itemModel.SourceItemId, itemModel.SourceItemNumber), out var itemOtherInfo))
{
    orderItemViewModel.Soh = itemOtherInfo.Soh;
    orderItemViewModel.TimeStamp = itemOtherInfo.TimeStamp;
}
```

**Phase 3 — Resolve canonical OrderId once at top of GetSubOrder**

```csharp
// Resolve once — pass resolved ID to all downstream calls
string resolvedOrderId = ResolveOrderId(SourceOrderId); // single helper, single query
var orderHeader        = GetOrderHeader(resolvedOrderId);
var orderPayments      = GetOrderMessagePayments(resolvedOrderId);
results.OrderPromotion = GetOrderPromotion(resolvedOrderId);
```

**Phase 4 — Fix `GetOrderPromotion` N+1**

```csharp
// BEFORE: load promotions, then Entry.Load() per item
// AFTER: eager load Amount in initial query
OrderPromotionModel[] datalist = _context.OrderPromotion
    .Include(p => p.Amount)
    .AsNoTracking()
    .Where(p => p.SourceOrderId == SourceOrderId)
    .ToArray();
// Remove the per-item Entry().Reference(Amount).Load() call entirely
```

**Phase 5 — Collapse all Any() + FirstOrDefault() double-queries**

```csharp
// BEFORE: 2 queries
if (_context.Order.Where(...).Any())
    return _context.Order.Include(...).Where(...).FirstOrDefault();

// AFTER: 1 query
return _context.Order
    .AsNoTracking()
    .Include(o => o.Customer)
    .Where(w => w.IsActive && w.SourceOrderId == orderId)
    .FirstOrDefault(); // null check at caller
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

**Baseline targets per metric (fill in before fix, compare after):**

| Metric | Baseline (before) | Target (after) | Actual (after) |
|--------|-------------------|----------------|----------------|
| ElapsedMs (P99) | ___ ms | < 300ms | — |
| DB query count per request | ~560 | < 30 | — |
| MemAllocatedKB per call | ___ KB | -40% | — |
| GC.Gen0 delta per call | ___ | significant drop | — |
| GC.Gen1 delta per call | ___ | 0 | — |

**What each metric reveals:**
- `ElapsedMs` — direct latency impact
- `DB query count` — confirms N+1 is eliminated
- `MemAllocatedKB` — EF tracking overhead; `AsNoTracking` will drop this visibly
- `GC.Gen0 delta` — short-lived object churn from EF proxy objects; drops after batch fix
- `GC.Gen1 delta` — if non-zero inside a request, memory pressure is serious

---

### Results

| Metric | Before | After (estimated) |
|--------|--------|-------------------|
| Response time | timeout | < 200ms |
| DB queries per request | ~564 | ~20–30 |
| MemAllocatedKB | pending baseline | -40% (AsNoTracking) |
| GC.Gen0 per call | pending baseline | significant drop |

> Fill in actual numbers after running baseline instrumentation and post-fix measurement.

---

### Prevention

```
[ ] Any DB call inside a foreach or for loop?                    → BLOCK immediately
[ ] Any Entry().Reference().Load() or Entry().Collection().Load()?  → Replace with Include() chain
[ ] Any Any() followed by FirstOrDefault() on same predicate?    → Collapse to one query
[ ] Same ID resolved by IsExistOrderReference multiple times?    → Resolve once, pass down
[ ] All GET endpoint queries using AsNoTracking()?               → Required on every read
[ ] Query count logged before merging?                           → Use EF Core LogTo or MiniProfiler
[ ] Stopwatch + GC baseline captured before and after fix?       → Required for hot-path changes
```

---

### Lesson Learned

> **Lazy load accumulation**: each `Entry().Load()` looks harmless in isolation. The problem only appears when you trace the full call graph — not just the method. Architects review call graphs, not individual methods.

> **Shared context resolution**: when a sub-call resolves the same data the parent already knows (e.g. `IsExistOrderReference`), the design has a hidden coupling gap. Fix: resolve shared context at the coordinator level and inject the result.

> **Latency ≈ DB query count × average round-trip time.** EF Core does not batch automatically. Every `.Load()` inside a loop is a performance bug waiting for enough data to detonate.

**Architectural rules extracted:**
- Never trust EF Core to batch automatically — it doesn't
- Every `.Load()` inside a loop is a block, not a warning
- Resolve shared context (order reference lookups, header data) once at the coordinator and pass it down — never re-resolve independently in each sub-call
- Instrument before you fix — a fix without a baseline is anecdotal

---

### KOS Links

| Type | Record |
|------|--------|
| **Knowledge** | N+1 Query Problem, Batch Query Pattern, EF Core Best Practices, GC pressure from EF tracking |
| **Pattern** | Avoid N+1 Query → see `references/patterns.md` #1 |
| **Decision** | Eager load via Include() chain over lazy Entry().Load() on hot-path read methods |
| **Decision** | Resolve canonical OrderId once at coordinator level — not inside each sub-call |
| **Tech Assets** | Stopwatch + GC instrumentation snippet, Prometheus histogram snippet, EF LogTo config snippet |