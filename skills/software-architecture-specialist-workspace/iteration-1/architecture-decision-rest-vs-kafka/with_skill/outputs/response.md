# Architecture Decision: Synchronous REST vs Kafka Events for Order → Fulfillment Communication

**Mode: Architecture Decision**

---

## Context

- **Services**: .NET Order Service (producer) → Go Fulfillment Service (consumer)
- **Current load**: ~200 orders/minute (3.3 orders/second)
- **Expected load in 6 months**: ~2,000 orders/minute (33.3 orders/second)
- **Fulfillment processing time**: 2–5 seconds per order
- **Communication type**: cross-service, triggering an action (order placed → fulfillment starts)

---

## Back-of-Envelope (BotE)

### Traffic

| Metric | Today | In 6 Months |
|--------|-------|-------------|
| Orders/minute | 200 | 2,000 |
| Orders/second (QPS) | 3.3 | 33.3 |
| Peak burst (3x) | ~10 QPS | ~100 QPS |

### Option A — Synchronous REST: Connection Hold Time

Concurrent in-flight at peak (6 months):
```
Concurrent requests = QPS × hold_time_s = 33.3 × 5s = ~167 held connections
```

.NET HttpClient default pool (MaxConnectionsPerServer = 10):
```
Pool saturates at = 10 ÷ 5s = 2 QPS → already exhausted at today's volume
```

Any fulfillment slowdown cascades back to the Order Service — order acceptance fails.

### Option B — Kafka Events

```
Required consumers = QPS × avg_processing = 33.3 × 3.5s = ~117 goroutines
4 Go instances × 30 goroutines = 120 → sufficient at 6-month volume

Storage: 2,000/min × 1440min × 2KB = ~5.8 GB/day → 7-day retention = ~40 GB (negligible)
Publish latency: <5ms — order acceptance is off the fulfillment critical path
```

---

## Decision

**Choose Kafka Events with Transactional Outbox.**

### Reasoning

1. **Trigger, not query**: The Order Service triggers an action; it does not need fulfillment data to respond to the customer. (Rule: "Caller just needs to trigger an action → event (Kafka)")

2. **Producer faster than consumer**: Fulfillment takes 2–5s per order. At 33 QPS, REST requires 167 simultaneous held connections — collapses on any slowdown. (Rule: "Producer faster than consumer → queue")

3. **REST fails the BotE test**: Connection pool saturation occurs at ~2 QPS with default settings.

4. **Eventual consistency is acceptable**: Orders can be accepted before fulfillment completes.

5. **Outbox is mandatory**: Order events are critical business data. (Rule: "DB write + event publish must both succeed or both fail → Outbox required")

---

## Architecture

```
[.NET Order Service]
  │
  ├─ DB Transaction:
  │   ├─ INSERT INTO orders (...)
  │   └─ INSERT INTO outbox_events (event_type='OrderCreated', payload=...)
  │
  └─ Outbox Relay (background worker / CDC via Debezium)
       │
       ▼
   [Kafka: orders.created]   ← partition key: order_id
       │
       ├─ [Go Fulfillment Consumer — instance 1]
       ├─ [Go Fulfillment Consumer — instance 2]
       └─ [Go Fulfillment Consumer — instance N]
            │
            ├─ Process fulfillment (2–5s)
            ├─ On permanent error → orders.created.DLQ
            └─ On transient error → retry (1s / 4s / 16s) → DLQ after 3x
```

### Partition Strategy
- **Key**: `order_id` — guarantees per-order event ordering
- **Launch**: 4 partitions (comfortable at 33 QPS)
- **6 months**: 8–12 partitions (scale as lag grows)

---

## Expected Outcome

| Metric | REST | Kafka + Outbox |
|--------|------|---------------|
| Order acceptance latency | 2–5s | <50ms |
| Max sustainable QPS | ~2 QPS (default pool) | >1,000 QPS |
| Fulfillment downtime | Order Service errors (cascade) | Orders queue, clear on recovery |
| 10x spike | Pool exhaustion → 503s | Lag increases, self-heals |
| Retry safety | Duplicate risk | Safe with DLQ + idempotency key |

---

## Watch Out For

1. **Outbox relay delay**: Use CDC (Debezium + PostgreSQL WAL) to reduce delay from seconds to milliseconds vs. polling relay.
2. **Consumer idempotency is mandatory**: Kafka is at-least-once. Implement a `fulfilled_orders` deduplication table with UNIQUE `order_id` constraint.
3. **DLQ alerting**: Alert if DLQ depth > 0 for 5 minutes. A growing DLQ is a systemic bug.
4. **Partition count is not easily changed**: Start with 4–8 at launch, not 1.
5. **API breaking change**: Response changes from synchronous fulfillment result to `202 Accepted`. Plan API versioning.
6. **Trace ID propagation**: Inject HTTP trace ID into Kafka message headers; Go consumer must extract and log it.

---

**References:** P12 (DLQ), P14 (Transactional Outbox), P15 (Idempotency Key), D4 (Distributed Transaction Strategy).

**Next Step:** Implement the Transactional Outbox in the .NET Order Service first: add `outbox_events` table via EF Core migration, wrap order creation in the outbox pattern, ship a polling relay as `IHostedService`, then build the Go consumer with idempotency check + DLQ routing.
