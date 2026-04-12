**Mode: Pattern Guidance**

## Back-of-Envelope (Mandatory)

### Traffic
- Event rate: 2,000/min = 33.3 QPS avg; peak burst ~100 QPS
- 1 DB query per event = 33–100 DB queries/sec

### DB / Connection Pool
- Pool = 20, p95 = 800ms → actual hold time under load = 800ms
- Concurrent connections at peak: 100 QPS × 0.800s = **80 connections needed vs 20 pool** = **pool exhausted (400% over capacity)**
- A healthy single-row PK lookup takes 5–15ms; 800ms is pure **connection queue wait**

### Root Cause
Pool exhaustion is the primary driver. The 20-connection pool cannot serve 80 simultaneous requests. Connections queue, hold time grows, which increases concurrent connections further — a feedback loop.

---

## Pattern A: Batch Reads (WHERE id = ANY(...))

**When to USE:**
- Kafka consumer reads messages in batch polls (true for all standard Go Kafka consumers)
- All IDs are known before the DB call
- Data correctness per-event is required (no staleness acceptable)

**When NOT to USE:**
- Events have strict serial dependency (each result determines next ID)
- Batch window latency (5–50ms) violates SLA

**BotE Impact:**
- Before: 100 QPS → 100 DB queries/sec → 80 concurrent connections → pool exhausted → 800ms p95
- After (batch of 100): 1 query/sec → 0.015 concurrent connections → p95 drops to ~20ms

**Go implementation:**
```go
msgs := consumer.Poll(ctx, 100)
ids := extractIDs(msgs)
rows, _ := db.QueryContext(ctx, `SELECT id, data FROM items WHERE id = ANY($1)`, pq.Array(ids))
itemMap := buildMap(rows)
for _, msg := range msgs { process(msg, itemMap[extractID(msg)]) }
```

**Trade-offs:** No new infrastructure. Requires small batch window. Error in one query affects batch (handle partial failures).

---

## Pattern B: Redis Caching (Look-Aside)

**When to USE:**
- Same IDs repeat frequently (cache hit rate > 50%)
- Data changes infrequently (reference data, config, user profiles)
- Read frequency > 10x/min per key

**When NOT to USE:**
- IDs are unique per event (transaction IDs, order IDs) → cache hit rate ≈ 0%
- Data requires real-time accuracy (payment status, inventory)
- You haven't measured hit rate yet

**BotE Impact (80% hit rate):**
- Cache hits: 80 QPS → Redis at ~0.5ms → no DB connection used
- Cache misses: 20 QPS → DB at 10ms → 0.2 concurrent connections → pool fine
- Expected p95: ~5ms blended

**BotE Impact (20% hit rate):**
- Adds Redis RTT overhead. Pool still fine but Redis buys little.

---

## Decision Rule

```
Pool = 20, p95 = 800ms → pool is the problem, not the query itself

Step 1: Raise pool to 50–100 immediately (stop-gap)
Step 2: Deploy batch reads — collects IDs from one Kafka poll, fires 1 WHERE IN query
Step 3: Measure ID reuse rate. If same ID appears > 10x/min → add Redis with TTL

IDs unique per event?                  → Batch Reads only (Redis hit rate ~0%)
IDs repeat heavily + data stable?      → Batch Reads + Redis layer on top
Unsure?                                → Batch first, measure, then decide on Redis
```

**Priority order:**
1. Batch reads — deploy now → p95: 800ms → ~20ms
2. Pool = 50–100 — stop-gap while deploying
3. Redis — only after measuring hit rate > 50%

---

**Next Step:** Instrument your Go Kafka consumer to log batch size per poll and ID distribution across batches. If IDs repeat across polls, Redis is justified. If not, batch reads alone will solve it. Deploy batch reads first — guaranteed improvement, zero new infrastructure.
