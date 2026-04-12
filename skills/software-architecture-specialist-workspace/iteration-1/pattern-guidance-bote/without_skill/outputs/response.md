# Architecture Analysis: Redis Caching vs. Batch Reads for PostgreSQL Lookup Latency

**Context:** Go background service, 2,000 Kafka events/min, single PostgreSQL row lookup per event by ID, p95 latency 800ms under load, connection pool = 20.

---

## Diagnosis First

Before choosing a solution, understand the actual bottleneck. At 2,000 events/minute (~33 events/second), a pool of 20 connections should be sufficient in theory — unless queries are slow or connections are held too long.

**Likely root causes ranked by probability:**

1. **Connection pool exhaustion** — 33 queries/sec with a pool of 20 means each query must complete in under ~600ms to avoid queuing. If your PostgreSQL query averages even 100ms, pool slots fill and requests wait. This alone explains 800ms p95.
2. **Missing or stale index on the ID column** — a sequential scan on a large table will spike under concurrent load even if it looks fast in isolation.
3. **PostgreSQL lock contention** — if other processes write to the same rows being read, shared lock waits accumulate.
4. **Network round-trip overhead** — repeated single-row lookups across a network add up when not batched.

---

## Option A: Redis Caching

**Wins when:** The same IDs are looked up repeatedly (high cache hit rate), data is read-heavy and changes infrequently, or you need sub-millisecond latency at scale beyond PostgreSQL.

**Fails when:** Each event carries a unique ID never repeated (cache hit rate ~0%). You pay Redis + PostgreSQL cost every time and add operational complexity for zero gain.

**Cost:** New infrastructure to operate, monitor, and keep synchronized. Cache invalidation logic on all write paths.

**Verdict for your scenario:** Redis is the right choice only if your 2,000 events/minute involve a bounded, recurring set of IDs (e.g., user profiles, product catalog, config records). If the ID space is large and each ID appears roughly once, Redis adds complexity with negligible benefit.

---

## Option B: Batch Reads (DataLoader Pattern)

Instead of issuing one `SELECT WHERE id = $1` per event, accumulate IDs over a short window (5–20ms) and issue a single `SELECT WHERE id = ANY($1::uuid[])`.

**Wins when:** IDs are unique per event, you have bursty concurrent goroutines hitting the DB simultaneously, and you want to reduce pool pressure without adding infrastructure.

**Performance impact:** Reduces 33 queries/sec to 3–5 batched queries/sec at a 10ms window. Each batch uses one connection slot instead of 20+ concurrent single-row queries. Pool exhaustion queuing is eliminated.

**Trade-off:** Adds 5–20ms intentional delay (the batching window). For background Kafka consumers, this rarely matters.

**Go implementation:** Use `github.com/graph-gophers/dataloader` or implement a simple accumulator goroutine that flushes on a timer or batch-size threshold.

---

## Recommendation

**Step 1 — immediate, zero infrastructure:**

1. Increase pool size incrementally (try 40–50) and measure if p95 drops. This costs nothing and confirms whether pool exhaustion is the root cause.
2. Run `EXPLAIN ANALYZE` on the lookup query to verify the ID column has a B-tree index and no sequential scans are happening under load.
3. Implement the DataLoader/batch-read pattern. This directly addresses the structural problem: N concurrent single-row queries against a shared pool.

**Step 2 — only if batch reads are insufficient:**

Add Redis after profiling confirms your ID space is bounded (the same IDs repeat frequently) AND PostgreSQL throughput is the ceiling even with batching and a healthy pool.

In most Go Kafka consumer architectures at 2,000 events/minute, batch reads alone reduce p95 from 800ms to under 50ms without Redis.

---

## Decision Rule

| Condition | Action |
|---|---|
| Cache hit rate > 60% AND staleness acceptable | Add Redis |
| Cache hit rate < 30% OR IDs are mostly unique | Use batch reads |
| Pool exhaustion confirmed as root cause | Increase pool + batch reads first |
| p95 remains > 200ms after batching | Add Redis on top of batching |

---

## Summary

Do not add Redis yet. The 800ms p95 spike is almost certainly connection pool exhaustion from 33 concurrent single-row queries per second competing for 20 connections. Batch reads (DataLoader pattern) directly fix this structural issue: fewer queries, fewer connections held, lower latency — no new infrastructure. Increase pool size as an immediate mitigation, implement batching as the proper fix, and revisit Redis only if profiling shows a high repeat-ID rate.
