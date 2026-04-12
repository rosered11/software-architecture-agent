# System Design Review: Order Webhook Pipeline

**Date:** 2026-04-12

## Design Summary

```
Webhook → .NET API → PostgreSQL
                   → Kafka → Go Consumer → Order Status Update
```

- .NET API receives order webhooks, persists to PostgreSQL, publishes to Kafka
- Go Consumer reads from Kafka and updates order status
- Current load: ~50 orders/minute; expected growth: 10x to ~500 orders/minute
- Missing: retry logic on consumer, Dead Letter Queue (DLQ)

---

## Strengths

1. **Decoupled write path** — Saving to PostgreSQL before publishing to Kafka establishes the source of truth before async processing begins.
2. **Kafka as a buffer** — Naturally handles burst absorption. 500 orders/minute fits comfortably in a single partition with headroom.
3. **Separation of concerns** — The Go consumer handles status updates independently, which is correct for a CQRS-adjacent pattern.
4. **Polyglot stack fits responsibilities** — .NET for rich domain logic, Go for high-throughput consumption is a solid operational split.

---

## Critical Gaps

### 1. No Retry Logic on the Go Consumer — Risk: HIGH

If the consumer fails to process a message (DB timeout, transient network error), the message is either skipped silently, committed before processing and lost, or loops infinitely on a poison pill blocking the entire partition.

**At 10x:** One bad message can halt all 500 orders/minute on that partition.

**Fix:** Exponential backoff retry within the consumer (3–5 attempts with jitter) before escalating to a DLQ topic.

---

### 2. No Dead Letter Queue (DLQ) — Risk: HIGH

Without a DLQ, permanently bad messages block retries indefinitely or are silently dropped. No observability, no replay path, no manual intervention option.

**Fix:** Create an `orders.dlq` Kafka topic. After N failed retries, publish the original message + error metadata there. Alert on DLQ consumer lag > 0.

---

### 3. Dual-Write Consistency (PostgreSQL + Kafka) — Risk: MEDIUM

If the Kafka publish fails after a successful DB write, the order exists in PostgreSQL but the consumer never processes it — silent inconsistency.

**Options:**

| Option | Trade-off |
|--------|-----------|
| Outbox Pattern | Best consistency; adds relay complexity |
| At-least-once + idempotent consumer | Simpler; requires careful consumer design |
| Kafka Transactions | Complex; requires transactional producers |

**Recommendation:** Outbox Pattern. At 500 orders/minute, even a 0.1% dual-write failure rate is 0.5 dropped events per minute — unacceptable for an order system.

---

### 4. Consumer Idempotency — Risk: MEDIUM

Kafka guarantees at-least-once delivery. The Go consumer may process the same message more than once after a crash/restart. Non-idempotent status updates cause incorrect order states.

**Fix:** Use `UPDATE orders SET status = $1 WHERE id = $2 AND status != $1` or include an `event_sequence` / `updated_at` guard.

---

### 5. Partition Strategy — Risk: LOW-MEDIUM (becomes HIGH at 10x)

Without partitioning by `order_id`, multiple status updates for the same order may arrive out of order on different partitions.

**Fix:** Partition Kafka messages by `order_id` to guarantee per-order sequential processing.

---

### 6. Observability Gaps — Risk: MEDIUM

No mention of consumer lag monitoring, processing latency, or DLQ alerting.

**Fix:** Expose Prometheus metrics from the Go consumer — consumer lag by topic/partition, `order_processing_duration_seconds` histogram, `order_processing_errors_total` counter by error type.

---

## Scalability at 10x (500 orders/minute)

| Component | 10x Readiness | Action Required |
|-----------|---------------|-----------------|
| .NET API | Yes, if stateless | Confirm connection pooling (PgBouncer or EF Core pool) |
| PostgreSQL | Needs validation | Add index on `order_id`; consider read replica |
| Kafka | Yes | Increase partitions proactively; replication factor >= 2 |
| Go Consumer | No — SPOF | Enable consumer group scaling; fix retry/DLQ first |

---

## Prioritized Recommendations

**Immediate (before production or any scaling):**
1. Add retry logic to Go consumer — exponential backoff, 3–5 attempts, jitter
2. Add DLQ topic + alerting — `orders.dlq`, alert on lag > 0
3. Make consumer updates idempotent — upsert with state guards

**Short-term (before 3x growth):**
4. Implement Outbox Pattern — eliminate dual-write inconsistency
5. Partition by `order_id` — preserve per-order ordering guarantees
6. Add consumer lag monitoring — Prometheus + threshold alerts

**Medium-term (before 10x growth):**
7. Scale Go consumer group — multiple instances, Kafka partition assignment
8. PostgreSQL connection pooling — PgBouncer in front of PostgreSQL
9. Load test at 2x, 5x, 10x — validate assumptions before traffic arrives

---

## Risk Summary

| Risk | Severity | Priority |
|------|----------|----------|
| Poison pill blocks partition (no retry/DLQ) | Critical | P0 |
| Dual-write drops Kafka events | High | P1 |
| Non-idempotent status updates corrupt state | High | P1 |
| Consumer SPOF at 10x | Medium | P2 |
| Out-of-order status updates | Medium | P2 |
| Observability blind spots | Medium | P2 |

---

## Conclusion

The architecture is directionally sound, but the **absence of retry logic and a DLQ is a critical production risk today** — not just at 10x. A single malformed webhook or transient DB timeout can permanently stall order processing on a partition.

The dual-write consistency gap is the second most urgent concern and should be resolved with the Outbox Pattern before scaling. Address P0 and P1 items before any growth milestone. With those fixes in place, this system is architecturally capable of reaching 500 orders/minute.
