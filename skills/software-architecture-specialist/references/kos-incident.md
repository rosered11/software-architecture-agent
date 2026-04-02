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
Status:              In Progress — Phase 5 applied 2026-04-02 (741ms); P3 IMemoryCache pending
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
Related Pattern:     → P7, P16, P17, P18, P19, P20, P22, P27
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

| Metric | Baseline | Target (Phase 3) | Target (Phase 4) | Actual (Phase 4) | Actual (Phase 5) |
|--------|----------|------------------|------------------|------------------|------------------|
| ElapsedMs (P50) | **5,048ms** | < 300ms | < 100ms | **1,117ms (-78%)** | **741ms (-85%)** |
| ElapsedMs (best) | 3,193ms | — | — | **1,080ms (-66%)** | **723ms (-77%)** |
| AllocatedKB per call | 2,668 KB | < 1,500 KB | < 1,500 KB | **~1,980 KB** (+4 ctx) | **~2,020 KB** (+2 ctx) |
| DB query count | ~33 | ~7 | ~7 (parallel) | **~20** | **~20** (2 parallel bulk) |
| Max concurrent (pool) | ~20 | ~200+ | ~400+ | **~400+** | **~400+** |

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
