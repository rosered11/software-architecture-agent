# Code Review: GetSubOrder (target.cs)

🔎 **Mode: Code Review**

**Technologies detected:** EF Core / .NET Data Access, API Endpoint (implied — this is a service method returning data)
**Checklists run:** EF Core, API Endpoint, PostgreSQL (implied via EF Core queries)

---

## --- FINDINGS ---

### 🚨 BLOCK — DB call inside a loop (`GetSubOrderMessage` N+1)

**Line/pattern:** `target.cs:523-531`

```csharp
foreach (SubOrderModel data1 in subOrderModel)
{
    SubOrderMessageViewModel suborder = GetSubOrderMessage(data1.SourceOrderId, data1.SourceSubOrderid);
```

**Risk:** N+1 queries. Each sub-order triggers a separate DB round-trip. At 10 sub-orders = 10 queries; at 100 concurrent requests with 10 sub-orders each = 1,000 sequential DB calls competing for the connection pool. This is the primary timeout driver.

**Fix:** Batch-load all sub-orders in one query:

```csharp
var subOrderIds = subOrderModel.Select(s => s.SourceSubOrderid).ToList();
var allSubOrders = _context.SubOrder
    .AsNoTracking()
    .Where(w => w.SourceOrderId == OrderId && subOrderIds.Contains(w.SourceSubOrderid))
    .Include(/* needed navigations */)
    .ToList();
// Map to ViewModels in memory
```

---

### 🚨 BLOCK — DB call inside a loop (`GetRewardItem` N+1)

**Line/pattern:** `target.cs:69-77`

```csharp
for (int i = 0; i < results.SourceSubOrderIdList.Count; i++)
{
    string sourceSubOrderId1 = results.SourceSubOrderIdList[i] + "";
    GetRewardItem(SourceOrderId, sourceSubOrderId1, ref rewardItemMessageTmp);
```

**Risk:** Same N+1 pattern. One DB query per sub-order ID to fetch reward/promotion items.

**Fix:** Single batch query:

```csharp
var rewardItems = _context.PromotionItemTb
    .AsNoTracking()
    .Where(p => p.SourceOrderId == SourceOrderId
        && results.SourceSubOrderIdList.Contains(p.SourceSubOrderId)
        && !p.IsDelete)
    .ToList();
```

---

### 🚨 BLOCK — `.Entry().Reference().Load()` inside a loop

**Line/pattern:** `target.cs:209`

```csharp
for (int i = 0; i < datalist.Length; i++)
{
    _context.Entry(datalist[i]).Reference(x => x.Amount).Load();
```

**Risk:** Each `.Load()` = 1 DB round-trip. EF Core does NOT batch these. For 20 promotions = 20 extra queries.

**Fix:** Eager-load with `Include()`:

```csharp
OrderPromotionModel[] datalist = _context.OrderPromotion
    .AsNoTracking()
    .Include(op => op.Amount)
    .Where(op => op.SourceOrderId == SourceOrderId)
    .ToArray();
// Remove the .Entry().Reference().Load() line entirely
```

---

### 🚨 BLOCK — `Any()` followed by `FirstOrDefault()` on the same table

**Line/pattern:** `target.cs:483-493` (`GetOrderHeader`)

```csharp
if (_context.Order.Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId)).Any())
{
    return _context.Order.Include(Order => Order.Customer)
        .Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId)).FirstOrDefault();
}
```

**Risk:** Two identical queries where one is enough. Doubles DB load on every call.

**Fix:**

```csharp
return _context.Order
    .AsNoTracking()
    .Include(o => o.Customer)
    .Where(w => w.IsActive == true && w.SourceOrderId.Equals(OrderId))
    .FirstOrDefault(); // returns null if not found — no Any() needed
```

---

### 🚨 BLOCK — `Any()` followed by `Where()` on the same table (x3 occurrences)

**Line/pattern:** `target.cs:499-506` and `target.cs:504-506` (`IsExistOrderReference` — both overloads), and `target.cs:553-555`

```csharp
if (_context.OrderReference.Where(w => w.NewSourceOrderId.Equals(SourceOrderId)).Any())
{
    var OrderRef = _context.OrderReference.Where(w => w.NewSourceOrderId.Equals(SourceOrderId))
        .OrderByDescending(o => o.CreatedDate).FirstOrDefault();
```

**Risk:** Same double-query pattern. Called by `GetOrderHeader`, `GetOrderMessagePayments`, and `GetOrderPromotion` — that's **6 redundant queries** per request.

**Fix:**

```csharp
public bool IsExistOrderReference(string SourceOrderId, ref string RefSourceOrderId)
{
    var orderRef = _context.OrderReference
        .AsNoTracking()
        .Where(w => w.NewSourceOrderId.Equals(SourceOrderId))
        .OrderByDescending(o => o.CreatedDate)
        .FirstOrDefault();
    if (orderRef == null) return false;
    RefSourceOrderId = orderRef.RefSourceOrderId;
    return true;
}
```

---

### 🚨 BLOCK — Same reference resolver called 3x for the same ID in one request

**Line/pattern:** `target.cs:55-57` — `GetOrderHeader`, `GetOrderMessagePayments`, `GetOrderPromotion` each independently call `IsExistOrderReference(SourceOrderId, ...)` with the same `SourceOrderId`.

**Risk:** Per decision-rules: *"Same reference resolver called 2+ times for the same ID in one request -> BLOCK. The coordinator must own that resolution."*

**Fix:** Resolve once at the coordinator level (`GetSubOrder`), pass the resolved ID down:

```csharp
// In GetSubOrder — resolve ONCE
string resolvedOrderId = SourceOrderId;
string refSourceOrderId = string.Empty;
if (IsExistOrderReference(SourceOrderId, ref refSourceOrderId))
    resolvedOrderId = refSourceOrderId;

// Pass resolvedOrderId to all three methods — remove IsExistOrderReference from each
var orderHeader = GetOrderHeader(resolvedOrderId, skipRefCheck: true);
var orderPayments = GetOrderMessagePayments(resolvedOrderId, skipRefCheck: true);
results.OrderPromotion = GetOrderPromotion(resolvedOrderId, skipRefCheck: true);
```

---

### 🚨 BLOCK — Missing `AsNoTracking()` on read-only queries

**Line/pattern:** Every `_context` query in the file — `GetOrderHeader` (line 488), `GetOrderMessagePayments` (line 136), `GetOrderPromotion` (line 194), `GetRewardItem` (line 366), `GetSubOrderMessage` (line 518).

**Risk:** EF change tracker allocates memory and CPU for every tracked entity. This is a pure read operation — tracking overhead is 100% waste. Under concurrency, this amplifies GC pressure (Gen0 churn from proxy objects).

**Fix:** Add `.AsNoTracking()` to every query in this read path.

---

### ⚠️ WARN — No timeout on downstream calls

**Line/pattern:** All DB queries run with no explicit timeout. The method holds `_context` for the entire duration of 30+ sequential queries.

**Risk:** Under high concurrency, slow queries stack up, exhaust the connection pool (default 100 in EF Core), and new requests timeout waiting for a connection — cascading failure.

**Fix:** Add `CommandTimeout` to the DbContext or per-query. Consider: `_context.Database.SetCommandTimeout(5)` (5 seconds) for this read path.

---

### ⚠️ WARN — Exception swallowed with weak logging

**Line/pattern:** `target.cs:44-48`, `target.cs:116-122`

```csharp
catch (Exception ex)
{
    InfoTmp = "" + ex.Message;
    _logger.LogInformation($"OnError ---- {result.MethodnameTmp} ---- {InfoTmp}");
```

**Risk:** (1) `LogInformation` for an error — should be `LogError`. (2) No stack trace logged. (3) No `SourceOrderId` or `SourceSubOrderId` in the log — impossible to trace in production. (4) Inner exceptions in the "All" branch (line 44) are swallowed and processing continues with potentially corrupt state.

**Fix:**

```csharp
_logger.LogError(ex, "GetSubOrder failed | SourceOrderId={OrderId} | SourceSubOrderId={SubOrderId}",
    SourceOrderId, SourceSubOrderId);
```

---

### ⚠️ WARN — No request/trace ID in any log line

**Line/pattern:** All `_logger` calls throughout the file.

**Risk:** Under concurrent load, logs from different requests interleave — impossible to trace a single timeout.

**Fix:** Add correlation ID to all log lines (via middleware or structured logging scope).

---

### 💡 SUGGEST — Synchronous DB calls in async context

**Line/pattern:** All queries use `.FirstOrDefault()`, `.ToArray()`, `.ToList()` — no async variants.

**Why:** Blocks the thread pool under concurrent load. Each in-flight request holds a thread hostage during every DB round-trip.

**Option:** Convert to `async`/`await` with `FirstOrDefaultAsync()`, `ToListAsync()`, etc.

---

### 💡 SUGGEST — `resultAll.Count()` uses LINQ extension instead of `.Count` property

**Line/pattern:** `target.cs:15`, `target.cs:32`

```csharp
for (int i = 0; i < resultAll.Count(); i++)
```

**Why:** `.Count()` on a `List<T>` calls the LINQ extension which is slower than the `.Count` property. Minor, but indicative of LINQ vs. property confusion throughout.

**Option:** Use `.Count` (property) for `List<T>`.

---

## --- SUMMARY ---

| | |
|---|---|
| **Score** | **🚨 BLOCK** |
| Blocks | **7** |
| Warns | **3** |
| Suggests | **2** |

### Query count analysis (worst case, order with N sub-orders)

| Source | Queries |
|--------|---------|
| `IsExistOrderReference` (called 3x, each fires 2 queries) | 6 |
| `GetOrderHeader` (duplicate Any + FirstOrDefault) | 2 |
| `GetOrderMessagePayments` | 1 |
| `GetSubOrderMessage` loop (N sub-orders) | N |
| `GetOrderPromotion` (1 + N lazy loads for Amount) | 1 + N |
| `GetRewardItem` loop (N sub-orders) | N |
| **Total (N=10)** | **~30** |
| **Total (N=50)** | **~110 -> critical per decision-rules** |

Under 100 concurrent requests x 30 queries each = **3,000 DB round-trips** competing for the connection pool -> pool exhaustion -> timeouts.

---

### Architectural lesson

> **The Batch Query pattern is non-negotiable when N is unbounded.** Every DB call inside a loop is a latency multiplier that becomes a connection pool bomb under concurrency. Resolve shared context once at the coordinator level, not independently in each sub-call.

### KOS action

Create:
1. **Incident record** — `GetSubOrder timeout under concurrent load` with root cause: N+1 x 3 + duplicate reference resolution + lazy loading in loop
2. **Knowledge record** — `Coordinator-level reference resolution pattern` — when multiple sibling methods need the same resolved ID, the coordinator must own that resolution
3. **Pattern record** — link to existing `Batch Query` pattern with this as a new real-world example
