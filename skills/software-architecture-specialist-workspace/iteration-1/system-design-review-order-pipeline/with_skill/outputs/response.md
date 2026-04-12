**Mode: System Design Review**
**System:** Order Webhook Pipeline | **Type:** Event-Driven / Kafka-based, API / Service Layer, Background Worker

---

## Back-of-Envelope Estimation

```
[1] Traffic
    Current:              50 orders/min = 0.83 QPS avg
    Peak (3x burst):      ~2.5 QPS
    10x growth target:    500 orders/min = 8.3 QPS avg
    Peak at 10x (3x burst): ~25 QPS

[2] Data Volume
    ~2 KB per order record
    Write rate (current): ~144 MB/day
    Write rate (10x):     ~1.44 GB/day
    90-day retention at 10x: ~130 GB (manageable with PostgreSQL partitioning)

[3] DB / Connection Pool
    10x peak: 25 QPS × 2 queries × 0.05s = 2.5 conn-seconds → ~3 connections held (pool=100, safe)
    RISK: If EF Core tracking or Kafka publish blocks request thread:
          50 burst QPS × 2 queries × 0.5s blocked = 50s → pool exhausted

[6] Headroom
    Real bottleneck: Go consumer reliability (no retry, no DLQ) — not infrastructure capacity
    Infrastructure can absorb 10x. Correctness is the failure mode, not throughput.
```

---

## Risks (Ranked by Likelihood × Impact)

**CRITICAL — No Retry and No DLQ on Go Consumer**
Where: Go Kafka consumer | Likelihood: High | Impact: Silent data loss
Failure: Consumer processes a message, PostgreSQL update fails transiently, offset committed, status update lost forever with no alert.
Fix: (1) Retry transient errors with exponential backoff (3 attempts, max 30s). (2) Route permanent errors to `orders.status-update.dlq`. (3) Commit Kafka offset only after successful DB write (`EnableAutoCommit = false`). Alert on DLQ depth > 0.

**CRITICAL — Dual-Write Risk: DB Write + Kafka Publish Not Atomic**
Where: .NET API | Likelihood: Medium | Impact: Split-brain — order saved but event never published
Fix: Implement the **Outbox Pattern**. Add `outbox_events` table. Write to Outbox in the same DB transaction as the order insert. Background Outbox publisher reads and publishes to Kafka.

**CRITICAL — Consumer Not Idempotent**
Where: Go Kafka consumer | Likelihood: High (any crash + restart re-delivers)
Fix: Add `webhook_event_id UNIQUE` constraint or `(order_id, event_type, sequence)` dedup key.

**MEDIUM — No Partition Key Strategy**
Fix: Set Kafka message key to `order_id`. Guarantees per-order ordering.

**MEDIUM — No Consumer Observability**
Fix: Prometheus metrics — `consumer_messages_processed_total`, `consumer_messages_failed_total`, `kafka_consumer_lag`. Alert on lag > 2 min, error rate > 1%. Propagate trace ID through Kafka headers.

**MEDIUM — No Timeout on Kafka Publish**
Fix: Set `DeliveryTimeout` + `MessageTimeoutMs` (e.g., 5s). Handle `DeliveryReport` errors.

---

## Scorecard

| Dimension           | Score | Notes |
|---------------------|-------|-------|
| Flow Completeness   |  3/5  | Happy path defined. Duplicate webhooks, partial failures not addressed. |
| Failure Handling    |  1/5  | No retry, no DLQ, no circuit breaker. Dual-write risk on API. |
| Data Consistency    |  2/5  | No Outbox pattern. No idempotency guard on consumer. |
| Retry & Idempotency |  1/5  | No retry policy. No DLQ. Consumer not idempotent. Most critical gap. |
| Observability       |  2/5  | Consumer observability absent. No consumer lag alert. |
| Scalability         |  3/5  | Infrastructure handles 10x. No partition key strategy documented. |
| Security Boundary   |  3/5  | Not fully described. Webhook signature verification not mentioned. |

**Overall: 15/35** — Not production-safe. Will fail silently under any transient fault.

---

## Action Plan

**Priority 1 — Add retry + DLQ to Go consumer**
Exponential backoff (3 attempts) for transient errors, DLQ for permanent errors, manual offset commit after successful DB write. Effort: 1–2 days.

**Priority 2 — Make Go consumer idempotent**
Add dedup unique constraint + `ON CONFLICT DO NOTHING`. Must be done alongside Priority 1. Effort: 0.5 days.

**Priority 3 — Set Kafka message key to `order_id`**
One-line change in .NET producer. Effort: < 1 hour.

**Priority 4 — Add consumer observability**
RED metrics + consumer lag in Prometheus, alert rules, trace ID propagation. Effort: 0.5–1 day.

**Priority 5 — Implement Outbox Pattern on .NET API**
Replace direct Kafka publish with Outbox table + background publisher. Essential before 10x. Effort: 2–3 days.

**Priority 6 — Add webhook idempotency key**
`webhook_event_id UNIQUE` on orders table. Prevents duplicate orders from retried webhooks. Effort: < 1 day.

---

## ADR + KOS Recommendations

**ADRs needed:**
- ADR-001: Outbox Pattern adoption for API → Kafka publish
- ADR-002: Go consumer retry strategy — transient vs permanent error classification + DLQ routing policy

**KOS records to create:**
- `K#` — Outbox Pattern: guarantees, trade-offs, .NET + EF Core implementation
- `P#` — Retry + DLQ pattern for Go Kafka consumers
- `D#` — Outbox vs dual-write decision for API-to-Kafka publish
- `TA#` — Go consumer retry wrapper with manual offset commit

---

**Next Step:** Start with Priority 1 today: add retry logic and DLQ routing to the Go consumer. The key design decision is error classification — which errors are transient (retry) vs permanent (DLQ immediately).
