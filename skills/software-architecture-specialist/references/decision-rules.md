# 📐 Decision Rules

> Read this file when the user asks "when should I use X?", "is N too many?", "should I add a cache?",
> or any question that needs a concrete threshold or if/then judgment — not a pattern explanation.
> These rules are extracted from real incidents, KOS knowledge records, and architectural principles.
> They are meant to be fast answers, not full discussions.

---

## Index

| Domain | Rules |
|--------|-------|
| [DB Query & Performance](#db-query--performance) | N+1 threshold, batch size, chunking, AsNoTracking |
| [EF Core](#ef-core) | When to use Include vs batch, projection, split query |
| [Kafka & Messaging](#kafka--messaging) | Retry count, DLQ routing, partition strategy, Outbox trigger |
| [Caching](#caching) | When to add cache, TTL, invalidation strategy |
| [Data Ingestion (ETL/FTP)](#data-ingestion-etlftp) | Staging trigger, validation gate, chunk size |
| [API Design](#api-design) | Pagination threshold, timeout, idempotency trigger |
| [Architecture Patterns](#architecture-patterns) | When to introduce CQRS, Saga, Repository, Circuit Breaker |
| [System Design](#system-design) | Microservice split trigger, event vs direct call, retry strategy |
| [Observability](#observability) | What to always log, alert thresholds, metric naming |
| [Code Review Flags](#code-review-flags) | Immediate flags, questions to always ask |

---

## DB Query & Performance

```
N < 50    → N+1 acceptable, no action needed
N > 100   → must use batch query (IN clause + dictionary)
N > 1000  → batch + chunk (chunk size: 500)
N > 10000 → batch + chunk + streaming (avoid loading all into RAM)
```

```
Query count per request:
< 10    → healthy
10–30   → acceptable, monitor
30–100  → investigate
> 100   → critical, must fix before merge
```

```
Response latency target (read APIs):
< 100ms  → good
100–300ms → acceptable under load
300–900ms → degraded, investigate
> 900ms  → incident level, page on this
```

```
Connection pool math (concurrency ceiling):
Formula: concurrent_requests × queries_per_request × avg_hold_time_seconds < pool_size
Example (target.cs GetSubOrder before fix):
  100 concurrent × 33 queries × 0.01s = 33s total hold → pool exhaustion (default pool=100)
Example (after fix):
  100 concurrent × 7 queries × 0.01s = 7s → well within pool capacity
Rule: if formula result > 80% of pool size → investigate query count reduction first
```

```
Batch vs chunking:
Batch query  → optimizes average latency (fewer roundtrips)
Chunking     → optimizes tail latency and memory (controls max RAM per operation)
Both needed  → when N > 1000
```

---

## EF Core

```
AsNoTracking():
Always use on GET endpoints and read-only operations.
Never skip — the default tracking overhead is not free.
```

```
Include() vs batch load:
Include() with 1 collection   → OK
Include() with 2+ collections → use AsSplitQuery() to avoid cartesian explosion
Include() inside a loop       → NEVER — replace with batch + dictionary
```

```
Select() projection:
Always project to a DTO when you need < 50% of the entity fields.
Never load full entity if you only need 3 fields out of 20.
```

```
Any() + FirstOrDefault() on same table:
Always collapse to a single FirstOrDefault() — two queries where one is enough.
```

```
.Entry().Reference().Load() or .Entry().Collection().Load():
Inside a loop → BLOCK — replace with Include() chain (Eager Graph Loading, Pattern #11).
Outside a loop (single entity) → acceptable.
```

```
Shared context resolution (e.g. IsExistOrderReference, order header lookup):
Called once for a single request → OK.
Called N times for the same ID in the same request → BLOCK — resolve once at coordinator level, pass result down.
Rule: if two sibling calls resolve the same ID independently, the coordinator must own that resolution.
See patterns.md #12: Coordinator-Level Resolution.

Real example (target.cs):
  GetOrderHeader (line 479), GetOrderMessagePayments (line 131), GetOrderPromotion (line 185)
  each call IsExistOrderReference independently for the same SourceOrderId = 6-9 redundant queries.
  Fix: resolve once in GetSubOrder (coordinator), pass resolved ID to all three.
```

```
Include() chain depth:
1–2 levels         → OK, no split query needed
3+ levels or 2+ collections → AsSplitQuery() required to avoid cartesian explosion
5+ levels and data sparse   → switch to projection (Select DTO) instead of deep Include()
```

---

## Kafka & Messaging

```
Retry policy per error type:
Transient (timeout, DB lock, network)  → retry with exponential backoff, max 3 attempts
Permanent (bad schema, business rule)  → DLQ immediately, no retry
Unknown                                → retry 3x, then DLQ
```

```
Backoff strategy:
Attempt 1 → wait 1s
Attempt 2 → wait 4s
Attempt 3 → wait 16s
Then DLQ
```

```
Outbox pattern trigger:
DB write + event publish must both succeed or both fail → Outbox required
Fire-and-forget notification (email, push, analytics) → direct publish OK
```

```
Partition key selection:
Need order per entity (e.g., per OrderId) → partition by entity key
No ordering requirement                   → round-robin or random
Need global order                         → single partition (accept throughput limit)
```

```
Consumer group scaling:
Consumers < partitions → some consumers are idle, scale up
Consumers = partitions → optimal
Consumers > partitions → extra consumers sit idle, no benefit
```

```
DLQ monitoring:
DLQ message count > 0 → always alert, never ignore silently
DLQ growing steadily  → systemic bug, treat as incident
```

---

## Caching

```
When to add cache:
Same data read > 10x per minute with low change frequency → cache candidate
Data is expensive to compute (joins, aggregations)        → cache candidate
Real-time accuracy required (stock, payment status)       → do NOT cache
```

```
TTL selection:
Reference data (categories, config)     → 1 hour – 24 hours
User profile / session                  → 5–15 minutes
Order / inventory status                → do not cache, or < 30 seconds with explicit invalidation
```

```
Cache invalidation strategy:
Write-through → update cache on every write (consistent, higher write cost)
TTL expiry    → simple, acceptable staleness
Event-driven  → invalidate on Kafka event (preferred for distributed systems)
```

```
Cache vs DB read replica:
Low latency needed + data rarely changes → cache (Redis)
Need consistent reads + moderate latency → DB read replica
Both                                     → cache in front of read replica
```

---

## Data Ingestion (ETL/FTP)

```
Staging table trigger:
External / untrusted source (FTP, partner API) → always use staging
Internal trusted source (own service)          → staging optional, add inline validation
Need replay on bug fix                         → staging mandatory
```

```
Chunk size for file processing:
< 10,000 rows   → process in memory, single transaction
10k – 100k rows → chunk by 1,000, commit per chunk
> 100k rows     → streaming read + chunk insert, never load full file into RAM
```

```
Validation gate:
Hard validation failure (missing required field, wrong type) → reject row, log, continue
Soft validation failure (unexpected value, out of range)     → flag row, process with default
All rows in file fail validation                             → reject file, alert, do not partially apply
```

```
Change detection strategy:
Source has reliable timestamps   → filter by updated_at > last_sync
Source has no timestamps         → record-level hash comparison
Source sends full snapshot daily → staging + diff against current state
```

---

## API Design

```
Pagination threshold:
Result set potentially > 100 rows → always paginate
Result set always < 20 rows       → pagination optional
Default page size: 20–50
Max page size: 200 (enforce server-side)
```

```
Timeout defaults (.NET HttpClient):
Internal service call  → 5s
External partner API   → 15s
File download / upload → 120s
Never use infinite timeout
```

```
Idempotency key requirement:
POST that creates a resource          → idempotency key required
POST that triggers payment / charge   → idempotency key required
GET / read-only                       → not needed (idempotent by nature)
PUT / PATCH (full or partial replace) → idempotent by design if using same payload
```

```
HTTP status code discipline:
200 → success with body
201 → created
204 → success no body (DELETE, async trigger)
400 → client error, validation failure — include error detail
404 → resource not found — not a 200 with null body
409 → conflict (duplicate key, idempotency collision)
422 → business rule violation
500 → never expose stack trace in response body
```

---

## Architecture Patterns

```
Repository pattern:
Complex query logic repeated in 2+ services  → introduce Repository
Simple CRUD, 1 service, no test requirement  → direct DbContext is fine
Need to unit test business logic             → Repository with interface, inject mock
```

```
CQRS trigger:
Read shape == write shape, simple CRUD       → no CQRS needed
Read model is significantly different        → CQRS read model (same DB OK)
Read volume >> write volume (100:1+)         → CQRS with separate read store
Need event sourcing                          → CQRS required
```

```
Saga trigger:
Single service, single DB operation          → local transaction, no Saga
2–3 services, simple linear flow             → Choreography Saga (events)
3+ services, complex flow with rollback need → Orchestration Saga
Cannot define compensating actions           → do not use Saga, redesign boundary
```

```
Circuit Breaker trigger:
Calling external HTTP service        → always add Circuit Breaker
Internal in-process call             → not needed
Downstream timeout > 2s expected     → Circuit Breaker + Timeout policy
Service mesh available (Istio, etc.) → circuit breaker at mesh level preferred
```

```
Outbox vs direct Kafka publish:
Must guarantee delivery (order, payment, inventory) → Outbox
Informational / analytics event, loss acceptable    → direct publish
```

---

## System Design

```
Microservice split trigger:
Team owns it independently                           → split candidate
Deployment cycles are completely different           → split candidate
Shared DB with another service AND tight coupling    → do NOT split yet, fix coupling first
Shared DB with another service AND independent data  → split with data migration
```

```
Event-driven vs direct call:
Caller needs immediate response with data  → direct HTTP / gRPC call
Caller just needs to trigger an action     → event (Kafka)
Eventual consistency acceptable            → event
Strong consistency required                → direct call or Saga
```

```
Retry strategy by operation type:
Idempotent read          → retry immediately, up to 3x
Idempotent write (upsert)→ retry with backoff, up to 3x
Non-idempotent write     → do NOT retry without idempotency key
Payment / charge         → idempotency key required before any retry
```

```
When to add a message queue:
Producer is faster than consumer (throughput mismatch) → queue
Need to decouple services (producer doesn't wait)      → queue
Fan-out to multiple consumers                          → topic / Kafka
Simple in-process background task                      → IHostedService, no queue needed
```

---

## Observability

```
Always log:
- Request ID / Trace ID on every log line
- Method entry + exit with duration for operations > 100ms
- All exceptions with stack trace
- All external calls (DB, Kafka, HTTP) with duration
- Business events (order created, payment processed, sync completed)
```

```
Before/after measurement — required for hot-path changes:
Before touching any code on a hot path → capture baseline: ElapsedMs, DB query count, MemAllocatedKB, GC.Gen0 delta
After each fix phase → re-measure and record delta
A fix without a baseline is anecdotal — it cannot be logged as a real incident result

Minimum instrumentation for a .NET hot-path method:
  var sw = Stopwatch.StartNew();
  var memBefore = GC.GetTotalMemory(false);
  var gen0Before = GC.CollectionCount(0);
  // ... method body ...
  _logger.LogInformation("Method | ElapsedMs: {Ms} | MemKB: {Kb} | Gen0: {Gen0}",
      sw.ElapsedMilliseconds,
      (GC.GetTotalMemory(false) - memBefore) / 1024,
      GC.CollectionCount(0) - gen0Before);
```

```
GC pressure indicators:
GC.Gen0 delta > 0 per request   → short-lived object churn (EF proxy objects, tracking overhead)
GC.Gen1 delta > 0 per request   → memory pressure — objects surviving Gen0, investigate
GC.Gen2 delta > 0 per request   → serious — large or long-lived allocations, treat as incident
AsNoTracking() on read path      → reduces Gen0 pressure by eliminating EF change tracking objects
```

```
Never log:
- PII (name, email, phone, address) in plain text
- Passwords, tokens, API keys
- Full request/response body in production (log shape, not data)
```

```
Prometheus metric naming convention:
<service>_<operation>_<unit>_total
Examples:
  suborder_api_requests_total
  suborder_db_query_duration_seconds
  stock_sync_records_processed_total
  kafka_consumer_lag_messages
```

```
Alert thresholds (starting points, tune per system):
Error rate > 1%       → warning
Error rate > 5%       → critical, page
P99 latency > 1s      → warning
P99 latency > 3s      → critical
Kafka consumer lag > 1000 messages → warning
Kafka consumer lag > 10000         → critical
```

---

## Code Review Flags

**Immediate flags — block merge:**
```
[ ] DB call inside a loop (foreach, for, while)
[ ] .Entry().Reference().Load() or .Entry().Collection().Load() inside a loop
[ ] Any() followed by FirstOrDefault() on the same table/query
[ ] Missing AsNoTracking() on read-only GET endpoint
[ ] Missing try/catch on Kafka consumer handler
[ ] Hardcoded connection string, API key, or secret
[ ] Exception swallowed silently (catch with no log, no rethrow)
[ ] Infinite retry without max attempts
[ ] Same reference resolver (e.g. IsExistOrderReference) called 2+ times for the same ID in one request
[ ] Hot-path change merged without before/after query count or latency measurement
[ ] Connection pool math not validated for expected concurrency level
```

**Questions to always ask in review:**
```
- What happens if this fails halfway through?
- What happens if this is called twice with the same input?
- What is the worst case query count for this endpoint?
- Is the caller expected to retry? Is this operation safe to retry?
- What does the caller see if the dependency is down?
- How will we know in production if this breaks?
- Does any sub-call resolve data the parent already knows? (shared context leak)
- Is there a baseline measurement to compare this change against?
- What is the connection pool math at expected peak concurrency?
```