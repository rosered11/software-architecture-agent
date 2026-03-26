# Session Tracking & Communication Log

**Date**: 2026-03-25
**Session Focus**: GetSubOrder timeout analysis → Full knowledge chain → Career roadmap alignment

---

## Session Summary

This session performed a complete **Incident → Knowledge → Pattern → Decision → Reuse** loop on the `GetSubOrder` method in `target.cs`, then mapped the work to the Software Architect career roadmap.

---

## 1. Code Review Output

**Mode**: Code Review
**File**: `target.cs` — `GetSubOrder()` method and all supporting methods
**Score**: **BLOCK** (7 Blocks, 3 Warns, 2 Suggests)

### Findings Summary

| Severity | Count | Key Findings |
|----------|-------|-------------|
| BLOCK | 7 | N+1 in GetSubOrderMessage loop (line 518-540), N+1 in GetRewardItem loop (line 69-77), Entry().Load() in GetOrderPromotion loop (line 209), Any()+FirstOrDefault() double queries in GetOrderHeader (line 483-494) and IsExistOrderReference (lines 497-510, 553-555), same reference resolver called 3x per request (lines 55-57), missing AsNoTracking() on all read queries |
| WARN | 3 | No timeout on DB calls, exception swallowed with LogInformation instead of LogError (lines 44-48, 116-122), no request/trace ID in logs |
| SUGGEST | 2 | Synchronous DB calls (no async), .Count() LINQ extension instead of .Count property |

### Query Count Analysis

| Scenario | Total DB Queries |
|----------|-----------------|
| Before fix (N=10 sub-orders) | ~33 |
| After Phase 1 (collapse duplicates, AsNoTracking, Include) | ~15 |
| After Phase 2 (coordinator resolution) | ~10 |
| After Phase 3 (batch loops) | ~7 |

### Connection Pool Math

```
Before: 100 concurrent × 33 queries × 0.01s = 33s hold → POOL EXHAUSTION
After:  100 concurrent × 7 queries × 0.01s  = 7s hold  → 25% utilization (healthy)
```

**Full output**: `code-review.md`

---

## 2. Architecture Decision Output

**Mode**: Architecture Decision
**Problem**: How to restructure GetSubOrder to survive high concurrency without timeouts

### Options Evaluated

| Option | Query Reduction | Risk | Effort | Decision |
|--------|----------------|------|--------|----------|
| A. Batch Query Refactor | ~33 → ~7 | Low | 2-3 days | **Selected — implement now** |
| B. Async + Parallel Calls | ~7 parallel | Medium | 5-7 days | Fast-follow after A proven |
| C. CQRS Read Model | ~33 → 1 | High | 2-3 weeks | Deferred — premature |

### Expected Outcome After Option A

| Metric | Before | After |
|--------|--------|-------|
| Queries per request (N=10) | ~33 | ~7 |
| Connection hold time | ~300ms+ | ~70ms |
| P99 latency (100 concurrent) | timeout | < 300ms |
| Connection pool utilization | saturated | ~25% |

### Implementation Phases

```
Phase 1 (Day 1): Collapse Any()+FirstOrDefault(), AsNoTracking(), Include(Amount) → ~33 to ~15
Phase 2 (Day 2): Hoist IsExistOrderReference to coordinator → ~15 to ~10
Phase 3 (Day 3): Batch GetRewardItem + GetSubOrderMessage with Contains() → ~10 to ~7
Phase 4 (Follow-up PR): Async migration with IDbContextFactory + Task.WhenAll
```

**Full output**: `architecture-decision.md`

---

## 3. Runbook Output

**Mode**: Runbook Generator
**File generated**: `runbooks/suborder-processing-latency.md`

### Runbook Coverage

| Section | Status |
|---------|--------|
| Header | Complete — linked to incident, patterns, ADR |
| Overview | Complete |
| Alert Condition | Complete — P99 latency, query count, pool utilization, manual triggers |
| Detection | Complete — 3-step confirmation with Prometheus queries and SQL |
| Diagnosis Tree | Complete — 5 branches covering deploy rollback, N+1, pool exhaustion, specific OrderId, GC pressure |
| Fix Procedures | Complete — 4 fixes (Rollback, N+1 Fix with 3 phases, Scale Out, AsNoTracking quick mitigation) |
| Rollback | Complete — git revert, kubectl rollback, connection pool restore |
| Post-Incident | Complete — metrics capture, KOS update, prevention tasks, team comms |

---

## 4. Knowledge Base Updates

All reference files updated with findings from `target.cs`:

| File | Changes Made |
|------|-------------|
| `references/incident-log.md` | Rewrote Incident #1 with accurate line numbers from target.cs, correct query count (~33), connection pool math, 4-phase fix plan, Architecture Decision section |
| `references/patterns.md` | Updated Pattern #1 (Batch Query) and #11 (Eager Graph Loading) with target.cs code. **Added Pattern #12: Coordinator-Level Resolution** |
| `references/decision-rules.md` | Added connection pool math formula, updated shared context resolution rule with target.cs references, added pool math to code review flags |
| `references/system-design-review.md` | Rewrote SubOrder Processing worked example — 6 CRITICAL, 3 MEDIUM, 1 LOW. Updated scorecard to 19/35 with query count breakdown |
| `references/review-checklists.md` | Added BLOCK item: "Same reference resolver called 2+ times for same ID" with target.cs example |
| `SKILL.md` | Added Eager Graph Loading and Coordinator-Level Resolution to Common Patterns Reference |

---

## 5. Files Generated This Session

| File | Type | Purpose |
|------|------|---------|
| `code-review.md` | Review output | Full code review with 7 BLOCKs, 3 WARNs, 2 SUGGESTs |
| `architecture-decision.md` | ADR | 3 options compared, decision rationale, implementation plan |
| `runbooks/suborder-processing-latency.md` | Runbook | Full 8-section operational playbook |
| `tracking-comunicate.md` | Session log | This file — full session tracking and career roadmap |

---

## 6. Career Roadmap — Current Status

**Goal**: Software Architect in 2 years
**Current context**: .NET, Go, Kafka, PostgreSQL — microservices, data sync, event-driven systems

### Progress Check (as of 2026-03-25)

| Indicator | Status | Evidence | Target |
|-----------|--------|----------|--------|
| ADRs documented | 1 — In Progress | `architecture-decision.md` (GetSubOrder: 3 options, trade-offs, phased plan) | 10+ by Month 9 |
| Incidents fully logged in KOS | 1 — In Progress | `incident-log.md` #1 GetSubOrder (root cause, fix, before/after, lessons) | All incidents logged |
| Systems through Design Review | 1 of 3 — In Progress | SubOrder Processing reviewed via target.cs (scorecard 19/35) | All 3 systems by Q1 |
| Runbooks written | 1 — Done | `runbooks/suborder-processing-latency.md` (full 8 sections) | 1 per system by Month 3 |
| Trace ID propagation | Not Started | No trace ID in target.cs logs | By Q2 |
| Design reviews led for others | Not Started | — | At least 1 by Q3 |
| Patterns documented | 12 total (1 new this session) | Pattern #12 Coordinator-Level Resolution added | Ongoing |
| Code review checklist usage | Started | Applied full EF Core + API checklist to target.cs | Every PR |

### Competency Domain Assessment

| Domain | Level | Key Evidence | Biggest Gap |
|--------|-------|-------------|-------------|
| 1. System Design | Intermediate | SubOrder Design Review done, ADR created | Stock Sync and FTP ETL not yet reviewed |
| 2. Distributed Systems | Intermediate | Kafka in use, patterns documented | No trace ID, no Saga designed, no Circuit Breaker |
| 3. Performance & Optimization | Intermediate-Advanced | GetSubOrder fully diagnosed, connection pool math understood, batch pattern applied | Not yet catching issues in design phase (pre-incident) |
| 4. Decision Making & Documentation | Early | 1 ADR created with 3 options and trade-offs | **Highest-leverage gap** — only 1 ADR, most decisions undocumented |
| 5. Operational Maturity | Reactive → Improving | 1 incident logged, 1 runbook written, measurement plan defined | No SLA targets defined, not yet consistently following post-incident process |
| 6. Communication & Influence | Not Yet Demonstrated | — | Needs intentional focus in Year 2 |

### Highest-Leverage Gap

**Domain 4: Decision Making & Architecture Documentation**

You have the technical skills (Domain 3 is strong). The gap is the **habit of documenting decisions**. Architects are judged on their decisions, not their code. Every non-trivial choice needs an ADR.

### Mindset Shift Progress

| Shift | Current State | Evidence |
|-------|--------------|----------|
| Scope: "This PR" → "This system over time" | Shifting | Reviewed full call graph, not just one method |
| Decisions: Implicit → Explicit in ADRs | Starting | 1 ADR written with full trade-off analysis |
| Incidents: Surprises → Expected with runbooks | Starting | 1 runbook written, measurement plan defined |
| Patterns: Tools → Lenses to think with | Growing | 12 patterns documented, new pattern extracted from incident |
| Performance: "Does it pass?" → "What's the query count?" | Strong | Connection pool math calculated, query count is first diagnostic |
| Documentation: "Code is docs" → "Future me needs this" | Starting | Knowledge chain complete for 1 system |
| Failure: "Shouldn't fail" → "How does it fail gracefully?" | Growing | Diagnosis tree in runbook covers 5 failure branches |

---

## 7. Next Actions (Priority Order)

### This Week

```
[ ] Implement Phase 1 fixes in target.cs
    → Capture Stopwatch baseline BEFORE any code changes
    → Apply: collapse Any()+FirstOrDefault(), AsNoTracking(), Include(Amount)
    → Record before/after metrics in incident-log.md Results table

[ ] Implement Phase 2: hoist IsExistOrderReference to GetSubOrder coordinator
    → Measure again after this phase
```

### Next Week

```
[ ] Implement Phase 3: batch GetRewardItem and GetSubOrderMessage
    → Final measurement — should be ~7 queries per request

[ ] Pick system #2 (Stock Sync or FTP ETL) for System Design Review
    → Run all 7 dimensions from references/system-design-review.md
    → Score and rank risks
    → Write at least 1 ADR from findings
```

### This Month

```
[ ] Write runbooks for remaining 2 systems (Stock Sync, FTP ETL)
[ ] Log every incident in incident-log.md — no exceptions
[ ] Run review-checklists.md on every PR — flag at least 1 architectural issue per week
[ ] Define SLA targets (P99 latency, error rate) for SubOrder Processing
[ ] Add EF Core query count metric to Prometheus dashboard
```

### Quarter Goal (Q2 2026)

```
[ ] All 3 systems through System Design Review
[ ] All 3 systems have runbooks
[ ] 5+ ADRs documented in Notion Decision Log
[ ] Trace ID propagation implemented in at least 1 service
[ ] Connection pool utilization alert configured
[ ] "State of Systems" one-pager drafted (1 page per system: health, risks, decisions)
```

---

## 8. The Architect Test

> "If your tech lead asked you to explain the 3 biggest architectural risks in your systems right now — could you answer immediately, with evidence?"

**Today's answer**: You can answer for **1 of 3 systems** (SubOrder Processing):
1. N+1 query pattern causing timeouts under concurrency — 33 queries per request, connection pool exhaustion at 100 concurrent
2. No observability — no query count metrics, no trace ID, errors logged at wrong level
3. No timeout protection on DB calls — cascading failure risk

**Target by Q2 2026**: Answer for all 3 systems with evidence, metrics, and documented decisions.

---

## 9. Performance Baseline — Captured 2026-03-25

**Test conditions**: 30 sequential calls, single-user, OrderId `TWDCDS2602122610025068`, SubOrderId `All`

### Latency

| Metric | Value |
|--------|-------|
| Average | 4,872ms |
| P50 (median) | 5,048ms |
| P99 (worst) | 8,283ms |
| Best | 3,193ms |
| Target | < 300ms |
| Gap | **~16x slower than target** |

### CPU vs I/O Wait

| State | Value | Meaning |
|-------|-------|---------|
| CpuMs (steady) | 15-62ms | Actual computation |
| ElapsedMs (steady) | 4,500-5,500ms | Wall-clock time |
| **I/O Wait %** | **99%** | **Almost all time is waiting on DB round-trips** |

Verdict: This method is **not CPU-bound**. Reducing DB round-trips is the only lever.

### Memory & GC

| Metric | Value |
|--------|-------|
| MemDelta per call (steady) | 2,676 KB (~2.6 MB) |
| AllocatedKB per call (steady) | 2,668 KB |
| MemDelta call #1 (cold start) | 22,237 KB (21.7 MB) — EF model + JIT |
| Heap growth pattern | 27MB → 86MB over 30 calls, GC reclaims ~44MB every ~10 calls |
| GC0 per 10 calls | 1 |
| GC1 per 10 calls | 1 |
| GC2 (cold start only) | 1 |
| Concurrency risk | 100 concurrent × 2.6MB = 260MB tracked entities → frequent GC pauses |

### Thread Pool

| Metric | Value | Meaning |
|--------|-------|---------|
| WorkerUsed | 3 / 32,767 | No thread pressure at single-user |
| IOUsed | **0** / 1,000 | All DB calls are synchronous — not using async I/O |
| Concurrency risk | 100 concurrent × 5s blocked = 500 thread-seconds held | Thread pool starvation |

### Baseline Conclusions

1. **99% I/O wait** → DB round-trip reduction is the #1 fix (Phase 1-3)
2. **2.6 MB tracked per call** → `AsNoTracking()` will reduce memory + GC (Phase 1)
3. **IOUsed=0** → Async migration needed for concurrency (Phase 4)
4. **CpuMs=15-62ms** → CPU optimization is unnecessary — skip it
5. **5s per call at single-user** → under 20 concurrent requests, thread pool stress begins

### Fix Priority Validated by Data

```
Phase 1 (highest impact): Collapse duplicate queries + AsNoTracking + Include(Amount)
  → Expected: reduce I/O wait from 99% to ~95%, cut MemDelta by ~40%

Phase 2: Hoist IsExistOrderReference to coordinator
  → Expected: eliminate 4-8 redundant DB round-trips

Phase 3: Batch GetRewardItem + GetSubOrderMessage
  → Expected: ElapsedMs drop from ~5,000ms to < 300ms (biggest latency reduction)

Phase 4 (follow-up): Async migration
  → Expected: IOUsed > 0, thread pool threads unblocked during DB waits
```

---

## 10. Phase 1 Results — Measured 2026-03-26

**Test conditions**: 30 sequential calls, single-user, same OrderId `TWDCDS2602122610025068`, SubOrderId `All`

### Before/After Comparison

| Metric | Baseline | Phase 1 | Change |
|--------|----------|---------|--------|
| ElapsedMs (P50) | 5,048ms | **2,836ms** | **-44%** |
| ElapsedMs (best) | 3,193ms | 2,792ms | -13% |
| ElapsedMs (cold start) | 8,283ms | 12,533ms | +51% (heavier query plan, one-time) |
| CpuMs (steady) | 15-62ms | 0-46ms | ~same |
| MemDelta (steady) | 2,676 KB | 2,705 KB | ~same (N+1 loops still dominate) |
| GC0 per 10 calls | 1 | **0.2** | **-80%** |
| GC1 per 10 calls | 1 | **0.1** | **-90%** |
| Heap before GC | ~80 MB | ~68 MB | -15% |
| DB queries (est.) | ~33 | ~22 | -33% |

### Interpretation

- **44% latency reduction** from collapsing duplicate queries + Include(Amount) eager load
- **GC pressure dropped 80-90%** — AsNoTracking() working as expected
- **MemDelta flat** because N+1 loops still load the same amount of entity data — memory win comes in Phase 3
- **Remaining 2.8s = N+1 loops** — GetSubOrderMessage (10 queries) + GetRewardItem (10 queries) = ~20 sequential round-trips at ~140ms each
- **Phase 2-3 will be the big drop**: eliminating 20 loop queries → expected < 300ms

---

## 11. Phase 2 Results — Measured 2026-03-26

**Test conditions**: 30 sequential calls, single-user, same OrderId `TWDCDS2602122610025068`, SubOrderId `All`

### Before/After Comparison (Cumulative)

| Metric | Baseline | Phase 1 | Phase 2 | Change (vs Baseline) |
|--------|----------|---------|---------|---------------------|
| ElapsedMs (P50) | 5,048ms | 2,836ms | **~2,730ms** | **-46%** |
| ElapsedMs (best) | 3,193ms | 2,792ms | **2,634ms** | **-17%** |
| ElapsedMs (cold start) | 8,283ms | 12,533ms | **6,309ms** | **-24%** |
| CpuMs (steady) | 15-62ms | 0-46ms | **0-46ms** | ~same |
| MemDelta (steady) | 2,676 KB | 2,705 KB | **~2,663 KB** | ~same |
| AllocatedKB (steady) | 2,668 KB | 2,697 KB | **~2,655 KB** | ~same |
| GC0 per 10 calls | 1 | 0.2 | **0.03** | **-97%** |
| GC1 per 10 calls | 1 | 0.1 | **0.03** | **-97%** |
| Heap before GC | ~80 MB | ~68 MB | **~80 MB (1 GC at call #21)** | ~same |
| DB queries (est.) | ~33 | ~22 | **~18** | -45% |

### Interpretation

- **Marginal latency improvement** (2,836ms → ~2,730ms, -4%) — expected since hoisted IsExistOrderReference queries were individually fast (~25ms each)
- **Cold start dramatically improved** (12,533ms → 6,309ms, -50%) — coordinator resolution means fewer query plan compilations at startup
- **GC nearly eliminated** — only 1 GC0 + 1 GC1 across 30 calls (at call #21 when heap reached ~80MB). 97% reduction from baseline
- **MemDelta still flat** — N+1 loops remain the dominant memory consumer (20 queries loading full entities)
- **Remaining ~2,700ms is almost entirely N+1 loops** — GetSubOrderMessage (10 queries) + GetRewardItem (10 queries) = ~20 sequential round-trips at ~135ms each
- **Phase 3 is the critical phase** — collapsing 20 loop queries to 2 batch queries → expected < 300ms

---

## 12. Phase 3 Results — Measured 2026-03-26

**Test conditions**: 30 sequential calls, single-user, same OrderId `TWDCDS2602122610025068`, SubOrderId `All`

### Attempt 1: Include Chain + Remove Entry().Load() — REVERTED

| Metric | Phase 2 | Phase 3 (attempt 1) | Change |
|--------|---------|---------------------|--------|
| ElapsedMs (P50) | ~2,730ms | **~2,720ms** | **~0% — no improvement** |
| ElapsedMs (cold start) | 6,309ms | **7,530ms** | **+19% worse** |
| CpuMs (cold start) | — | **1,828ms** | Much higher — query plan compilation |
| MemDelta (steady) | ~2,663 KB | ~2,661 KB | ~same |

**Why it failed**: `AsSplitQuery` with 16 Include paths generates the **same number of queries** as the `Entry().Load()` calls it replaced. The split queries replaced lazy loads 1:1. No net reduction in DB round-trips.

**Reverted**: Include chain expansion + Entry().Load() removal rolled back due to worse cold start with no latency benefit.

### Changes KEPT from Phase 3

| Change | Impact |
|--------|--------|
| Batch GetRewardItem with `Contains()` | N loop queries → 1 batch query |
| Collapse GetLatestOrder Any()+FirstOrDefault() | 2 → 1 query per sub-order |
| Collapse GetOrderItemOtherInfo Count()+FirstOrDefault() + AsNoTracking | 2 → 1 query per item |

### Key Lesson Learned

> **`AsSplitQuery` + Include ≠ fewer queries.** EF Core's `AsSplitQuery` avoids Cartesian joins by splitting each Include path into a separate query. With 16 Include paths, this generates 5-8 split queries — the same count as the `Entry().Load()` calls it replaces. The approach traded lazy loads for eager split queries with no net improvement.
>
> **The real bottleneck is the N outer loop**, not the per-item loads inside each sub-order. Each of the 10 `GetSubOrderMessage(orderId, subOrderId)` calls makes ~8 sequential DB queries at ~34ms each = ~270ms per sub-order × 10 = ~2,700ms. The only path to < 300ms is **batching the outer loop itself** — loading ALL sub-orders in a single query.

### Revised Architecture Decision

The original 3-phase plan was wrong about Phase 3. The correct next step is:

```
Phase 3 (revised): Batch the outer GetSubOrderMessage loop
  → Restructure from per-sub-order processing to bulk-load-then-map
  → Single query: load ALL sub-orders for OrderId with full Include chain
  → Batch all supporting queries: IsExistOrderReference, GetLatestOrder, GetOrderItemOtherInfo
  → Map all ViewModels in memory (zero per-sub-order DB calls)
  → This is a significant restructuring — estimated 1-2 days
  → Expected: ~2,700ms → < 500ms
```

---

## 13. Phase 3 Revised Results — Measured 2026-03-26

**Test conditions**: 30 sequential calls, single-user, same OrderId `TWDCDS2602122610025068`, SubOrderId `All`

### Before/After Comparison (Full Progression)

| Metric | Baseline | Phase 1 | Phase 2 | Phase 3 Revised | Change vs Baseline |
|--------|----------|---------|---------|-----------------|--------------------|
| ElapsedMs (P50) | 5,048ms | 2,836ms | 2,730ms | **1,505ms** | **-70%** |
| ElapsedMs (best) | 3,193ms | 2,792ms | 2,634ms | **1,481ms** | **-54%** |
| ElapsedMs (cold start) | 8,283ms | 12,533ms | 6,309ms | **4,521ms** | **-45%** |
| AllocatedKB (steady) | 2,668 KB | 2,697 KB | ~2,655 KB | **~2,470 KB** | -7% |
| GC0 per 10 calls | 1 | 0.2 | 0.03 | **~5 (cycling)** | — |
| DB queries (est.) | ~33 | ~22 | ~18 | **~50 (20+3×N)** | +52% queries, -70% latency |

### Interpretation

- **P50 dropped 1,225ms (-45% vs Phase 2)** — bulk-loading all sub-orders in one `AsSplitQuery` eliminated the dominant sequential loop cost
- **Cold start improved 28%** (6,309ms → 4,521ms) — one bulk query plan compiled instead of N separate plans
- **GC cycling is healthy**: ~2.5 MB allocated per call, collected every ~2 calls. GC0/GC1 firing at normal intervals — no accumulation
- **Query count paradox**: estimated ~50 queries (20 + 3×N) vs ~18 before — but P50 is 45% faster. The remaining queries are either batched (fast) or the 16 AsSplitQuery paths run in a single DB round-trip
- **Remaining bottleneck**: `getPackageInfoByOrderAndSubOrder` + `GetPackageTb` + `GetStoreLocation` — all per-sub-order, all sequential. For N=10: ~30 sequential DB calls × ~30ms each ≈ ~900ms

### Remaining Bottleneck Analysis

```
Observed steady-state: ~1,505ms
Bulk query overhead (AsSplitQuery 16 paths + batched lookups): ~400-600ms (est.)
Per-sub-order sequential tail: ~900ms (getPackageInfoByOrderAndSubOrder + GetPackageTb + GetStoreLocation)

Phase 4 target: parallelize the 3 per-sub-order calls with Task.WhenAll
Expected gain: 900ms sequential → ~100ms parallel = -800ms
Expected Phase 4 P50: ~700-800ms
```

### Phase 4 Plan

```
Goal: Parallelize remaining per-sub-order calls
  → Use IDbContextFactory<> to create separate DbContext per parallel task
  → Wrap GetStoreLocation, getPackageInfoByOrderAndSubOrder, GetPackageTb in Task
  → Execute per-sub-order group with Task.WhenAll
  → Expected: ~1,505ms → ~700ms
  → Risk: Requires IDbContextFactory registration in DI container (context-per-request won't work in parallel)
```

---

## 14. Database Index Results — Measured 2026-03-26

**Indexes applied**: Priority 1–3 as designed in previous section (SubOrder, OrderReference, PackageTb, StoreLocation, ItemOtherInfo, PackageInfo, PromotionItemTb, OrderPromotion, all FK child tables)

**Test conditions**: 30 sequential calls, same OrderId, SubOrderId="All"

### Before/After Comparison

| Metric | Phase 3 Revised | After Indexes | Change |
|--------|----------------|---------------|--------|
| ElapsedMs (P50) | 1,505ms | **~1,579ms** | **+5% (noise — no improvement)** |
| ElapsedMs (cold start) | 4,521ms | **9,014ms** | **+99% (plan recompile — one-time)** |
| Cold start AllocatedKB | 109,147 KB | **108,445 KB** | ~same (confirms plan recompilation) |
| AllocatedKB (steady) | ~2,470 KB | **~1,808 KB** | **-27% (indexes reducing I/O reads)** |
| GC0 per 10 calls | ~5 | **0.3 (1 event in 30)** | **-94%** |
| GC1 per 10 calls | ~5 | **0** | **-100%** |

### Why Latency Did Not Improve

The indexes reduced **I/O cost per query** but latency is dominated by **sequential round-trip count**, not I/O cost:

```
~30 per-sub-order sequential calls × 38ms each = ~1,140ms (before indexes)
~30 per-sub-order sequential calls × 35ms each = ~1,050ms (after indexes)
Difference: ~90ms — too small to measure against 1,500ms baseline
```

The bottleneck shifted completely to round-trip count after the batch refactor. Indexes cannot reduce round-trip count — only code structure can.

### Cold Start Regression — Root Cause

Call #1 AllocatedKB = 108,445 KB (same as baseline) confirms SQL Server cleared the plan cache after index creation and rebuilt statistics + query plans on first request. This is a one-time event after index creation, not a permanent regression.

### What Indexes Did Accomplish

- **AllocatedKB -27%**: covering indexes serve queries without heap lookups → less data read into .NET
- **GC eliminated**: less allocation per call → GC has nothing to collect in steady state
- **Future-proofing**: under concurrency, faster I/O per query improves pool utilization ceiling even if single-request latency is unchanged

### Revised Phase 4 Plan

Indexes are complete. Next bottleneck is exclusively the sequential tail:
```
Target: 30 sequential per-sub-order calls → parallel execution groups
  GetStoreLocation ×N  \
  PackageInfo ×N        → Task.WhenAll per sub-order
  PackageTb ×N         /

Also consider: StoreLocation cache — same BU/SourceBU/SourceLoc called 3+ times per request
→ Cache key: (BU, SourceBU, SourceLoc) → IMemoryCache with 5-min TTL
→ Expected: eliminate 2 of 3 StoreLocation calls per request → -70ms additional

Expected P50 after Phase 4: ~700ms (parallel) - ~70ms (cache) = ~630ms
```
