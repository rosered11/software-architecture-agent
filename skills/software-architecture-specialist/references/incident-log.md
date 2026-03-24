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

- API response time ~900ms per request
- ~289 DB queries generated per single `GetSubOrder` call
- Latency scaled linearly with number of items in the suborder
- No infrastructure issue — problem was purely in the data access layer

---

### Root Cause

**N+1 query pattern across multiple EF Core lazy loads inside `foreach` loops.**

Three compounding problems were found:

**1. `.Entry().Reference().Load()` inside item loop**
```csharp
// Called once per item — N DB roundtrips
for (int i = 0; i < datalist.Length; i++)
{
    _context.Entry(datalist[i]).Reference(x => x.Amount).Load();
}
```

**2. `.Entry().Collection().Load()` inside item loop**
```csharp
// Each relation = separate DB call per item
foreach (SubOrderItemModel itemModel in subOrderModel.Items)
{
    _context.Entry(itemModel.Amount).Reference(p => p.Normal).Query()
        .Include(i => i.Taxes).Load();

    _context.Entry(itemModel.Amount).Reference(p => p.Paid).Query()
        .Include(i => i.Taxes).Load();

    _context.Entry(itemModel).Collection(p => p.Payments)
        .Query().Include(i => i.Taxes).Load();

    _context.Entry(itemModel).Collection(p => p.Remarks).Load();
    _context.Entry(itemModel).Collection(p => p.SubBarcode).Load();
    _context.Entry(itemModel).Collection(p => p.Promotions).Load();
    _context.Entry(itemModel).Reference(p => p.Promotion).Load();
}
```
With 50 items × 7 relation loads = **350 potential DB calls** from item loop alone.

**3. Redundant `Any()` + `FirstOrDefault()` pattern**
```csharp
// Two queries where one would do
if (_context.Order.Where(w => w.SourceOrderId.Equals(OrderId)).Any())
{
    return _context.Order
        .Include(Order => Order.Customer)
        .Where(w => w.SourceOrderId.Equals(OrderId))
        .FirstOrDefault();
}
```

---

### Fix

**Replace all loop-based lazy loads with batch queries + in-memory dictionary lookup.**

```csharp
// 1. Collect all item IDs upfront
var itemIds = subOrderModel.Items.Select(i => i.Id).ToList();

// 2. Batch load all related entities in one query each
var amountMap = await _context.ItemAmount
    .AsNoTracking()
    .Where(a => itemIds.Contains(a.ItemId))
    .ToDictionaryAsync(a => a.ItemId);

var paymentsMap = await _context.ItemPayments
    .AsNoTracking()
    .Include(p => p.Taxes)
    .Where(p => itemIds.Contains(p.ItemId))
    .GroupBy(p => p.ItemId)
    .ToDictionaryAsync(g => g.Key, g => g.ToList());

// 3. O(1) lookup in loop — zero DB calls
foreach (var itemModel in subOrderModel.Items)
{
    if (amountMap.TryGetValue(itemModel.Id, out var amount))
        orderItemViewModel.Amount = MapAmount(amount);

    if (paymentsMap.TryGetValue(itemModel.Id, out var payments))
        orderItemViewModel.Payments = MapPayments(payments);
}
```

**Fix the redundant Any() + FirstOrDefault() pattern:**
```csharp
// Before: 2 queries
if (_context.Order.Where(...).Any())
    return _context.Order.Where(...).FirstOrDefault();

// After: 1 query
return _context.Order
    .AsNoTracking()
    .Include(o => o.Customer)
    .Where(w => w.IsActive && w.SourceOrderId == orderId)
    .FirstOrDefault();
```

**Add `AsNoTracking()` to all read-only queries:**
```csharp
_context.SubOrder
    .AsNoTracking()
    .AsSplitQuery()
    .Include(s => s.Items)
        .ThenInclude(i => i.Amount)
    ...
```

---

### Results

| Metric | Before | After |
|--------|--------|-------|
| Response time | ~900ms | ~40ms |
| DB queries per request | ~289 | ~10 |
| Improvement | — | **22× faster** |

---

### Prevention

**Architecture review checklist — add to code review process:**

```
[ ] Any DB call inside a foreach or for loop? → Flag immediately
[ ] Any .Entry().Reference().Load() or .Entry().Collection().Load()? → Replace with batch
[ ] Any Any() followed by FirstOrDefault() on same table? → Collapse to one query
[ ] All GET endpoint queries using AsNoTracking()? → Required
[ ] Query count profiled before merging? → Use EF Core logging or MiniProfiler
```

---

### Lesson Learned

> **Latency ≈ number of DB queries × average roundtrip time**

EF Core lazy loading is invisible at low data volumes and catastrophic at scale. The problem was written in 2020 and undetected until production load exposed it. The fix is not hard — the discipline to catch it early is.

**Architectural rule extracted:**
- Never trust EF Core to batch automatically — it doesn't
- Every `.Load()` inside a loop is a performance bug waiting for enough data to detonate

---

### KOS Links

| Type | Record |
|------|--------|
| **Knowledge** | N+1 Query Problem, Batch Query Pattern, EF Core Best Practices |
| **Pattern** | Avoid N+1 Query → see `references/patterns.md` #1 |
| **Decision** | Use Batch IN Query instead of Eager Load in GetSubOrder |
| **Tech Assets** | Batch IN query snippet, Dictionary O(1) lookup snippet, AsNoTracking config snippet |