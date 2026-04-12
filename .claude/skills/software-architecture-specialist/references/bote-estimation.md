# 📊 Back-of-Envelope Estimation

> Read this file when Back-of-Envelope estimation is triggered (incident latency, system design, architecture decision, hot-path code review, any "will this scale?" question).
> Fill in the template with real numbers before recommending any fix, pattern, or architecture.

---

## Estimation Template

```text
📊 Back-of-Envelope

[1] Traffic
    DAU / concurrent users: ___
    QPS (avg):              DAU × actions/day ÷ 86,400 = ___
    QPS (peak):             avg × 3–5 (burst multiplier) = ___

[2] Data Volume
    Record size:            ___ bytes
    Write rate:             ___ records/day → ___ GB/day
    Retention:              ___ days → total storage = ___

[3] DB / Connection Pool
    Formula: concurrent_requests × queries_per_request × avg_hold_time_s < pool_size
    Concurrency ceiling: pool_size ÷ (queries_per_request × avg_hold_time_s) = ___
    Real example: 100 × 33 × 0.01s = 33s hold → pool exhausted (default pool=100)

[4] Memory
    Memory per request:     ___ KB
    At peak concurrency:    concurrent_requests × memory_per_request = ___ MB
    GC trigger point:       when heap > ___ MB

[5] Latency Budget
    Target P50 / P99:       ___ ms / ___ ms
    Current:                ___ ms → gap = ___
    Breakdown:              DB wait ___ ms | CPU ___ ms | Network ___ ms

[6] Headroom
    Current load:           ___% of ceiling
    Ceiling hit at:         ___ concurrent users / ___ QPS
    Next bottleneck:        DB pool | Memory | CPU | Network
```

---

## Shortcut Formulas

```text
QPS (avg)            = DAU × actions_per_day ÷ 86,400
QPS (peak)           = avg QPS × 3  (conservative burst)
Connection ceiling   = pool_size ÷ (queries × avg_hold_time_s)
Memory at scale      = concurrent_requests × memory_per_request
Storage per year     = write_rate_per_day × 365
Cache hit rate needed= 1 − (DB_capacity ÷ total_read_QPS)
```

---

## Thresholds

```
Response latency:    < 100ms good | 100–300ms acceptable | 300–900ms degraded | > 900ms incident
Query count/request: < 10 healthy | 10–30 monitor | 30–100 investigate | > 100 BLOCK
Connection pool:     formula result > 80% of pool size → act now
GC Gen1 delta > 0   → memory pressure, investigate
GC Gen2 delta > 0   → incident level
```

> 📖 For the full scalability threshold reference table, read `references/kos-decisions.md` (Scalability Thresholds section).

---

## When to Run Each Section

| Trigger | Sections to fill |
|---------|-----------------|
| Latency / timeout incident | [3] Pool + [5] Latency Budget |
| System design or ADR | [1] Traffic + [3] Pool + [4] Memory + [6] Headroom |
| Pattern recommendation | [3] Pool or [4] Memory (whichever the pattern affects) |
| Hot-path code review | [3] Pool (query count × hold time at expected concurrency) |
| "Will this scale?" | All 6 sections |
