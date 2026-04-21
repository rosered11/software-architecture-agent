# KOS — Incident Log

> Cross-linked per the Incident → Knowledge → Pattern → Decision → Reuse loop.

---

## INCIDENT LOG

---

### I1: GetSubOrder API Latency Spike

```
Title:               GetSubOrder API Latency Spike — Timeout Under High Concurrency
Severity:            High
System:              SubOrder Processing
Status:              Validated — Phase 5 confirmed 2026-04-07: Single ~950ms, All ~950ms (converged by design); P3 IMemoryCache pending
Date:                2026-03-25
Problem:             API timeout under high concurrent load. ~33 DB queries per request
                     (N+1 loops, redundant reference resolution, lazy loading in loops).
                     100 concurrent × 33 queries × ~10ms = 33s DB hold → pool exhaustion
                     → cascading timeouts. Latency scaled O(n) with sub-order count.
Root Cause:          N+1 query patterns across 3 loops, IsExistOrderReference called 3×
                     per request for same ID, duplicate Any()+FirstOrDefault() on same
                     predicate, lazy Entry().Reference().Load() inside a for loop,
                     no AsNoTracking() on any read path.
Lesson Learned:      Connection pool exhaustion = query_count × hold_time × concurrent_requests
                     > pool_size. Reducing query count 33 → 7 alone increases concurrency
                     ceiling 4×. Trace the full call graph — not individual methods.
                     Instrument before you fix — a fix without a baseline is anecdotal.
Prevention:          Code review: DB call in loop, Entry().Load() in loop, Any()+FirstOrDefault()
                     on same predicate, missing AsNoTracking(), same ID resolved independently
                     in sibling calls. Always capture baseline metrics before touching hot paths.
                     Validate connection pool math: queries × hold_time × concurrent < pool_size.
Related Knowledge:   → K25, K28, K29
Related Pattern:     → P7, P16, P17, P18, P19, P20, P22, P23
Related Decisions:   → D8, D9, D10, D11, D13, D14, D15
Related Tech Assets: → TA7, TA8, TA9, TA10, TA11, TA15, TA16
```

---

#### Symptoms

- API response time: **timeout** under high concurrent request load
- Estimated **~33 DB queries** per call for an order with 10 sub-orders
- Under 100 concurrent requests × 33 queries each = **3,300 DB round-trips** competing for the connection pool
- Connection pool exhaustion → new requests queue → cascading timeouts
- Latency scaled as O(n) with sub-order count, not O(1)
- No infrastructure issue — problem is entirely in the data access layer

---

#### Root Cause

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

#### Fix

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

**Expected result Phase 1: ~33 → ~22 queries**

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

**Expected result Phase 2: ~22 → ~18 queries**

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

**Expected result Phase 3: ~18 → ~7 queries**

---

**Phase 4 (Follow-up PR) — Async parallel coordinator**

```csharp
// Convert to async + parallel independent calls using IDbContextFactory
await using var ctx1 = _contextFactory.CreateDbContext();
await using var ctx2 = _contextFactory.CreateDbContext();
await using var ctx3 = _contextFactory.CreateDbContext();
await using var ctx4 = _contextFactory.CreateDbContext(); // all at coordinator scope
// IMPORTANT: ctx4 must be declared here even if conditionally used — see D15

var headerTask    = GetOrderHeaderAsync(ctx1, resolvedOrderId);
var paymentsTask  = GetOrderMessagePaymentsInternalAsync(ctx2, resolvedOrderId);
var promotionTask = GetOrderPromotionInternalAsync(ctx3, resolvedOrderId);
if (isGetRewardPromotion)
    rewardTask = GetRewardItemsBatchedAsync(ctx4, resolvedOrderId, subOrderIds);

await Task.WhenAll(headerTask, paymentsTask, promotionTask, rewardTask ?? Task.CompletedTask);
```

---

**Phase 5 (Follow-up PR) — Parallel bulk SubOrder load**

Split `_bulkSubOrderQuery` (27 sequential AsSplitQuery queries) into two independent compiled queries
run in parallel via `Task.WhenAll` + `IDbContextFactory`:

```csharp
// _bulkSubOrderHeaderQuery: Addresses, Remarks, Promotions, Fee (~9 split queries)
// _bulkSubOrderItemsQuery:  Items + all financial/fulfillment sub-graphs (~13 split queries)
await using var ctxHeader = contextFactory.CreateDbContext();
await using var ctxItems  = contextFactory.CreateDbContext();
var headerTask = Task.Run(() => _bulkSubOrderHeaderQuery(ctxHeader, orderIdsArr, subOrderIdsArr).ToList());
var itemsTask  = Task.Run(() => _bulkSubOrderItemsQuery(ctxItems,  orderIdsArr, subOrderIdsArr).ToList());
await Task.WhenAll(headerTask, itemsTask);
```

BotE prediction: ~900ms → ~455ms (parallel max). Actual Step 3: ~524ms.
Gap (~69ms vs predicted): PostgreSQL connection pool contention — two parallel tasks competing for pool slots simultaneously.
Total: **1,117ms → 741ms (-34%)**. Cold start req #1 = 6,620ms (EF.CompileQuery JIT, one-time).

---

#### Observability — Before/After Measurement

**Baseline captured 2026-03-25** — 30 sequential calls, single-user, SubOrderId `All`:

| Metric | Baseline (All) | Target (Phase 3) | Target (Phase 4) | Actual (Phase 4) | Actual (Phase 5) | Phase 5 — All (2026-04-07) |
|--------|----------------|------------------|------------------|------------------|------------------|---------------------------|
| ElapsedMs (P50) | **5,048ms** | < 300ms | < 100ms | **1,117ms (-78%)** | **741ms (-85%)** | **~950ms (-81%)** |
| ElapsedMs (best) | 3,193ms | — | — | **1,080ms (-66%)** | **723ms (-77%)** | **~893ms (-72%)** |
| AllocatedKB per call | 2,668 KB | < 1,500 KB | < 1,500 KB | **~1,980 KB** (+4 ctx) | **~2,020 KB** (+2 ctx) | **~2,020 KB** (stable) |
| DB query count | ~33 | ~7 | ~7 (parallel) | **~20** | **~20** (2 parallel bulk) | **~20** (same, batched) |
| Max concurrent (pool) | ~20 | ~200+ | ~400+ | **~400+** | **~400+** | **~400+** |
| GC pressure | Gen0–2 | — | — | Gen0 only | Gen0 only (single) | Gen0+Gen1 (see note) |

**Phase 5 "All" path GC note (2026-04-07):** Gen1 collection fires every ~13 calls (vs Gen0 every ~37 calls for single path). At 3 sub-orders this is acceptable — no latency spike observed (call #0D: 970ms normal). Monitor if order sub-order count grows to 10+.

**Key finding — latency convergence is by design:** "All" and single paths reach the same wall-clock time because `GetSubOrderMessageFromBatchAsync` replaces N sequential queries with 2 parallel compiled queries (`Task.WhenAll`). Latency is bounded by `max(headerQuery, itemsQuery)`, not `N × singleQuery`. AllocatedKB ~2× confirms real extra data — it is absorbed by parallel execution, not sequential cost.

---

#### Results

| Metric | Baseline | Phase 1 | Phase 2 | Phase 3+Idx | P0+P1 | Phase 4 | Phase 5 |
|--------|----------|---------|---------|-------------|-------|---------|---------|
| ElapsedMs (P50) | **5,048ms** | 2,600ms (-48%) | 2,514ms (-50%) | 1,410ms (-72%) | 1,242ms (-75%) | **1,117ms (-78%)** | **741ms (-85%)** |
| ElapsedMs (best) | 3,193ms | 2,571ms | 2,463ms | 1,371ms | 1,228ms | **1,080ms** | **723ms** |
| AllocatedKB | 2,668 KB | ~2,700 KB | ~2,655 KB | ~1,810 KB (-32%) | ~1,538 KB (-42%) | ~1,980 KB | ~2,020 KB |
| DB queries | ~33 | ~22 | ~18 | ~49¹ | ~20+N | **~20** | **~20** (2∥) |
| Max concurrent | ~20 | ~35 | ~40 | ~200+ | ~200+ | **~400+** | **~400+** |

¹ Phase 3 query count temporarily higher due to AsSplitQuery bulk load (16 Include paths × N sub-orders split into separate queries) — but single-pass bulk, not per-sub-order loop.

**Phase 3 failure note**: Attempt 1 replaced `Entry().Load()` inside loop with Include+AsSplitQuery inside the same loop — zero improvement (1:1 replacement). Fix: batch the outer loop entirely (Bulk Load Then Map). See D11.

---

#### Heap Dump Analysis — Order.API-3.dmp (2026-03-31)

**Dump taken after Phase 3 (AsNoTracking applied). Total: 1,327,781 objects, ~112 MB.**

```
Top heap consumers:
  System.Byte[]                              94,262 objects   19.8 MB  (17.6%)  → HTTP/JSON buffers — normal
  System.String                             157,652 objects   17.7 MB  (15.7%)  → SQL text, log strings — normal
  System.Char[]                              20,709 objects    7.5 MB  (6.7%)   → String internals — normal
  System.Reflection.Emit.DynamicILGenerator  17,557 objects    2.67 MB          ← NON-RECLAIMABLE
  Microsoft.Data.SqlClient._SqlMetaData      13,663 objects    2.19 MB          ← SqlDataReader column descriptors
  System.Reflection.Emit.DynamicMethod       17,557 objects    2.25 MB          ← NON-RECLAIMABLE
  System.Reflection.Emit.DynamicResolver     17,539 objects    1.26 MB          ← NON-RECLAIMABLE
  Microsoft.Data.SqlClient.SqlBuffer          8,188 objects    524 KB           ← SqlDataReader raw data
```

**Finding 1 — EF compiled query cache: 17,557 entries (~6 MB non-reclaimable)**
- Threshold: < 500 = healthy, > 2,000 = action required. 17,557 = critical.
- Fix: extract bulk SubOrder query as `static readonly Func<>` using `EF.CompileAsyncQuery` → see D13

**Finding 2 — SqlClient buffers: 2.7 MB alive at snapshot**
- 13,663 `_SqlMetaData` + 8,188 `SqlBuffer` — column descriptors and raw data from open result sets.
- Verify all ADO.NET calls use `await using` on `DbCommand` and `SqlDataReader`.

**Finding 3 — ChangeTracker entities ABSENT (confirms AsNoTracking working)**
- No large EF proxy entity clusters. Phase 3 `AsNoTracking()` fully effective.

**GC improvement action plan:**

| Priority | Action | Expected Impact |
|----------|--------|-----------------|
| P0 | `EF.CompileAsyncQuery` static field for bulk GetSubOrderMessage query | ✅ Done — DynamicMethod 17,557 → 7,356; freed ~3 MB |
| P1 | Verify `await using` on all ADO.NET calls | ✅ Done — SqlBuffer/SqlMetaData halved under load |
| P2 | Phase 4 async parallel (Task.WhenAll) coordinator | ✅ Done — 1,117ms |
| P3 | Phase 5 parallel bulk SubOrder (split compiled queries) | ✅ Done — 741ms (-34% from Phase 4) |
| P4 | IMemoryCache on GetStoreLocation (5-min TTL) | ⬜ Next — eliminate N identical queries per request |

---

#### Heap Dump Analysis — Order.API-11.dmp (Load Test, 2026-03-31)

**Dump taken after P0+P1 fixes under load test. Total: 782,396 objects, ~90 MB.**

| Metric | heapstat-3 (pre) | heapstat-4 (post) | Change |
|--------|------------------|--------------------|--------|
| Total objects | 1,327,781 | 782,396 | -41% |
| Total heap | 112 MB | 90 MB | -20% |
| DynamicMethod | 17,557 | **7,356** | **-58%** (stable ceiling) |
| _SqlMetaData | 13,663 | 6,242 | -54% (load-proportional) |
| SubOrderMessageViewModel | 836 | **50** | **-94%** |

7,356 DynamicMethod = entire service's unique query footprint compiled once. Stable — will not grow further. ~3.2 MB total static cache, acceptable.

---

#### Prevention

```
[ ] Any DB call inside a foreach or for loop?                    → BLOCK immediately
[ ] Any Entry().Reference().Load() inside a loop?                → Replace with Include() chain
[ ] Any Any() followed by FirstOrDefault() on same predicate?    → Collapse to one query
[ ] Same ID resolved by IsExistOrderReference multiple times?    → Resolve once at coordinator, pass down
[ ] All GET endpoint queries using AsNoTracking()?               → Required on every read path
[ ] Query count logged before merging?                           → Use EF Core LogTo or MiniProfiler
[ ] Stopwatch + GC baseline captured before and after fix?       → Required for hot-path changes
[ ] Connection pool math validated for expected concurrency?     → queries × hold_time × concurrent < pool_size
```

---

#### Lesson Learned

> **Connection pool math**: timeout under concurrency is not about a single slow query — it's about `query_count × hold_time × concurrent_requests > pool_size`. Reducing query count from 33 to 7 alone increases the concurrency ceiling by ~4×.

> **Lazy load accumulation**: each `Entry().Load()` looks harmless in isolation. The problem only appears when you trace the full call graph — not just the method. Architects review call graphs, not individual methods.

> **Shared context resolution**: when a sub-call resolves the same data the parent already knows (e.g. `IsExistOrderReference` called 3× for same ID), the design has a hidden coupling gap. Fix: resolve shared context at the coordinator level and inject the result.

**Architectural rules extracted:**
- Never trust EF Core to batch automatically — it doesn't
- Every `.Load()` inside a loop is a block, not a warning
- Resolve shared context once at the coordinator — never re-resolve independently in each sub-call
- Instrument before you fix — a fix without a baseline is anecdotal
- `AsNoTracking()` is mandatory on every read path — EF tracking overhead is never free

---

### I2: PostgreSQL Dead Tuple Bloat — stockadjustments

```
Title:               PostgreSQL Dead Tuple Bloat — stockadjustments (spc_inventory)
Severity:            High
System:              spc_inventory — stockadjustments table
Status:              Fixed — All critical actions complete 2026-03-30. Monitoring deferred.
Date:                2026-03-30
Problem:             14.50% dead ratio (702,783 dead rows out of 4,144,411 live).
                     last_autovacuum = NULL — autovacuum had never fired. Silent degradation:
                     slower range queries, ~1.07 GB index bloat across 6 indexes (63% sparse
                     B-tree), every PK lookup traversing 85% empty pages.
Root Cause:          Default autovacuum_vacuum_scale_factor = 0.20 requires 828,932 dead rows
                     to trigger on a 4M-row table. Actual dead rows (702,783) never reached
                     threshold. After VACUUM, index files retained bloat — VACUUM marks pages
                     reusable but does not compact or shrink index files.
Lesson Learned:      PostgreSQL default autovacuum is calibrated for small tables. Large tables
                     (> 500K rows) need per-table scale_factor tuning. VACUUM cleans the heap
                     but does not shrink index files — REINDEX CONCURRENTLY is needed separately.
                     "Autovacuum never ran" on a large table = almost always a scale_factor problem.
Prevention:          Every table > 500K rows: autovacuum_vacuum_scale_factor = 0.01.
                     After VACUUM on large table: always check index bloat, run REINDEX CONCURRENTLY.
                     Monitor dead_ratio > 5% on tables > 100K rows. Check pg_stat_activity for
                     long-running transactions blocking VACUUM.
Related Knowledge:   → K26, K27
Related Pattern:     → P21
Related Decisions:   → D12
Related Tech Assets: → TA12, TA13, TA14
```

---

#### Symptoms

- `stockadjustments` table: 702,783 dead rows (14.50% dead ratio) out of 4,144,411 live rows
- `last_autovacuum` was NULL — autovacuum had **never run** on this table
- Index scans degraded: sparse B-tree traversal due to high dead index page ratio
- No explicit errors — silent performance degradation (slower range queries, bloated storage)
- Other tables: `StockSyncTracker` 72.73% dead ratio (32 dead / 12 live) — tiny table, caught by autovacuum

---

#### Root Cause

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

#### VACUUM Output Analysis (2026-03-30)

```
Pages removed:        6,975 pages (54 MB freed from heap)
Dead index entries:   702,347 removed across 6 indexes
Heap tuples removed:  2,492 (partial scan — 32.23% of heap pages)
Duration:             41.72 seconds (non-blocking)
Dead remaining:       0 — heap is clean
```

**Index bloat after VACUUM (critical finding):**

| Index | Total Pages | Reusable Pages | Bloat % | Est. Wasted |
|-------|-------------|----------------|---------|-------------|
| `stockadjustments_pkey` | 76,838 | 65,465 | **85%** | ~510 MB |
| `stockadjustments_adjusted_at_idx` | 22,297 | 18,906 | **85%** | ~148 MB |
| `stockadjustments_sync_stock_seq_idx` | 22,296 | 18,904 | **85%** | ~148 MB |
| `stockadjustments_adjustment_type_idx` | 26,502 | 20,227 | **76%** | ~158 MB |
| `stockadjustments_product_id_idx` | 35,093 | 9,267 | **26%** | ~72 MB |
| `stockadjustments_stock_id_idx` | 34,327 | 4,631 | **13%** | ~36 MB |
| **TOTAL** | **217,353** | **137,400** | **63%** | **~1.07 GB** |

VACUUM marks pages "reusable" — B-tree index files do not shrink. Index scans traverse a 63% sparse B-tree = 2.7× more I/O than a clean index.

---

#### Fix

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

**Step 3 — Reclaim index space: REINDEX CONCURRENTLY**
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

#### Results (Measured 2026-03-30)

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Heap dead_ratio | 14.50% (702,783 dead rows) | **0.00%** | -100% |
| Total index size | ~1.7 GB | **251 MB** | **-85% (~1.45 GB reclaimed)** |
| `stockadjustments_pkey` | ~600 MB | **89 MB** | -85% |
| `stockadjustments_stock_id_idx` | ~268 MB | **44 MB** | -84% |
| `stockadjustments_product_id_idx` | ~274 MB | **35 MB** | -87% |
| `stockadjustments_adjusted_at_idx` | ~174 MB | **28 MB** | -84% |
| `stockadjustments_sync_stock_seg_idx` | ~174 MB | **28 MB** | -84% |
| `stockadjustments_adjustment_type_idx` | ~207 MB | **27 MB** | -87% |
| B-tree density (pkey) | ~15% live pages | **~100% live pages** | fully restored |

Actual outcome exceeded estimate: predicted ~630 MB post-REINDEX, actual = 251 MB.

**idx_scan findings (4 of 6 indexes show zero scans):**

| Index | idx_scan | Assessment |
|-------|----------|------------|
| `stockadjustments_pkey` | 3,006 | Active — FK joins + PK lookups |
| `stockadjustments_adjusted_at_idx` | 2 | Occasional range queries |
| `stockadjustments_stock_id_idx` | 0 | Potentially unused — monitor 30 days |
| `stockadjustments_product_id_idx` | 0 | Potentially unused — monitor 30 days |
| `stockadjustments_sync_stock_seq_idx` | 0 | Potentially unused — monitor 30 days |
| `stockadjustments_adjustment_type_idx` | 0 | Potentially unused — monitor 30 days |

---

#### Prevention

```
[✅] VACUUM (ANALYZE) stockadjustments              — heap clean, 702K dead tuples removed
[✅] ALTER TABLE autovacuum_vacuum_scale_factor=0.01 — triggers at ~41K dead rows going forward
[✅] REINDEX CONCURRENTLY all 6 indexes             — ~1.7 GB → 251 MB (-85%), B-tree density restored
[✅] VACUUM ANALYZE ShipAdjustment                  — stale stats refreshed
[ ] Add dead_ratio monitoring to external scheduler — DEFERRED to next phase
    Alert threshold: dead_ratio > 5% on tables > 100K rows. See TA12.
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

#### Lesson Learned

> **PostgreSQL default autovacuum is calibrated for small tables. For large tables (> 500K rows), the default scale_factor = 0.20 means hundreds of thousands of dead rows accumulate before vacuum fires. This is silent: no errors, no alerts, just steadily degrading query performance.**

> **VACUUM cleans the heap but does not shrink index files. After a high-churn period, REINDEX CONCURRENTLY is needed to recover the index space. VACUUM alone is not enough.**

**Architectural rules extracted:**
- Dead tuple ratio > 5% on a table > 100K rows = performance incident
- Per-table autovacuum tuning is mandatory for any table expected to exceed 500K rows
- After VACUUM, always check index bloat separately — they are independent problems
- `REINDEX CONCURRENTLY` is safe for production (no lock) and should be used whenever index bloat > 30%
- "Autovacuum never ran" + large table = almost certainly a scale_factor configuration problem

---

### I3: MySQL ETL Sync — Long-Lived Transaction Timeout Causes Airflow Job Failure

```
Title:               MySQL ETL Sync — Long-Lived Transaction Timeout Causes Airflow Job Failure
Severity:            High
System:              ETL Pipeline — SyncProductMasterJda / SyncProductBarcodeJda (Airflow + .NET)
Status:              Fix implemented 2026-04-08. Per-batch commit + Prometheus resource tracking metrics added.
Follow-Up:           I4 — added ETL resource tracking (batch duration, memory, records counter)
Date:                2026-04-03
Problem:             .NET sync job processing 3M records from staging DB to MySQL production DB
                     fails after a long run. Exit code 1. Airflow marks DAG run as failed.
                     Single transaction wraps entire 300-batch sync loop (~210s open).
                     MySQL innodb_lock_wait_timeout (default 50s) kills the connection,
                     triggering RollbackAsync(), exhausting Polly retry attempts, propagating
                     exit code 1 to Airflow.
Root Cause:          BeginTransactionAsync() at line 55 of ProcessSyncLoopAsync() wraps the
                     entire while(true) batch loop (lines 59–74) in a single DB transaction.
                     BotE: 300 batches × 700ms = 210s hold >> innodb_lock_wait_timeout (50s).
                     MySQL kills the connection → catch calls RollbackAsync() on dead connection
                     (second failure) → Polly retries=0 → exception propagates → exit code 1.
                     Airflow retries=0 → DAG run marked failed, no retry.
Lesson Learned:      Long-running ETL transactions must commit per batch, not per job.
                     TX hold = batch_count × batch_latency. Always BotE this before design.
Prevention:          Per-batch commit (TX inside loop). CommandTimeout(120) on DbContext.
                     Set Airflow retries=2 retry_delay=5min execution_timeout=40min.
                     Set subprocess timeout=1800s (derived from BotE: 300 × 1.5s × 3x safety factor).
Related Knowledge:   → K30, K32
Related Pattern:     → P24, P25
Related Decisions:   → D16, D17
Related Tech Assets: → TA19, TA20
Related Incidents:   → I4, I5, I6 (follow-ups: observability, OOM, copy-paste bug + batch size)
```

#### Symptoms

- Airflow DAG fails: `Exception: .NET job failed` (exit code 1) at `2026-04-03 11:47:41`
- Stack trace: `ProcessSyncLoopAsync() → MySqlTransaction.RollbackAsync() → Polly → Program.Main()`
- Job runs for a long time before failure (not immediate — confirms timeout, not config error)
- 0 records committed — all work lost on each run attempt

#### BotE — Transaction Hold Time

| Variable | Value |
|---|---|
| Total records | 3,000,000 |
| Batch size | 10,000 |
| Batch count | 300 |
| Avg staging read | ~500ms |
| Avg production insert | ~200ms |
| Per-batch duration | ~700ms |
| **Total TX hold** | **210 seconds** |
| MySQL `innodb_lock_wait_timeout` | 50s (default) |
| MySQL `net_read_timeout` | 30s (default) |
| **Risk** | **Certain failure** — 210s >> 50s |

#### Root Cause — Deep Analysis

The fundamental error: the commit boundary is the entire job, not the batch.

```csharp
// product.cs — ProcessSyncLoopAsync()
// Line 55: Transaction opened BEFORE the loop
await using var tx = await context.Database.BeginTransactionAsync(cancellationToken);
try
{
    long lastIdFromStaging = startingId;
    while (true)                              // 300 iterations for 3M records
    {
        var productStagings = await GetProductStaging(lastIdFromStaging, cancellationToken);
        // ...writes to production MySQL, all under same open TX...
        await SyncProductMasterAsync(...)
    }
    await tx.CommitAsync(cancellationToken);  // Line 66: unreachable — times out at batch ~43–71
}
catch (Exception ex)
{
    await tx.RollbackAsync(cancellationToken); // Line 81: also fails — connection already dead
    throw;
}
```

MySQL kills the connection at ~30–50s (whichever timeout fires first). When `MySqlConnector` throws, the `catch` block calls `tx.RollbackAsync()` on a dead TCP session — this throws a second exception. The stack trace confirms both failures. Polly has `retries=0` so the exception propagates immediately. Airflow sees exit code 1 and marks the DAG run failed with no retry.

#### Fix

Move `BeginTransactionAsync()` inside the `while(true)` loop. Each batch opens, commits, and closes its own short TX (~700ms hold). On failure: only the in-flight batch is rolled back. All prior batches remain committed. Idempotent restart via monotonic cursor (`WHERE Id > lastId`).

See → P24 for blueprint, → TA19 for full C# template.

#### Results (Expected Post-Fix)

| Metric | Before | After |
|---|---|---|
| TX hold time | ~210s | ~700ms per batch |
| MySQL timeout risk | Certain | Eliminated |
| On-failure data loss | 100% (3M records) | ≤ 0.03% (1 batch / 300 batches) |
| Restart | Full re-run from record 0 | Resume from last committed cursor |
| Airflow retry effectiveness | 0% (retries=0) | Effective — resumes from checkpoint |

---

### I4: MySQL ETL Sync — Zero Observability on Batch Resource Consumption

```
Title:               MySQL ETL Sync — Zero Observability on Batch Resource Consumption
Severity:            Medium
System:              ETL Pipeline — SyncProductMasterJda (Airflow + .NET)
Status:              Fix implemented 2026-04-08
Date:                2026-04-08
Problem:             After I3 fix (per-batch commit), the ETL job runs without timeout failures.
                     However, there are zero metrics on per-batch resource consumption: TX hold time,
                     memory allocation, staging read latency, records throughput. If batch latency
                     drifts (data volume growth, index degradation, connection pool contention),
                     there is no early warning — next symptom will be another timeout incident.
Root Cause:          ProcessSyncLoopAsync() in product.cs had no instrumentation beyond basic
                     log messages. No Prometheus metrics, no Stopwatch per batch, no GC tracking.
                     Observability gap: "a fix without measurement is anecdotal" (I3 lesson).
Lesson Learned:      Every ETL batch loop must expose: per-batch TX hold time (Histogram),
                     cumulative records counter, staging read latency, and GC allocation.
                     These are the 4 signals that predict the next timeout before it happens.
Prevention:          Prometheus metrics + structured logging with per-batch resource tracking.
                     Alert rules: WARN if batch_duration_p95 > 5s, CRIT if > 30s.
                     Dashboard: Grafana panel showing batch duration trend over time.
Related Knowledge:   → K31, K32
Related Pattern:     → P25
Related Decisions:   → D17
Related Tech Assets: → TA20, TA21
Related Incidents:   → I3 (predecessor), I5 (follow-up — OOM), I6 (follow-up — copy-paste bug + batch size)
```

#### Symptoms

- ETL job succeeds but provides no visibility into resource consumption per batch
- No way to detect batch latency drift before it causes a timeout
- No Prometheus metrics for alerting on TX hold time regression
- Memory allocation per batch unknown — cannot predict GC pressure at scale

#### BotE — Metric Budget

| Metric | Overhead per batch | Acceptable? |
|---|---|---|
| Stopwatch (2×: staging read + TX hold) | ~0.001ms | Yes — negligible |
| GC.GetTotalAllocatedBytes (2×) | ~0.01ms | Yes — non-precise mode |
| Prometheus Observe/Inc (5 calls) | ~0.005ms | Yes — in-process counters |
| Structured log (1 per batch) | ~0.1ms | Yes — async sink |
| **Total per batch** | **~0.12ms** | **< 0.02% of 700ms batch** |

#### Fix

Added 5 Prometheus metrics + Stopwatch + GC tracking to `ProcessSyncLoopAsync()` in `product.cs`:

1. **`etl_sync_batch_duration_seconds`** (Histogram) — per-batch TX hold time, buckets 0.1s–51.2s
2. **`etl_sync_records_processed_total`** (Counter) — cumulative records committed
3. **`etl_sync_current_batch_round`** (Gauge) — current batch round number
4. **`etl_sync_staging_read_seconds`** (Histogram) — staging read latency per batch
5. **`etl_sync_batch_alloc_bytes`** (Summary) — GC allocation per batch

Plus structured log per batch: TX hold ms, staging read ms, alloc MB, total records, job elapsed.
Plus job summary log on completion: total records, batch count, total duration, avg ms/batch.

#### Alert Rules (Prometheus)

```yaml
# WARN: batch TX hold drifting high
- alert: EtlBatchDurationHigh
  expr: histogram_quantile(0.95, rate(etl_sync_batch_duration_seconds_bucket[5m])) > 5
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "ETL batch P95 TX hold > 5s — investigate before timeout threshold"

# CRIT: approaching MySQL timeout
- alert: EtlBatchDurationCritical
  expr: histogram_quantile(0.95, rate(etl_sync_batch_duration_seconds_bucket[5m])) > 30
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "ETL batch P95 TX hold > 30s — imminent timeout risk (MySQL default 50s)"

# WARN: sync stall — no records processed
- alert: EtlSyncStall
  expr: increase(etl_sync_records_processed_total[5m]) == 0 and etl_sync_current_batch_round > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "ETL sync has not committed records in 5 minutes — possible stall"
```

#### Results

| Metric | Before | After |
|---|---|---|
| Per-batch TX hold visibility | None | Histogram with P50/P95/P99 |
| Memory allocation visibility | None | Summary per batch |
| Staging read latency visibility | None | Histogram per batch |
| Alert on latency drift | None | WARN > 5s, CRIT > 30s |
| Total overhead per batch | 0 | ~0.12ms (~0.02% of 700ms) |

#### Lesson Learned

> **Observability is not optional for ETL.** The I3 fix (per-batch commit) eliminated the timeout, but without metrics the fix is a black box. The next data volume doubling or index degradation will silently push batch duration from 700ms toward 50s with zero warning. Metrics close the loop: Incident → Fix → Measure → Alert → Prevent recurrence.

---

### I5: ETL Sync — OOM Risk from Oversized Batch + EF ChangeTracker Accumulation

```
Title:               ETL Sync — OOM Risk from Oversized Batch + EF ChangeTracker Accumulation
Severity:            High
System:              ETL Pipeline — SyncProductMasterJda / SyncProductBarcodeJda (Airflow + .NET)
Status:              Root cause confirmed. Fix implemented 2026-04-08.
Date:                2026-04-08
Problem:             Live Airflow log shows Batch 1: 100K records, TX hold 144s, alloc 5,757MB,
                     heap 1,191MB (+1,175MB). Batch 2: heap 1,780MB (+589MB). Heap growing every
                     batch — OOM expected by batch 4-5. Root: batch size config = 100K (10×
                     intended), EF ChangeTracker never cleared after commit, per-batch activity
                     tracking dictionary never cleared (grows to 3M entries across job).
Root Cause:          Three compounding issues: (1) BatchSize config returned 100K instead of 10K —
                     100K entities × 30 fields × EF SqlParameter per insert = ~5GB alloc per batch.
                     (2) context.ChangeTracker not cleared after tx.CommitAsync() — committed
                     entities remain tracked across batches, heap grows with each batch commit.
                     (3) productMasterActivityTracking Dictionary<string, Activity> created once in
                     ProcessAsync() and passed through loop — accumulates all 3M records in memory,
                     never flushed between batches.
Lesson Learned:      Per-batch commit prevents TX timeout but does NOT prevent memory accumulation.
                     After each commit: clear ChangeTracker (dead tracking weight) and flush the
                     activity tracking dictionary (unbounded growth). Batch size must be verified
                     in staging before prod — BotE: batch_size × fields × EF_overhead > 500MB = too large.
Prevention:          context.ChangeTracker.Clear() after tx.CommitAsync().
                     activityTracking.Clear() after each batch commit.
                     Verify batch size config in staging with heap metrics before deploying.
                     Alert: heap_delta > 200MB per batch = memory leak signal.
Related Knowledge:   → K31, K32
Related Pattern:     → P24, P25
Related Decisions:   → D16, D17
Related Tech Assets: → TA20, TA21
Related Incidents:   → I3, I4, I6 (follow-up — copy-paste bug + batch size near timeout)
```

#### Symptoms (from Airflow log 2026-04-08)

```
Batch 1: 100K records, TX hold 144,829ms, alloc 5,757MB, heap 1,191MB, heapDelta +1,175MB
Batch 2: 100K records, TX hold 139,447ms, alloc 6,346MB, heap 1,780MB, heapDelta +589MB
Projected Batch 3: heap ~2,200MB → OOM / Gen2 GC storm
```

#### BotE — Memory per Batch at 100K

| Source | Memory |
|---|---|
| 100K staging entities (AsNoTracking) loaded | ~100MB |
| 100K mapped Product objects | ~100MB |
| EF ChangeTracker: 100K entities × 30 fields × SqlParameter | ~3–4GB alloc |
| 100K ProductMasterActivity with JSON Payload per record | ~200MB |
| Dictionary accumulation across batches (3M entries) | ~500MB+ |
| **Total alloc per batch** | **~5,700MB (matches log)** |

At 10K batch size (correct config): ~570MB alloc per batch — within acceptable range.

#### Fix

Three changes applied to both `product.cs` and `barcode.cs`:

```csharp
await tx.CommitAsync(cancellationToken);

// Fix 1: release tracked entities — no longer needed after commit
context.ChangeTracker.Clear();

// Fix 2: flush activity tracking dictionary — prevent unbounded growth
productMasterActivityTracking.Clear();
```

Config fix: set `BatchSize = 10000` in appsettings (not a code change).

#### Results (Expected Post-Fix at 10K batch size)

| Metric | Before (100K batch) | After (10K batch + ChangeTracker.Clear) |
|---|---|---|
| TX hold per batch | ~144s | ~14s |
| Alloc per batch | ~5,757MB | ~200-300MB |
| Heap after batch 1 | 1,191MB | ~100-150MB |
| Heap delta (steady state) | +589MB per batch (growing) | ~0 (flat sawtooth) |
| OOM risk | Certain by batch 4-5 | Eliminated |

---

### I6: SyncProductBarcodeJda — Copy-Paste Bug in CheckPendingAsync + Batch Size Approaching MySQL Timeout

```
Title:               SyncProductBarcodeJda — CheckPendingAsync Copy-Paste Bug + 20K Batch Near Timeout
Severity:            High
System:              ETL Pipeline — SyncProductBarcodeJda / SyncProductMasterJda (Airflow + .NET)
Status:              Fix implemented 2026-04-08
Date:                2026-04-08
Problem:             Two issues discovered in follow-up review of I3/I5 fixes.
                     A) barcode.cs CheckPendingAsync queries SpcJdaProductStaging instead of
                     SpcJdaBarcodeStaging — copy-paste from product.cs. Silent failure: if product
                     staging has no pending rows but barcode staging does, entire barcode sync skips.
                     B) SyncProductMasterJda running at BatchSize=20K. Airflow logs show TX hold
                     27,082–39,689ms per batch (Batch 1: 39,689ms = 79% of MySQL 50s timeout).
                     CRIT alert threshold (>30s) already firing for Batches 1, 9, 10.
Root Cause:          A) barcode.cs was cloned from product.cs. GetProductStaging() was correctly
                     updated to SpcJdaBarcodeStaging, but CheckPendingAsync() retained the original
                     SpcJdaProductStaging reference — silent wrong-table query.
                     B) BatchSize config not reduced to 10K after I5 fix. At 20K: TX hold scales to
                     ~28–40s (linear with I5 BotE: 100K→144s, 10K→14s, 20K→28s). Any write latency
                     spike → timeout breach.
Lesson Learned:      Clone validation is not optional. After cloning an ETL sync service, all DbSet
                     references must be audited in both the staging query AND CheckPendingAsync.
                     These are independent call sites — updating one does not update the other.
                     Batch size calibration: verify actual TX hold vs timeout limit after every
                     config change. 20K→28–40s leaves zero headroom vs 50s MySQL timeout.
Prevention:          ETL clone checklist (→ P26): verify 6 touch points before merging a cloned service.
                     Batch size rule (→ D18): batch_size × avg_write_ms < timeout × 0.5 (50% margin).
                     At current throughput: 10K = ~14s = 28% of 50s limit. Hard ceiling: 10K.
Related Knowledge:   → K30, K33
Related Pattern:     → P24, P26
Related Decisions:   → D16, D18
Related Tech Assets: → TA19, TA22
Related Incidents:   → I3 (per-batch TX fix), I5 (OOM + ChangeTracker fix)
```

#### Symptoms

**Issue A — CheckPendingAsync wrong table (barcode.cs)**

- `SyncProductBarcodeJda` runs without error but commits 0 records
- Airflow log shows "no data to sync" warning even when barcode staging table has pending rows
- Invisible unless both staging tables are checked: if product staging is empty, barcode sync silently skips entirely

**Issue B — Batch size 20K TX hold near timeout (Airflow log 2026-04-08)**

```
Batch  1: 20000 records, TX hold 39,689ms  ← CRIT (79% of 50s limit)
Batch  2: 20000 records, TX hold 27,975ms
Batch  9: 20000 records, TX hold 35,900ms  ← CRIT
Batch 10: 20000 records, TX hold 30,310ms  ← CRIT threshold
Batch 21: 20000 records, TX hold 27,897ms
```

Heap is stable (~240–267MB, oscillating ±10MB) — ChangeTracker.Clear() and dict.Clear() from I5 fix are working correctly.

#### BotE — TX Hold vs Batch Size

| Batch Size | TX Hold (BotE) | % of MySQL 50s timeout | Risk |
|---|---|---|---|
| 10K (target) | ~14s | 28% | Safe |
| 20K (current) | ~28–40s | 56–80% | CRITICAL |
| 100K (I5 pre-fix) | ~144s | 288% | Fatal |

**BotE formula**: `tx_hold ≈ (batch_size / 10000) × 14s`  
Safety margin rule: tx_hold < timeout × 0.5 → 10K is the ceiling for this workload.

#### Root Cause Detail

**A — Copy-paste bug in barcode.cs:204**

```csharp
// barcode.cs — BEFORE FIX (wrong):
internal async ValueTask<bool> CheckPendingAsync(long lastId, CancellationToken cancellationToken)
{
    return await stagingContext.SpcJdaProductStaging   // ← product table, not barcode!
        .AnyAsync(x => x.Id > lastId, cancellationToken);
}

// barcode.cs — AFTER FIX:
internal async ValueTask<bool> CheckPendingAsync(long lastId, CancellationToken cancellationToken)
{
    return await stagingContext.SpcJdaBarcodeStaging   // ← correct
        .AnyAsync(x => x.Id > lastId, cancellationToken);
}
```

`GetProductStaging()` in barcode.cs correctly queries `SpcJdaBarcodeStaging` — only `CheckPendingAsync` was missed. Both are independent call sites; updating one does not update the other.

#### Fix

**A — Code fix** (`barcode.cs` line 204): 1-line change — `SpcJdaProductStaging` → `SpcJdaBarcodeStaging`

**B — Config fix** (`appsettings.json`): `BatchSize = 10000` (not a code change)

#### Results

| Metric | Before | After |
|---|---|---|
| Barcode sync correctness | Silently skips when product staging empty | Correctly reads barcode staging |
| TX hold per batch | 28–40s (CRIT alert) | ~14s (28% of MySQL limit) |
| Timeout risk | Present (Batch 1: 40s) | Eliminated (10K = 14s) |


### I7: Airflow DAG Local Debug Setup — Multi-Layer Bug Discovery (ds_outbound_order)

```
Title:               Airflow DAG Local Debug Setup — Multi-Layer Bug Discovery
Severity:            Medium
System:              ds_outbound_order ETL Pipeline (Airflow + Python + .NET)
Status:              All bugs fixed 2026-04-21. Debug environment stable.
Date:                2026-04-21
Problem:             Engineer setting up local VS Code debugger for Airflow DAG
                     (ds_inc_outbound_order) encountered 6 layered bugs: 3 environment
                     issues blocking debugpy startup, 3 code bugs in production DAG logic.
Root Cause:          (1) Windows Thai locale (cp874) → KeyboardInterrupt in platform._syscmd_ver()
                     blocking debugpy init. (2) PYTHONUTF8=1 fix breaks pandas import via
                     _path_join in SQLAlchemy 1.4 venv. (3) SQLAlchemy 1.x engine.connect()
                     has no conn.commit() — production code written for 2.x. (4) str.join()
                     on list[int] in xcom_push → TypeError. (5) INSERT/UPDATE silently skipped
                     after .NET job — guard (if not dih_batch_id: return) placed after dotnet
                     ran, spc_batch_id already incremented. (6) Subprocess not killed on
                     AirflowTaskTimeout — .NET process leaks on server.
Lesson Learned:      Airflow DAG code is not independently testable without a stub layer.
                     Local debug environments on Windows with non-English locale need
                     PYTHONIOENCODING=utf-8 (not PYTHONUTF8=1 which breaks venv path handling).
                     SQLAlchemy future=True enables 2.0-style Connection.commit() on 1.4.x
                     without version upgrade. Guard position matters: check input early,
                     before side effects (batch ID increment, subprocess launch).
Prevention:          Use debug runner stub pattern (→ P27, TA23) for all Airflow DAGs.
                     PYTHONIOENCODING=utf-8 in launch.json for Windows Thai locale machines.
                     future=True on create_engine() in debug venv (→ D19).
                     Guard dih_batch_id at top of function, before any side effects.
                     try/except/finally around subprocess.Popen — kill on any exception.
Related Knowledge:   → K34
Related Pattern:     → P27
Related Decisions:   → D19
Related Tech Assets: → TA23
```

#### Symptoms

- debugpy fails to start: `KeyboardInterrupt` at `platform.py:284 _syscmd_ver()` → `cp874.py:22`
- After fix 1: pandas import fails at `_path_join` in frozen importlib
- After fix 2: `AttributeError: 'Connection' object has no attribute 'commit'` at `_insert_chunks` line 75
- After fix 3: `TypeError: sequence item 0: expected str instance, int found` at `xcom_push` for `total_outbound_order_success`
- Production: INSERT into `wms_staging.st_control_table` and UPDATE `st_control_table` not executing after .NET job — intermittent (once)
- Production: .NET subprocess continues running on server after Airflow marks task FAILED/timeout

#### Root Cause — Each Bug

**Bug 1 — Windows cp874 Thai locale blocks debugpy**
```
platform._syscmd_ver() runs subprocess(['ver']) to get Windows version.
Output decoded with system codepage cp874 (Thai). Hangs on read → KeyboardInterrupt.
Fix: PYTHONIOENCODING=utf-8 in launch.json — overrides stdin/stdout/stderr encoding only.
```

**Bug 2 — PYTHONUTF8=1 breaks pandas import**
```
PYTHONUTF8=1 (attempted fix for Bug 1) enables UTF-8 mode globally including
import system path handling. In SQLAlchemy 1.4 venv, cache_from_source() calls
_path_join() which fails. PYTHONUTF8 scope is too broad — breaks venv bootstrap.
Fix: revert to PYTHONIOENCODING=utf-8 (I/O only, does not touch import machinery).
```

**Bug 3 — SQLAlchemy 1.x conn.commit() missing**
```python
# Production code (written for SQLAlchemy 2.x):
with engine.connect() as conn:
    df.to_sql(table, conn, if_exists='append', index=False)
    conn.commit()  # AttributeError on SQLAlchemy 1.4

# Debug fix (no production change):
return create_engine(url, future=True)  # enables 2.0-style Connection on 1.4.x
```

**Bug 4 — str.join() on list[int]**
```python
# BEFORE (production bug):
ti.xcom_push(key='total_outbound_order_success',
             value=str(','.join(total_outbound_order_success)))  # list[int] → TypeError

# AFTER:
ti.xcom_push(key='total_outbound_order_success',
             value=','.join(str(x) for x in total_outbound_order_success))
```

**Bug 5 — Guard placed after side effects (intermittent)**
```
spc_to_wms runs: increment spc_batch_id → launch .NET → read dih_batch_id → if empty: return
When CO has no pending batch, dih_batch_id='' → early return silently skips INSERT/UPDATE
but spc_batch_id was already incremented and .NET already launched = wasted work + wrong state.
Fix: check dih_batch_id at TOP of function before any side effects.
```

**Bug 6 — Subprocess not killed on AirflowTaskTimeout**
```python
# BEFORE: .NET keeps running after Python thread killed by Airflow
result = subprocess.Popen(...)
for line in result.stdout:
    print(line, end="")
exit_code = result.wait()

# AFTER: kill on any exception including AirflowTaskTimeout
try:
    for line in result.stdout: print(line, end="")
    exit_code = result.wait()
    if exit_code != 0: raise Exception(f"exit code {exit_code}")
except Exception:
    if result.poll() is None:
        result.kill(); result.wait()
    raise
finally:
    if result.poll() is None:
        result.kill(); result.wait()
```

#### Architecture Changes Made

1. **Per-CO XCom keys** — replaced comma-joined `dih_batch_id='id1,id2'` with `dih_batch_id_CDS='id1'`, `dih_batch_id_RBS='id2'` — each CO chain gets its own isolated values
2. **Sequential per-CO chain** — `prev_task` pointer pattern generates `extract >> staging_cds >> wms_cds >> staging_rbs >> wms_rbs` from `CO_LIST` loop
3. **execution_timeout** — `TIMEOUT_EXTRACT=1h`, `TIMEOUT_STAGING_SPC=2h`, `TIMEOUT_SPC_WMS=2h` on all operators
4. **MS Teams on_failure_callback** — wired to `default_args` + `DAG.on_failure_callback` via `MsTeamsHook.send_failure()` in all 3 DAGs

#### Results

| Bug | Status | Fix Location |
|---|---|---|
| cp874 locale debugpy crash | Fixed | launch.json: `PYTHONIOENCODING=utf-8` |
| PYTHONUTF8=1 pandas import | Fixed | launch.json: removed PYTHONUTF8 |
| SQLAlchemy conn.commit() | Fixed | debug_runner.py: `future=True` |
| str.join() on int list | Fixed | ds_outbound_order.py: `str(x) for x in` |
| Silent early return guard | Fixed | ds_spc_order_outbound_jda_spc_to_wms.py: guard at top |
| Subprocess not killed | Fixed | Both net DAG files: try/except/finally + kill |

