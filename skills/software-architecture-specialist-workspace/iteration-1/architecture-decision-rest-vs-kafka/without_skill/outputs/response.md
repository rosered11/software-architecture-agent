# Architecture Decision: REST vs Kafka for .NET Order Service → Go Fulfillment Service

**Date:** 2026-04-12
**Load:** ~200 req/min today → ~2,000 req/min in 6 months
**Processing time:** 2–5 seconds per fulfillment

---

## Recommendation: Use Kafka (Async Event-Driven)

**Choose Kafka.** The combination of 10x growth, 2–5 second processing time, and cross-language service boundaries makes synchronous REST the wrong tool here.

---

## Why Synchronous REST Fails at This Scale

**Latency mismatch creates cascading risk.** At 2,000 req/min (~33 req/sec) with 2–5 second blocking calls, you need roughly 116 concurrent in-flight requests held open at all times. Any slowdown or spike in Fulfillment propagates directly upstream into Orders — classic synchronous coupling amplification.

**Availability coupling.** If the Go Fulfillment Service restarts or has a transient failure, every in-flight order fails. Orders submitted during the outage window are lost unless the caller persists and retries. There is no natural buffer.

**10x growth is not linear.** Crossing from 200 to 2,000/min (plus burst headroom to ~3,000–4,000/min) pushes the concurrent-connection math firmly into the danger zone.

---

## Why Kafka Fits This Problem

**Decoupled processing rate.** The Order Service publishes and returns immediately (sub-millisecond). The Go Fulfillment Service consumes at its own pace. Order throughput is no longer coupled to fulfillment processing time.

**Backpressure is handled naturally.** Spikes queue in Kafka. No events are dropped. No circuit breakers trip. The lag clears when the spike passes.

**Clear horizontal scale path.** At 2,000/min with 3 sec avg processing: ~33 orders/sec requiring ~100 parallel processing units. With Kafka, add 100 partitions and 100 consumer goroutines — a config change, not an architecture change.

**Failure isolation.** If Fulfillment goes down, Orders keeps accepting. Events accumulate durably. When Fulfillment recovers, it replays from its last committed offset. Zero order loss.

**Cross-language fit.** .NET (Confluent.Kafka) and Go (sarama or confluent-kafka-go) are both mature. Kafka's protocol is language-agnostic — a natural fit for this polyglot stack.

---

## Comparative Table

| Dimension | REST | Kafka |
|---|---|---|
| Coupling | Tight (availability coupled) | Loose (publish and forget) |
| Throughput ceiling | ~30–50 req/sec before saturation | Millions/sec with partitioning |
| Failure isolation | None — caller must handle | Full — events persist through outage |
| Scale mechanism | Vertical or complex LB | Add partitions + consumers |
| Observability | Latency + error rate | Consumer lag (key metric) |
| Complexity cost | Low initial | Higher initial (broker ops) |
| Order guarantee | Per-request | Per-partition (key by order_id) |

---

## Implementation Guidance

**Topic design:** Start at 20 partitions, partition key = `order_id`, retention = 7 days, replication factor = 3.

**Transactional Outbox Pattern (critical):** In the .NET Order Service, persist the Kafka event to a DB outbox table in the same transaction as the order record. A relay process publishes to Kafka. This eliminates the dual-write problem.

**Go consumer:** Use manual offset commit — commit only after fulfillment is durably persisted. Consumer group = `fulfillment-service`.

**Dead Letter Queue:** Topic `order.submitted.dlq` for events that fail after N retries. Alert on DLQ depth.

**Key metrics:** Consumer lag per partition (primary health signal), processing time P50/P95/P99, DLQ event count, producer error rate.

---

## Decision Rule

> If processing time > 500ms OR expected load > 500 req/min OR services cross team/language boundaries → use async messaging (Kafka). Otherwise REST is acceptable.

---

## When REST Would Be Right

REST is appropriate only if: you need synchronous confirmation before responding to the end user (e.g., a payment), load is low and stable (< 50 req/min), and fulfillment latency is < 200ms. None of these apply here.

---

## Summary

Choose **Kafka**. The 2–5 second processing time combined with 10x growth makes synchronous REST unsustainable within months. Kafka provides decoupling, durability, and horizontal scale. The .NET → Kafka → Go pattern is idiomatic and proven for this stack. The operational cost of running a broker is a one-time investment that pays dividends across every future integration on this platform.
