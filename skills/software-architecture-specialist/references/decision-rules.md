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

```
When to add indexes vs when to fix code:

Indexes help when:          → I/O cost per query is high (slow disk reads, full table scans)
                            → Same rows fetched repeatedly (high AllocatedKB per call)
                            → GC pressure from large result sets
                            → Concurrency ceiling is low (index reduces hold_time per connection)

Indexes do NOT help when:   → Bottleneck is sequential round-trip count (N calls in series)
                            → Each query is fast but there are too many of them
                            → P50 >> (query_count × avg_query_time) suggests non-DB overhead

Diagnosis rule:
  If (P50 ÷ query_count) > 30ms → bottleneck is likely sequential round-trips → fix code structure
  If (P50 ÷ query_count) < 10ms → bottleneck is likely I/O → indexes first
  If AllocatedKB drops after indexes but P50 unchanged → confirms round-trip bottleneck, proceed to async

Real incident (target.cs):
  Indexes reduced AllocatedKB by 27% (I/O working) but P50 unchanged (1,505ms → 1,579ms).
  Diagnosis: P50 ÷ 50 queries = ~30ms/query → still borderline, but sequential tail of 30 per-sub-order
  calls dominates regardless. Code fix (async parallel) is the correct next step.
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
Async parallel coordinator (Task.WhenAll + IDbContextFactory):
Trigger when ALL of these are true:
  (1) Coordinator calls 2+ independent DB operations sequentially
  (2) I/O wait % > 80% (threads blocking, not CPU-bound)
  (3) Sequential latency > 300ms on hot-path

Do NOT use when:
  - Calls have data dependencies (B needs A's result) → sequential await
  - Only 1 DB call → async/await alone, no Task.WhenAll
  - < 10 req/s low-concurrency → sequential async sufficient

Thread safety rule:
  EF Core DbContext is NOT thread-safe.
  NEVER share _context across Task.WhenAll tasks.
  Each parallel task MUST get its own DbContext from IDbContextFactory.
  Rule: 1 concurrent task = 1 DbContext instance. No exceptions.

BotE impact:
  Sequential: latency = sum(all DB calls)
  Parallel:   latency = max(all DB calls)
  Throughput gain = (sum - max) / sum
  Example: 400+300+250+200=1150ms → max=400ms → 65% latency reduction

See patterns.md #26: Async Parallel DB Coordinator.
Real example: GetSubOrderAsync (incident2.cs) — Phase 4, applied 2026-03-27.
```

```
Map function extraction:
When: async version of a method needs the same in-memory mapping as the sync version.
Rule: extract the mapping (e.g. MapPayments, MapPromotions, MapRewardItems) to a private
  pure method with no DbContext dependency.
  Both sync and async paths call the same mapper — zero duplication, zero DB.
Why: keeps async methods thin (query + return), mapping logic tested independently.
```

```
Include() chain depth:
1–2 levels         → OK, no split query needed
3+ levels or 2+ collections → AsSplitQuery() required to avoid cartesian explosion
5+ levels and data sparse   → switch to projection (Select DTO) instead of deep Include()
```

```
AsSplitQuery() behavior — what it does and does NOT do:
  DOES:  Splits each Include path into a separate SQL query to avoid cartesian join explosion
  DOES:  Improve memory efficiency when loading multiple collections
  DOES NOT: Reduce total query count — N Include paths = N split queries (same count as Entry().Load() per path)
  DOES NOT: Help if the outer loop is the bottleneck — AsSplitQuery inside a loop still runs N×queries

Rule:
  Using AsSplitQuery to replace Entry().Load() inside a loop → ZERO improvement (1:1 replacement)
  Using AsSplitQuery in a BULK query (all records at once) → CORRECT — ~16 queries total regardless of N
  If AsSplitQuery didn't reduce latency → the outer loop is the real bottleneck, apply Pattern #13

Real incident (target.cs): Phase 3 attempt 1 — replaced 21 Entry().Load() with Include + AsSplitQuery
  inside the per-sub-order loop. Result: ~0% latency change, +19% worse cold start. Reverted.
  Fix: batch the outer loop itself (Pattern #13 Bulk Load Then Map). P50: 2,730ms → 1,505ms (-45%).
```

```
Outer loop vs inner query optimization:
  Symptoms of inner query bottleneck: each iteration has 1-2 queries, latency ∝ query_count × latency_per_query
  Symptoms of outer loop bottleneck:  each iteration has 5+ queries, latency ∝ N × (queries × latency)
  Diagnosis: if (P50 ÷ N) ≈ constant → outer loop is the bottleneck
  Fix for outer loop: Pattern #13 Bulk Load Then Map — eliminate the loop, not the inner queries
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

---

## Distributed Systems — CAP & Consistency

```
Data correctness = money / safety (inventory, payment, booking)?
  → CP system: refuse to respond during partition, never serve stale data
  → Use: PostgreSQL/MySQL with ACID, ZooKeeper, 2PC

User experience > strict correctness (social feed, notifications, analytics)?
  → AP system: return possibly stale data during partition
  → Use: Cassandra, DynamoDB, Redis (eventual consistency)

Multi-region active-active?
  → AP with conflict resolution (vector clocks, LWW, CRDT)
  → Never 2PC across regions (too slow, too fragile)
```

```
Quorum configuration (N replicas, W write quorum, R read quorum):
Strong consistency:   W + R > N  (e.g. N=3, W=2, R=2)
Fast reads:           R=1, W=N
Fast writes:          W=1, R=N
Balanced production:  N=3, W=2, R=2  ← default for most systems

Financial/inventory?  → N=3, W=2, R=2 (balanced + consistent)
Social/analytics?     → W=1, R=1 (fast, eventual)
Audit log?            → W=N, R=1 (write to all, fast read)
```

```
Conflict resolution strategy:
Shopping cart / collaborative doc?  → CRDT or client-merge
Financial transaction?              → TC/C + Saga (never LWW — too lossy)
Key-value store (eventual OK)?      → Vector clocks + LWW
```

---

## Distributed Systems — Consistent Hashing

```
Static server count (never changes)?  → Simple mod-N hashing
Dynamic server count (autoscale)?     → Consistent hashing
Need even distribution across nodes?  → Virtual nodes: 100–200 per physical server
Standard deviation target:            → 5–10% with 100–200 virtual nodes
```

```
Key remapping on topology change:
Traditional mod-N:    ~all keys remapped on any server change
Consistent hashing:   k/n keys remapped (k=total keys, n=total slots)
```

---

## Distributed Systems — ID Generation

```
Need time-sortable 64-bit IDs, distributed, no coordination?
  → Snowflake (41-bit timestamp + 5-bit DC + 5-bit machine + 12-bit sequence)
  → 4,096 IDs/ms per machine, 69-year range, requires NTP

Need random non-guessable IDs?
  → UUID v4 (128-bit, no coordination, not sortable)

Need strictly sequential, single-server?
  → DB auto-increment (PostgreSQL SERIAL / MySQL AUTO_INCREMENT)

Clock synchronization unreliable?
  → ULID (monotonic, base32, UUID-compatible, no strict NTP)

Max throughput per Snowflake node:
  → 4,096 IDs/millisecond = 4.096M IDs/second per machine
```

---

## Distributed Systems — Distributed Transactions

```
All operations in one DB?
  → Local DB transaction (ACID) — no distributed mechanism needed

Cross-service, 2–3 services, loss-tolerant with rollback?
  → Choreography Saga + idempotency keys
  → Each service emits event on success, compensates on failure

Cross-service, complex multi-step with strict rollback?
  → Orchestration Saga (central orchestrator coordinates steps)

Financial payment across services with strict atomicity?
  → TC/C (Try-Confirm/Cancel) + idempotency + end-of-day reconciliation

Strict ACID across few resources (2–3 DBs), latency acceptable?
  → 2PC (accept blocking on coordinator failure)

Rule: never use 2PC across datacenters — network partition makes it deadlock
```

---

## Rate Limiting

```
Algorithm selection:
  General API, burst acceptable?           → Token Bucket (most widely used)
  Stable constant processing rate?         → Leaking Bucket
  Simple per-minute quota?                 → Fixed Window Counter
  High accuracy required?                  → Sliding Window Log (high memory)
  Scale + accuracy balance?                → Sliding Window Counter (~0.003% error)

Token Bucket parameters:
  bucket_size   = max burst allowed (e.g. 20 requests)
  refill_rate   = sustained rate (e.g. 10 req/sec)
  Start with:   bucket_size = 2× refill_rate

Rate limit key selection:
  Per user/API key?     → most common, protects against single client abuse
  Per resource (order)? → when one order being hammered is the bottleneck
  Per IP?               → edge/public APIs before auth

Storage: Redis (INCR + EXPIRE or Lua script for atomicity)
Response: HTTP 429 Too Many Requests + Retry-After header
```

---

## Real-Time Connections

```
Connection type selection:
  Bidirectional, low latency (chat, location, collaborative editing)?
    → WebSocket (full-duplex, persistent TCP)

  One-way server push, infrequent updates (file sync, order status)?
    → Long Polling (HTTP-based, simpler, less overhead)

  One-way continuous feed (stock tickers, live scores)?
    → Server-Sent Events (SSE) — HTTP-based, auto-reconnect

  Periodic check, low frequency (> 5 second interval)?
    → Short Polling (simple, stateless)

WebSocket memory budget:
  Each connection: ~10KB server RAM
  100K connections: ~1GB RAM
  1M connections:  ~10GB RAM
  Plan connection servers: 100K–1M connections per server instance

WebSocket scaling: sticky sessions OR shared routing via Redis Pub/Sub
  If WebSocket servers are stateless → use Redis Pub/Sub for message routing
  If stateful → use service discovery (ZooKeeper/etcd) + consistent hashing
```

---

## Caching — Enhanced (CDN + Distributed)

```
When to use CDN:
  Static assets (HTML, CSS, JS, images, video)?  → CDN mandatory
  Map tiles, precomputed content?                → CDN (pull model)
  Dynamic API responses?                         → CDN only with explicit Cache-Control
  Popular vs long-tail content (YouTube rule):
    → Top 20% content → CDN
    → Bottom 80% (long-tail) → origin only (CDN cost not justified)

CDN cost signal: CDN egress ~$0.02–0.08/GB
  If CDN monthly bill > Redis cluster bill → review what you're caching on CDN

Cache layer selection:
  Global static content?                  → CDN edge nodes
  Session / auth tokens?                  → Redis (5–15 min TTL)
  Hot read data, rarely changes?          → Redis (1 hour TTL)
  Order / payment status?                 → Do not cache OR ≤ 30s TTL + event invalidation
  Reference data (categories, config)?    → Redis (1–24 hour TTL)

Cache invalidation strategy:
  Write-through:  update cache on every write → consistent, higher write cost
  TTL expiry:     simple, acceptable staleness for non-critical data
  Event-driven:   Kafka event → invalidate cache key → most accurate for distributed systems
  CDC (Debezium): watch DB changes → auto-invalidate → good for cache-DB sync

Hot key / celebrity problem:
  Condition: one cache key receives >> traffic than average
  Detection: cache hit rate drops on specific keys despite high overall hit rate
  Fix: replicate hot key to multiple shards + add random suffix (key_1, key_2)
       or serve from client-side cache (short TTL in memory)
```

---

## Storage Strategy

```
Replication vs Erasure Coding:
  Hot data (accessed daily)?                    → 3× replication
  Warm data (accessed weekly)?                  → 3× replication or hybrid
  Cold data (accessed monthly or less)?         → Erasure coding 4+2 (50% overhead vs 200%)
  Storage cost is primary constraint?           → Erasure coding
  Fast recovery required?                       → 3× replication
  Hybrid (best of both):                        → Replicate hot, erasure-code cold

Durability comparison:
  3× replication (4+2 erasure):
  Both survive 2 simultaneous node failures
  3× overhead: 200% | 4+2 overhead: 50%
  3× recovery: fast (copy) | 4+2 recovery: slow (reconstruct)

Database type by workload:
  ACID + complex joins + bounded scale?         → PostgreSQL / MySQL
  High-volume time series (metrics, IoT)?       → InfluxDB / Prometheus (10–100× faster)
  Chat / messaging (time-sorted access)?        → Cassandra / HBase (wide-column)
  Cache + session + leaderboard?                → Redis
  Full-text / document search?                  → Elasticsearch
  Object / file storage?                        → S3 / Blob (not a DB)
  Financial ledger (audit + ACID)?              → PostgreSQL + Event Sourcing
  High-write key-value at scale?                → DynamoDB / Cassandra

LSM Tree vs B-Tree:
  Write-heavy (events, logs, time series)?      → LSM-based DB (Cassandra, RocksDB, InfluxDB)
  Read-heavy with complex queries?              → B-Tree DB (PostgreSQL, MySQL)
  Both?                                         → CQRS: LSM for write, B-Tree read model
```

---

## Geospatial Indexing

```
Algorithm selection:
  Nearby search, simple range, fixed precision?  → Geohash (string prefix + 8 neighbors)
  Density-aware, variable precision?             → Quadtree (dynamic subdivision)
  Arbitrary polygon regions?                     → Google S2

Geohash precision levels:
  Level 4: ~39km × 20km (city-scale)
  Level 5: ~4.9km × 4.9km (neighborhood-scale)
  Level 6: ~1.2km × 609m (block-scale)  ← most common for "nearby" search

Geohash search pattern:
  1. Convert user location to geohash at chosen precision
  2. Compute 8 neighboring cells
  3. Query WHERE geohash_col = ANY(9 cells)
  4. Filter by haversine distance
  5. If insufficient results → expand to one precision level lower

Index: CREATE INDEX ON businesses(geohash_6) — regular string index, O(log n) lookup
Boundary problem: always check all 8 neighbors, not just the center cell
```

---

## Financial Systems

```
Double-entry ledger rule:
  Any monetary transfer?  → double-entry ledger mandatory
  Balance query?          → SUM of ledger entries (never store mutable balance only)
  Currency storage?       → integer cents (never float — floating point is lossy)
  Deletion of entries?    → NEVER — append-only, immutable audit trail

Idempotency in payments:
  Every payment attempt?  → client-generated UUID idempotency_key required
  Retry window?           → idempotency key TTL: 24–48 hours
  Duplicate detection?    → check key before processing, store result with key
  Kafka payment event?    → deduplication table with event_id + TTL

PCI-DSS scope:
  Team handles raw card data?  → PCI-DSS Level 1 audit required (expensive)
  Use PSP hosted page?         → PCI scope eliminated (Stripe / PayPal tokenize for you)
  Rule: always use hosted payment page unless you have a dedicated compliance team

Reconciliation:
  Financial system?  → end-of-day reconciliation mandatory
  Compare: internal ledger total vs PSP settlement file
  Any discrepancy?   → alert immediately, treat as incident

Event sourcing for finance:
  Financial audit trail required?   → Event sourcing mandatory
  Temporal queries ("balance at T")? → Event sourcing mandatory
  Simple balance counter?            → regular DB update is sufficient
```

---

## Scalability Thresholds (Back-of-Envelope Reference)

```
QPS estimation formula:
  QPS = DAU × actions_per_day / 86,400

Key latency targets:
  < 100ms  → good (green)
  100–300ms → acceptable under load
  300–900ms → degraded, investigate
  > 900ms  → incident level, page on this

When to add caching:     QPS > 1,000 reads on same data
When to shard:           Storage > 1 TB OR write QPS > 5,000 on single node
When to add CDN:         Static assets > 100MB OR users in multiple continents
When to add message queue: Producer throughput ≠ consumer throughput (mismatch)
When to go async:        Connection hold time × concurrent requests > 80% of pool size

Storage estimation:
  100M users × 10 actions/day × 100 bytes = 100GB/day
  1B events/day × 1KB = 1TB/day
  Video (300MB avg) × 5M uploads/day = 1.5PB/day

Availability → downtime budget:
  99%    → 3.65 days/year (not acceptable for production)
  99.9%  → 8.7 hours/year (acceptable for internal tools)
  99.99% → 52.6 min/year (target for customer-facing)
  99.999%→ 5.26 min/year (financial / payments target)
```