# KOS — Pattern Records

> Cross-linked per the Incident → Knowledge → Pattern → Decision → Reuse loop.

---

## PATTERN RECORDS

---

### P1: Token Bucket Rate Limiting

```
Name:             Token Bucket Rate Limiting
Category:         API Design
Problem:          API endpoints receive burst traffic that can overwhelm backend systems
                  or exhaust resources for legitimate users.
Solution:         1. Assign each client (API key, user ID, IP) a bucket of capacity C
                  2. Bucket refills at rate R tokens per second
                  3. Each request consumes 1 token
                  4. If bucket empty: return HTTP 429 Too Many Requests
                  5. Store bucket state in Redis (INCR + TTL or Lua script for atomicity)
When to Use:      Any public or partner-facing API
                  Endpoints that call expensive downstream services
                  When burst is acceptable (bursty client = legitimate use)
When NOT to Use:  Strict constant-rate requirement (use Leaking Bucket)
                  Fine-grained per-operation rate limiting (use different strategies per endpoint)
Complexity:       Low
Based on Knowledge:  → Rate Limiting Algorithms (K4)
Used in Decisions:  → D5: Rate limiter algorithm selection
Related Tech Assets:→ Redis INCR + EXPIRE pattern
```

---

### P2: Consistent Hashing Ring

```
Name:             Consistent Hashing Ring
Category:         Scalability
Problem:          Adding or removing nodes in a distributed cache or data store causes
                  massive key remapping, invalidating most of the cache.
Solution:         1. Map both server IDs and data keys onto a hash ring (0 to 2^32)
                  2. Assign each physical server 100-200 virtual nodes on the ring
                  3. For each key, walk clockwise from key's hash position to find owning server
                  4. On server add/remove: only adjacent keys on ring are remapped
When to Use:      Distributed cache with dynamic node count (autoscaling)
                  Data partitioning where node count changes
                  Load balancing across stateful servers (session affinity)
When NOT to Use:  Fixed, static number of servers (mod-N is simpler)
                  When exact key distribution control is needed
Complexity:       Medium
Based on Knowledge:  → Consistent Hashing (K3)
Related Tech Assets:→ Sorted map / BST implementation of ring
```

---

### P3: Fanout on Write (Push Model)

```
Name:             Fanout on Write (Push Model)
Category:         Architecture
Problem:          Followers need to see a user's new post in their feed with minimal read latency.
Solution:         1. On post creation: look up all followers
                  2. Write the post ID to each follower's feed cache entry
                  3. Feed reads are O(1) — just read from pre-computed cache
When to Use:      Users have bounded follower counts (< 10K)
                  Read performance is the priority (social feed, timeline)
                  Majority of users are active (cache writes are not wasted)
When NOT to Use:  User has millions of followers (celebrity problem)
                  Most users are inactive (wastes write operations on inactive feed caches)
Complexity:       Medium
Based on Knowledge:  → Fanout Strategies (K13)
                    → CDN Strategy & Cache Layers (K15)
Used in Decisions:  → D2: Real-time connection strategy
```

---

### P4: Fanout on Read (Pull Model)

```
Name:             Fanout on Read (Pull Model)
Category:         Architecture
Problem:          Pre-computing feeds for all followers wastes resources for inactive users
                  and overloads writes for high-follower-count users.
Solution:         1. User post is written only to author's post store
                  2. On feed read: query all followed users' recent posts
                  3. Merge and sort by recency in the application layer
                  4. Optionally cache the merged result per user for short TTL
When to Use:      Users have very high follower counts (celebrities)
                  Low active-user ratio (most users don't read regularly)
                  Feed freshness is critical (cannot tolerate stale pre-computed data)
When NOT to Use:  High-frequency feed reads (too many N calls per read)
                  Users follow many active users (fan-in too large at read time)
Complexity:       Low (write path) / High (read path)
Based on Knowledge:  → Fanout Strategies (K13)
```

---

### P5: Hybrid Fanout

```
Name:             Hybrid Fanout
Category:         Architecture
Problem:          Pure push wastes writes on celebrities; pure pull makes reads slow for
                  regular users.
Solution:         1. Classify users: regular (< N followers) vs. celebrity (≥ N)
                  2. Regular user posts: fanout on write (push to all followers' caches)
                  3. Celebrity posts: fanout on read (stored in author's post DB only)
                  4. Feed assembly: merge pre-computed cache + freshly-fetched celebrity posts
                  5. Threshold N: typically 10,000–100,000 (tune per system)
When to Use:      Social platform with power-law follower distribution
                  Mix of celebrity and regular users
                  Optimization needed at scale
When NOT to Use:  Uniform follower distribution (either pure push or pull is simpler)
Complexity:       High (dual path + classification logic + feed merge)
Based on Knowledge:  → Fanout Strategies (K13)
                    → CDN Strategy & Cache Layers (K15)
```

---

### P6: Event Sourcing Pattern

```
Name:             Event Sourcing Pattern
Category:         Architecture
Problem:          Traditional CRUD loses history. Cannot audit "what happened", cannot
                  replay to recover from bugs, cannot derive different projections from same data.
Solution:         1. Define events for all state changes (OrderPlaced, PaymentReceived, etc.)
                  2. Append events to immutable event log (never update/delete)
                  3. Current state = fold (reduce) over event log
                  4. Create snapshots periodically to avoid full replay on every read
                  5. Build read projections from event stream for query optimization
When to Use:      Financial systems requiring audit trail
                  Systems needing temporal queries ("state at time T")
                  Systems where bug fixes require reprocessing historical data
                  Systems needing multiple read models from same source data
When NOT to Use:  Simple CRUD with no audit/replay requirement (over-engineering)
                  Real-time writes where event schema evolution is unmanageable
                  Small systems where snapshot + versioned DB is sufficient
Complexity:       High
Based on Knowledge:  → Event Sourcing (K10)
                    → Message Queue Internals (K18)
Related Tech Assets:→ Append-only event table schema
                    → Snapshot + replay recovery pattern
```

---

### P7: Scatter-Gather

```
Name:             Scatter-Gather
Category:         Distributed Systems
Problem:          A query cannot be served from a single node — data is partitioned across
                  multiple shards and must be combined.
Solution:         1. Coordinator receives query
                  2. Scatter: broadcast sub-query to all relevant shards in parallel
                  3. Gather: collect responses, merge/sort/reduce
                  4. Return merged result to client
When to Use:      Top-K queries across sharded data (leaderboard, trending topics)
                  Search across multiple shards
                  Aggregations where data is partitioned by key
When NOT to Use:  Query can be routed to single shard (use direct routing instead)
                  N shards is too large (latency = max shard latency + merge time)
Complexity:       Medium
Based on Knowledge:  → Database Sharding Strategies (K16)
                    → Consistent Hashing (K3)
```

---

### P8: Write-Ahead Log (WAL)

```
Name:             Write-Ahead Log (WAL)
Category:         Resilience
Problem:          In-memory state is lost on crash. WAL provides durability by recording
                  every change to persistent storage before applying it to in-memory state.
Solution:         1. Before modifying in-memory state: append the change to WAL
                  2. WAL is append-only sequential writes (fast on disk)
                  3. On crash recovery: replay WAL from last checkpoint to restore state
                  4. Snapshot + WAL: periodically snapshot state, only replay WAL since snapshot
When to Use:      Any system with in-memory state that must survive crashes
                  Databases (PostgreSQL uses WAL), message queues (Kafka segments)
                  Financial systems (stock exchange event store)
When NOT to Use:  Stateless systems (no state to restore)
                  Systems where replay would take too long (use snapshots + short WAL)
Complexity:       Medium
Based on Knowledge:  → Event Sourcing (K10)
                    → LSM Tree & SSTables (K17)
```

---

### P9: Geohash Bucketing

```
Name:             Geohash Bucketing
Category:         Data
Problem:          Nearby location search requires efficient spatial indexing — scanning
                  all businesses by lat/lon is O(n).
Solution:         1. Convert all business locations to geohash strings (precision 6 = ~1km)
                  2. Index geohash as a regular string column in DB or Redis
                  3. For search: convert user location to geohash, query 9 cells (self + 8 neighbors)
                  4. Filter exact results by haversine distance
                  5. If insufficient results: expand to precision 5 (larger cells)
When to Use:      Nearby search (restaurants, drivers, events)
                  Static or semi-static business locations
                  Moderate scale (100M businesses)
When NOT to Use:  Very high update frequency (e.g., moving vehicles — use quadtree or H3)
                  Need irregular region shapes (use Google S2)
Complexity:       Low
Based on Knowledge:  → Geospatial Indexing (K9)
```

---

### P10: Snowflake ID Generation

```
Name:             Snowflake ID Generation
Category:         Distributed Systems
Problem:          Multiple services need to generate globally unique, time-sortable IDs
                  without coordination, database auto-increment, or UUID randomness.
Solution:         1. Assign each datacenter a 5-bit ID, each machine a 5-bit ID
                  2. Combine: [41-bit timestamp][5-bit DC][5-bit machine][12-bit sequence]
                  3. On each call: increment sequence counter; reset to 0 on new millisecond
                  4. On clock skew (clock going backward): wait until time advances
                  5. IDs are 64-bit integers, time-sortable, no coordination needed
When to Use:      High-throughput ID generation across distributed services
                  Need time-sortable IDs for range queries
                  Want to avoid DB auto-increment bottleneck
When NOT to Use:  Need strictly sequential IDs (use DB sequence)
                  Machine count exceeds 1,024 (expand machine bits)
                  Clock synchronization is unreliable (consider ULID instead)
Complexity:       Low
Based on Knowledge:  → Distributed Unique ID Generation (K5)
```

---

### P11: Hosted Payment Page

```
Name:             Hosted Payment Page
Category:         API Design
Problem:          Processing raw credit card data requires PCI-DSS Level 1 compliance
                  (expensive, complex, high audit burden).
Solution:         1. Redirect user to PSP's (Stripe, PayPal) hosted payment page
                  2. PSP collects and tokenizes card data directly
                  3. PSP returns payment token to your system
                  4. Your system calls PSP API with token to execute charge
                  5. Your system never touches raw card data — PCI scope eliminated
When to Use:      Any system processing credit card payments
                  Team lacks security expertise for PCI-DSS compliance
                  Speed to market is important
When NOT to Use:  Need fully custom payment UI (use PSP's JavaScript SDK instead)
                  Enterprise with existing PCI-DSS compliance (direct API may be better)
Complexity:       Low
Based on Knowledge:  → Idempotency in Distributed Systems (K20)
                    → Double-Entry Ledger System (K23)
```

---

### P12: Dead Letter Queue (DLQ) with Reconciliation

```
Name:             Dead Letter Queue (DLQ) with Reconciliation
Category:         Resilience
Problem:          Some messages permanently fail processing (bad data, downstream unavailable).
                  Without DLQ, the consumer blocks or loses data; without reconciliation,
                  financial discrepancies go undetected.
Solution:         1. Consumer retries with exponential backoff (3-5 attempts)
                  2. After max retries: route message to DLQ topic
                  3. Alert on DLQ size threshold (PagerDuty)
                  4. Monitor DLQ: inspect, fix root cause, replay from DLQ
                  5. For financial systems: run end-of-day reconciliation
                     Compare internal ledger against PSP settlement files
                     Any discrepancy → trigger investigation
When to Use:      Any Kafka consumer processing financial or critical events
                  Any system where missed messages need audit trail
When NOT to Use:  Non-critical events where loss is acceptable (discard instead of DLQ)
Complexity:       Low–Medium
Based on Knowledge:  → Message Queue Internals (K18)
                    → Idempotency in Distributed Systems (K20)
Related Patterns:  → P15: Idempotency Key
```

---

### P13: Saga Pattern

```
Name:             Saga Pattern
Category:         Resilience
Problem:          How to maintain data consistency across multiple services without a
                  distributed lock or 2PC, which blocks on coordinator failure?
Solution:         Break a long-running transaction into a sequence of local transactions,
                  each publishing an event. On failure, execute compensating transactions
                  in reverse to undo committed steps.

                  CHOREOGRAPHY SAGA:
                  Each service listens for events and publishes its own.
                  No central coordinator — each service knows what to do next.
                  Pro: Loose coupling. Con: Hard to visualize the overall flow.

                  ORCHESTRATION SAGA:
                  A central orchestrator sends commands to each service and awaits replies.
                  Pro: Easy to trace full flow. Con: Orchestrator is a SPOF / bottleneck.

                  COMPENSATING TRANSACTIONS:
                  Every step must have a defined compensation (undo) action.
                  Example (payment):
                    Step 1: ReserveBalance → Compensation: ReleaseBalance
                    Step 2: ChargeCard     → Compensation: RefundCard
                    Step 3: UpdateLedger  → Compensation: ReverseLedgerEntry

When to Use:      Multi-service workflows where each service has a local DB
                  Eventually consistent outcomes are acceptable
                  Payment, order fulfillment, booking workflows
When NOT to Use:  Single DB (use local ACID transaction instead)
                  Strong consistency required between services at commit time
Complexity:       High (compensation logic per step + idempotency required)
Based on Knowledge:  → Distributed Transactions — 2PC, Saga, TC/C (K11)
                    → Idempotency in Distributed Systems (K20)
```

---

### P14: Transactional Outbox

```
Name:             Transactional Outbox
Category:         Messaging
Complexity:       Medium
Problem:          How to guarantee that a domain event is published to a message broker
                  if and only if the corresponding database write succeeds? Direct publish
                  after DB commit can lose events on crash between the two operations.
Solution:         1. Within the same DB transaction: write business data AND insert an
                     "outbox" event record into an outbox table
                  2. A separate relay process (poller or CDC) reads the outbox table
                     and publishes unpublished events to Kafka/queue
                  3. On successful publish, mark event as published (or delete row)

                  Schema:
                    outbox (id, aggregate_type, aggregate_id, event_type,
                            payload JSONB, created_at, published_at)

                  Relay options:
                  - Polling relay: SELECT WHERE published_at IS NULL every N seconds
                  - CDC (Debezium): read DB WAL, zero-poll latency, no extra queries

When to Use:      Any write that must atomically produce a Kafka/queue event
                  Payments, orders, inventory changes with event sourcing
When NOT to Use:  Event loss is acceptable (fire-and-forget metrics/logs)
Complexity:       Medium (outbox table + relay process or CDC setup)
Based on Knowledge:  → Message Queue Internals — WAL, Partitions, ISR (K18)
                    → Event Sourcing (K10)
```

---

### P15: Idempotency Key

```
Name:             Idempotency Key
Category:         Resilience
Problem:          How to safely retry a mutating operation (payment, order creation)
                  without duplicating its effect when retries happen due to network
                  timeouts or at-least-once delivery?
Solution:         1. Client generates a UUID per logical operation attempt
                  2. Client sends the UUID in a header (e.g., Idempotency-Key)
                  3. Server checks the key in an idempotency_keys table before processing
                  4. If found: return the cached result immediately (no re-processing)
                  5. If not found: process, store result with key, return result
                  6. Key expires after a safe window (e.g., 24–48 hours)

                  Schema:
                    idempotency_keys (key VARCHAR PK, result JSONB,
                                      created_at TIMESTAMPTZ, expires_at TIMESTAMPTZ)

                  Variant — DB constraint approach:
                  - UNIQUE constraint on natural key (order_id, payment_id)
                  - Duplicate insert raises constraint violation
                  - Application catches violation and returns existing record

When to Use:      Any API endpoint that creates or mutates financial/critical data
                  Kafka consumers processing payment or order events
                  Any operation exposed to retries
When NOT to Use:  Read-only endpoints (already idempotent by nature)
                  Extremely high-volume non-critical events (use DB constraint instead)
Complexity:       Low (one extra table + pre-process key lookup)
Based on Knowledge:  → Idempotency in Distributed Systems (K20)
                    → Distributed Transactions — 2PC, Saga, TC/C (K11)
```

---

### P16: Async Parallel DB Coordinator

```
Name:             Async Parallel DB Coordinator
Category:         DB Performance
Problem:          A coordinator method fires 2+ independent DB calls sequentially.
                  Total latency = sum of all calls. Under concurrency, threads block on I/O
                  and the connection pool exhausts.
Solution:         1. Complete serial prerequisites (shared context resolution, initial query)
                  2. Identify all independent DB calls (no data dependency)
                  3. Create one DbContext per task from IDbContextFactory
                  4. Fire all tasks via Task.WhenAll
                  5. Await results and assemble in memory — zero DB calls in assembly
                  6. Expose sync wrapper; migrate callers incrementally
When to Use:      Coordinator calls 2+ independent DB operations sequentially
                  I/O wait % > 80% on hot path
                  Sequential latency > 300ms
When NOT to Use:  Calls have data dependencies (use sequential await instead)
                  Only 1 DB call — parallelism overhead not worth it
                  < 10 req/s low concurrency — sequential async sufficient
Complexity:       Medium
Based on Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
                     → Connection Pool Math
BotE Impact:      Sequential: latency = t1 + t2 + t3 + t4
                  Example: 400+300+250+200 = 1,150ms
                  Parallel:  latency = max(t1, t2, t3, t4) = 400ms  (-65%)
                  Pool pressure unchanged — same total queries, shorter hold time per request
Decision Rule:    2+ independent calls + hot-path → Async Parallel DB Coordinator
                  Shared _context across tasks → BLOCK — use IDbContextFactory
                  Calls have dependency chain → sequential await
Source:           incident2.cs GetSubOrderAsync, 2026-03-27
```

---

### P17: Batch Query (WHERE IN)

```
Name:             Batch Query (WHERE IN)
Category:         DB Performance
Stack:            EF Core / SQL
Summary:          Replace N serial single-row queries inside a loop with one batched
                  WHERE column IN (...) query. Eliminates per-iteration round-trips.
When to Use:      Loop issues N queries for N known IDs (N+1 pattern detected).
                  IDs are available before the loop starts.
When NOT to Use:  IDs are unknown until each step completes (dependency chain).
                  N is extremely large (> ~10,000) — use pagination instead.
Complexity:       Low
BotE Impact:      N queries × avg_latency → 1 query × avg_latency  (e.g. 10×20ms → 20ms)
Decision Rule:    Loop over a fixed set of IDs hitting the DB? → Batch query first.
Based on Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Source:           incident2.cs Phase 2, 2026-03-27
```

---

### P18: Eager Graph Loading (.Include + AsNoTracking)

```
Name:             Eager Graph Loading
Category:         DB Performance
Stack:            EF Core
Summary:          Use .Include() to load related entities in a single JOIN query instead of
                  triggering lazy-load calls per entity. Add .AsNoTracking() on all read-only
                  paths to skip EF change-tracking overhead.
When to Use:      Read-only query that accesses navigation properties.
                  Lazy loading is enabled and causing N+1 on hot paths.
When NOT to Use:  Entity will be modified and saved (tracking required).
                  Related set is huge and only partially needed (use projection instead).
Complexity:       Low
Decision Rule:    Read-only + navigation property accessed? → .Include().AsNoTracking()
                  Hot path + EF tracking overhead visible in profiler? → AsNoTracking mandatory
Based on Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Source:           incident2.cs Phase 1, 2026-03-27
```

---

### P19: Coordinator-Level Resolution

```
Name:             Coordinator-Level Resolution
Category:         API Design
Stack:            Any
Summary:          Resolve shared context (canonical IDs, configs, lookups) once at the
                  coordinator method. Pass the resolved value into sub-methods as a parameter.
                  Never re-resolve inside each sub-call or loop iteration.
When to Use:      Multiple sub-methods need the same derived value (e.g. canonical OrderId).
                  Sub-methods currently each resolve it independently via DB or service call.
When NOT to Use:  Sub-methods intentionally need independent resolution (e.g. for isolation).
Complexity:       Low
Decision Rule:    Two+ sub-methods resolve the same value? → Resolve once, pass down.
Source:           incident2.cs Phase 1, 2026-03-27
```

---

### P20: Bulk Load Then Map

```
Name:             Bulk Load Then Map
Category:         DB Performance
Stack:            EF Core / Any ORM
Summary:          Load all required rows in one query, then map/group them in memory.
                  Avoids per-entity DB calls inside a mapping loop.
When to Use:      Mapping loop calls DB per item to enrich or cross-reference.
                  All needed rows share a common parent key (e.g. SourceOrderId).
When NOT to Use:  Dataset is too large to hold in memory.
                  Rows are independent with no shared key for bulk fetch.
Complexity:       Low
Decision Rule:    Mapping loop hits DB per item? → Bulk load by parent key, then Dictionary lookup.
Based on Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Source:           incident2.cs Phase 3, 2026-03-27
```

---

### P21: Per-Table Storage Hygiene

```
Name:             Per-Table Storage Hygiene
Category:         DB Performance
Stack:            PostgreSQL
Summary:          Override autovacuum scale_factor per-table for any table > 500K rows, and run
                  REINDEX CONCURRENTLY after any high-churn period to restore B-tree density.
                  Default autovacuum settings are calibrated for small tables and silently fail large ones.
When to Use:      Any PostgreSQL table expected to exceed 500K rows.
                  Tables with regular UPDATE or DELETE workloads (stock, orders, adjustments).
                  After bulk migrations that delete or overwrite large row counts.
                  When dead_ratio > 5% or last_autovacuum IS NULL on a large table.
                  When index reusable_pages / total_pages > 30%.
When NOT to Use:  Read-only tables (no dead tuples generated).
                  Tables < 50K rows with infrequent writes (default autovacuum is sufficient).
Complexity:       Low
Decision Rule:    dead_ratio > 10% AND last_autovacuum IS NULL → VACUUM immediately + fix scale_factor
                  index reusable / total > 30%               → REINDEX CONCURRENTLY
                  table rows > 500K with default scale_factor → ALTER TABLE scale_factor = 0.01
Based on Knowledge:  → K26: PostgreSQL MVCC and Dead Tuples
                     → K27: Autovacuum Scale Factor Trap for Large Tables
Used in Incidents:   → I2: PostgreSQL Dead Tuple Bloat — stockadjustments (2026-03-30)
Used in Decisions:   → D12: REINDEX CONCURRENTLY vs VACUUM FULL
Related Tech Assets: → TA12: Dead Tuple Health Monitor Query
                     → TA13: Per-Table Autovacuum Configuration SQL
                     → TA14: REINDEX CONCURRENTLY Script
Source:           stockadjustments incident, spc_inventory, 2026-03-30
```

---

