# KOS — Decision Log

> Cross-linked per the Incident → Knowledge → Pattern → Decision → Reuse loop.

---

## DECISION LOG

---

### D1: Database Type Selection for Different Workloads

```
Title:            Database type selection for different workloads
Context:          Different systems require different data models, consistency guarantees,
                  and access patterns. Wrong DB choice leads to performance problems or
                  schema constraints.
Problem:          Given a new system, which database type should be used?
Options Considered:
  A. Relational DB (MySQL, PostgreSQL)
     Pros: ACID, joins, mature ecosystem, familiar
     Cons: Horizontal scaling complex, schema changes costly, poor at unstructured data
  B. Wide-column / NoSQL (Cassandra, DynamoDB, HBase)
     Pros: Horizontal scale-out, flexible schema, high write throughput
     Cons: No joins, eventual consistency (usually), limited query patterns
  C. Key-Value Store (Redis, DynamoDB)
     Pros: O(1) reads/writes, sub-millisecond, simple
     Cons: No complex queries, no joins, limited data structures
  D. Time-Series DB (InfluxDB, Prometheus)
     Pros: Optimized for time-range queries, downsampling, 10-100x faster than RDBMS
     Cons: Limited to time-series workloads, no complex joins
  E. Search Engine (Elasticsearch)
     Pros: Full-text search, faceted queries, near real-time
     Cons: Not ACID, complex to manage, expensive at scale
Decision:         Match DB to primary access pattern:
Trade-offs:       No single DB is optimal for all access patterns.
Expected Outcome: Right DB → 10-100x performance improvement vs. wrong DB choice.
Rules:
  ACID + complex joins + bounded scale?   → Relational (MySQL/PostgreSQL)
  High-volume time series?                → InfluxDB/Prometheus
  Chat/messaging (sorted access by time)? → Cassandra/HBase (wide-column, time-sorted)
  Cache + session + leaderboard?          → Redis
  Document search?                        → Elasticsearch
  Object/file storage?                    → S3/Blob (not a DB)
  Financial ledger (audit + ACID)?        → Relational + Event Sourcing
Related Knowledge:  → Database Sharding Strategies (K16)
                   → LSM Tree & SSTables (K17)
                   → Time-Series Database Design (K22)
Date:             Derived from System Design Interview Vol. 1 & 2
```

---

### D2: Real-Time Connection Strategy

```
Title:            Real-time connection strategy
Context:          System requires server-to-client or bidirectional communication with
                  varying latency, frequency, and directionality requirements.
Problem:          Which real-time protocol should be used?
Options Considered:
  A. Short Polling (HTTP)
     Pros: Simple, stateless, works everywhere
     Cons: Latency = polling interval, wasteful empty responses
  B. Long Polling (HTTP)
     Pros: Lower empty responses, simpler than WebSocket
     Cons: HTTP overhead per message, not bidirectional
  C. WebSocket
     Pros: Low latency, full-duplex, low per-message overhead
     Cons: Stateful (complex scaling), persistent connection memory overhead
  D. Server-Sent Events (SSE)
     Pros: Simple one-way push, built on HTTP, auto-reconnect
     Cons: One-way only (server → client)
Decision:         Match to use case:
Trade-offs:       WebSocket requires sticky sessions or shared connection routing.
Rules:
  Chat / collaborative editing / live location? → WebSocket
  Infrequent server push (file sync, notifications)? → Long Polling
  Live one-way feed (stock tickers, scores)? → SSE
  Simple polling acceptable (> 1 second interval)? → Short Polling
Related Knowledge:  → WebSocket vs HTTP Polling vs Long Polling (K14)
Date:             Derived from System Design Interview Vol. 1 & 2 (Chat, Nearby Friends, Maps)
```

---

### D3: Storage Strategy — Replication vs Erasure Coding

```
Title:            Storage strategy: Replication vs Erasure Coding
Context:          Distributed storage system needs durability with cost efficiency.
Problem:          How to balance storage overhead with durability and performance?
Options Considered:
  A. 3× Replication
     Pros: Simple, fast recovery (copy from replica), fast reads
     Cons: 200% overhead (3 bytes per byte stored)
  B. Erasure Coding (4+2 or 8+4)
     Pros: ~50% overhead (much cheaper), tolerates multiple failures
     Cons: CPU-intensive encode/decode, slower recovery (reconstruct from fragments)
  C. Hybrid (replicate hot, erasure-code cold)
     Pros: Optimal cost at each temperature tier
     Cons: Data lifecycle management complexity
Decision:         Hybrid is optimal at scale:
Trade-offs:       Erasure coding saves ~50% storage vs. replication at the cost of recovery speed.
Rules:
  Hot data (accessed daily, low latency reads)? → 3× Replication
  Cold data (accessed < monthly)?               → Erasure coding (4+2)
  Storage cost is primary constraint?            → Erasure coding
  Fast recovery / simple operations?             → Replication
Related Knowledge:  → Erasure Coding vs Replication (K19)
Date:             Derived from System Design Interview Vol. 2, S3-like Object Storage
```

---

### D4: Distributed Transaction Strategy

```
Title:            Distributed transaction strategy
Context:          Operation spans multiple services or databases that must succeed or
                  fail together.
Problem:          Which distributed transaction mechanism should be used?
Options Considered:
  A. Local DB Transaction
     Pros: ACID, simple, no coordination
     Cons: Only works for single DB
  B. Two-Phase Commit (2PC)
     Pros: Strict atomicity, all-or-nothing
     Cons: Blocking on coordinator failure, slow (2 round trips)
  C. Saga (Choreography)
     Pros: Decentralized, resilient, each service autonomous
     Cons: Eventual consistency, compensating transaction complexity
  D. Saga (Orchestration)
     Pros: Clear flow control, easier to debug
     Cons: Orchestrator becomes a bottleneck/SPOF
  E. TC/C (Try-Confirm/Cancel)
     Pros: Application-defined semantics, no blocking
     Cons: Must implement cancel logic for every operation
Decision:         Minimum sufficient for correctness:
Trade-offs:       Higher consistency = more coordination = lower availability.
Rules:
  Single DB?                                      → Local transaction
  2-3 services, loss-tolerant?                    → Choreography Saga + idempotency
  Financial payment across multiple services?     → TC/C + idempotency + reconciliation
  Complex multi-step workflow?                    → Orchestration Saga
  Strict ACID across few resources?               → 2PC (accept blocking risk)
Related Knowledge:  → Distributed Transactions — 2PC, Saga, TC/C (K11)
                   → Idempotency in Distributed Systems (K20)
Related Pattern:   → P13: Saga Pattern
                   → P15: Idempotency Key
Date:             Derived from System Design Interview Vol. 2, Payment System, Hotel Reservation, Digital Wallet
```

---

### D5: Rate Limiter Algorithm Selection

```
Title:            Rate limiter algorithm selection
Context:          API needs rate limiting to protect against abuse and resource exhaustion.
Problem:          Which algorithm provides the right balance of accuracy, memory, and burst handling?
Options Considered:
  A. Token Bucket: burst-friendly, complex tuning
  B. Leaking Bucket: stable rate, may starve new requests
  C. Fixed Window Counter: simple, edge-case vulnerability
  D. Sliding Window Log: accurate, high memory
  E. Sliding Window Counter: memory-efficient, ~0.003% error
Decision:         Token Bucket for most APIs; Sliding Window Counter for high-scale.
Trade-offs:       Accuracy vs. memory vs. burst tolerance.
Rules:
  General API with burst acceptable?        → Token Bucket
  Stable processing required?               → Leaking Bucket
  Simple per-minute quotas?                 → Fixed Window Counter
  High accuracy needed?                     → Sliding Window Log
  Balance accuracy + memory at scale?       → Sliding Window Counter
Related Knowledge:  → Rate Limiting Algorithms (K4)
Related Pattern:   → P1: Token Bucket Rate Limiting
Date:             Derived from System Design Interview Vol. 1, Chapter 4
```

---

### D6: ID Generation Strategy at Scale

```
Title:            ID generation strategy at scale
Context:          Distributed system needs globally unique IDs across multiple services.
Problem:          How to generate IDs that are unique, performant, and ideally sortable?
Options Considered:
  A. DB Auto-Increment: simple, sequential, but single point of failure
  B. UUID v4: no coordination, random, but 128-bit, non-sortable
  C. Ticket Server: centralized, SPOF, network hop
  D. Snowflake: 64-bit, time-sortable, no coordination, requires NTP
  E. ULID: like Snowflake but 128-bit, monotonic, URL-safe
Decision:         Snowflake for most distributed systems.
Trade-offs:       Coordination overhead vs. ordering guarantees vs. clock dependency.
Rules:
  Need time-sortable 64-bit IDs, distributed?  → Snowflake
  Need random non-guessable IDs?               → UUID v4
  Need strictly sequential?                    → DB sequence (accept single server)
  Clocks unreliable?                           → ULID (monotonic without strict NTP)
Related Knowledge:  → Distributed Unique ID Generation — Snowflake (K5)
Related Pattern:   → P10: Snowflake ID Generation
Date:             Derived from System Design Interview Vol. 1, Chapter 7
```

---

### D7: Pull vs Push Model for Metrics Collection

```
Title:            Pull vs Push model for metrics collection
Context:          Infrastructure monitoring system needs to collect metrics from thousands
                  of servers.
Problem:          Should the monitoring system pull metrics from services, or should services push to it?
Options Considered:
  A. Pull Model (Prometheus-style)
     Pros: Easy debugging (query endpoint manually), health check built-in, simpler at scale
     Cons: Services must expose HTTP endpoint, firewall rules needed for collector
  B. Push Model (StatsD/DataDog-style)
     Pros: Works for short-lived jobs, serverless, firewall-friendly
     Cons: Service must know collector address, can overwhelm collector
Decision:         Pull model for infrastructure; Push for short-lived/serverless.
Trade-offs:       Pull is more observable but requires network accessibility.
Rules:
  Long-lived services in same network?       → Pull model
  Short-lived jobs / serverless?             → Push model
  Strict firewall (can't expose ports)?      → Push model
  Need health check as side effect?          → Pull model
Related Knowledge:  → Message Queue Internals — WAL, Partitions, ISR (K18)
                   → Stream vs Batch Processing (K12)
Date:             Derived from System Design Interview Vol. 2, Metrics Monitoring System
```

---

### D8: Use IDbContextFactory for Parallel GetSubOrderAsync

```
Title:            Use IDbContextFactory for Parallel GetSubOrderAsync
Context:          GetSubOrder Phase 4 — async parallelization of 3+ independent DB calls.
                  EF Core DbContext is not thread-safe. Task.WhenAll requires concurrent access.
Problem:          How to enable parallel DB queries in EF Core without race conditions?
Options:
  A. IDbContextFactory    Each task creates its own DbContext. Explicit, safe, EF Core recommended.
                          BotE: 400ms latency, N connections per request (N = parallel tasks).
  B. IServiceScopeFactory Create a new DI scope per task. More boilerplate, same safety as A.
                          Useful when more than DbContext needed per scope.
  C. Shared _context      Reuse existing scoped DbContext across tasks.
                          BLOCKED — not thread-safe. Race condition guaranteed.
Decision:         Option A — IDbContextFactory
                  Cleanest API, no extra DI scope, await using disposes cleanly.
                  Factory is Singleton; DbContext instances are scoped per task.
Expected Outcome: P50: ~1,500ms → ~400ms (-73%)
                  Concurrency ceiling: ~140 req → ~400+ req
Actual Outcome:   N=1 (single sub-order): P50 878ms → 805ms (-8%). AllocatedKB: 768 KB → 1,100 KB (+43%).
                  "All" mode (N≈10): P50 1,242ms → 1,117ms (-10%). AllocatedKB: 1,538 KB → 1,980 KB (+29%).
                  AllocatedKB overhead: +332 KB (N=1) / +442 KB (All) — 4 factory DbContext instances per call.
                  Limited gain because GetSubOrderMessageFromBatch (bulk serial load) dominates ~900ms.
                  Total from baseline 5,048ms: Phase 1–3 → Phase 4 = 1,117ms (-78% total).
Watch out for:    Connection pool growth: N parallel tasks × concurrent requests.
                  Monitor pool size: pool ≥ expected_concurrent_requests × parallel_tasks.
                  await using var scope: factory DbContext must be declared at coordinator scope,
                  NOT inside nested if/for/while blocks — disposed at block exit, before Task.WhenAll runs.
                  See D15 for the scope pitfall rule.
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P16: Async Parallel DB Coordinator
                    → P23: Parallel Split Compiled Query
Related Decision:   → D15: await using var Scope Rule (pitfall when using this pattern)
Related Incidents:  → I1: GetSubOrder API Latency Spike
Date:             2026-03-27
Measured:         2026-04-02
```

---

### D9: Eager Load via .Include() over Lazy Entry().Load() on Hot-Path Reads

```
Title:            Eager Load via .Include() over Lazy Entry().Load() on Hot-Path Reads
Context:          GetSubOrder Phase 1 — EF Core lazy loading triggered N individual DB calls
                  inside mapping loops (one Entry().Reference().Load() per entity iteration).
Problem:          How to load related entities without per-entity DB round-trips?
Options:
  A. Lazy load via Entry().Reference().Load()
     Each navigation property access triggers a separate SELECT.
     N entities = N extra DB calls. Compounds with connection pool pressure.
  B. Eager load via .Include()
     Single JOIN query loads entity + related data together.
     No extra DB calls in mapping loop. AsNoTracking() removes change-tracking overhead.
Decision:         Option B — .Include().AsNoTracking() on all hot-path read queries.
                  Never call Entry().Reference().Load() inside a loop on a read-only path.
Expected Outcome: Eliminated N extra queries per GetSubOrder call (N = number of sub-order items).
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P18: Eager Graph Loading
Related Incidents:  → I1: GetSubOrder API Latency Spike
Date:             2026-03-27
```

---

### D10: Resolve Canonical OrderId Once at Coordinator Level

```
Title:            Resolve Canonical OrderId Once at Coordinator Level
Context:          GetSubOrder Phase 1 — each sub-method (GetOrderMessagePayments,
                  GetOrderPromotion, GetRewardItems) independently resolved the canonical
                  OrderId via IsExistOrderReference(), causing 2–3 redundant DB calls per request.
Problem:          How to avoid repeated resolution of the same derived value across sub-calls?
Options:
  A. Each sub-method resolves independently
     Simple, self-contained methods.
     Costs 2–3 extra DB calls per sub-method. At 3 sub-methods = 6–9 wasted queries.
  B. Resolve once at coordinator, pass resolved ID as parameter
     Coordinator calls IsExistOrderReference() once, passes resolvedOrderId down.
     Sub-methods receive canonical ID — no DB resolution needed internally.
Decision:         Option B — resolve once at GetSubOrder coordinator, pass resolvedOrderId.
                  Sub-methods renamed to *Internal(resolvedOrderId) to enforce the contract.
Expected Outcome: Eliminated 6–9 redundant resolution queries per request.
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P19: Coordinator-Level Resolution
Related Incidents:  → I1: GetSubOrder API Latency Spike
Date:             2026-03-27
```

---

### D11: Incremental Refactor — Batch First (Phase 1–3), Async Parallel Second (Phase 4)

```
Title:            Incremental Refactor — Batch First, Async Parallel Second
Context:          GetSubOrder had 33 queries/request causing connection pool exhaustion.
                  Two approaches available: sync batch refactor vs. full async rewrite.
Problem:          Should the fix be a single async rewrite or incremental phases?
Options:
  A. Full async rewrite in one pass
     Maximum performance gain immediately.
     High risk — large diff, harder to review, hard to isolate regressions.
  B. Incremental: sync batch refactor first (Phase 1–3), then async parallel (Phase 4)
     Phase 1–3 reduce query count from 33 → ~7 (sync, safe, reviewable).
     Phase 4 adds async parallelism on top of already-correct sync baseline.
     Each phase independently deployable and verifiable.
Decision:         Option B — incremental approach.
                  Phase 1–3 delivered ~750ms improvement. Phase 4 added further ~125ms ("All" mode).
                  Incremental diffs are easier to review, test, and roll back independently.
Expected Outcome: Phase 1–3: ~1,500ms → ~750ms. Phase 4: ~750ms → ~400ms. Total: -73%.
Actual Outcome:   Phase 1–3: 5,048ms → 1,242ms (-75%). Phase 4: 1,242ms → 1,117ms (-10%, "All" N≈10).
                  Phase 5: 1,117ms → 741ms (-34%) — parallel bulk SubOrder (split compiled queries).
                  Total: 5,048ms → 741ms (-85%). Best observed single run: 723ms.
                  Phase 4 gain smaller than estimated — GetSubOrderMessageFromBatch dominated ~900ms.
                  Phase 5 split into _bulkSubOrderHeaderQuery + _bulkSubOrderItemsQuery run via Task.WhenAll.
                  Actual Step 3 reduction: ~900ms → ~524ms (BotE predicted ~455ms; ~69ms gap = pool contention).
                  Next lever: IMemoryCache on GetStoreLocation (5-min TTL) to break below 500ms.
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P17: Batch Query (WHERE IN)
                   → P18: Eager Graph Loading
                   → P19: Coordinator-Level Resolution
                   → P20: Bulk Load Then Map
                   → P16: Async Parallel DB Coordinator
                   → P23: Parallel Split Compiled Query
Related Incidents:  → I1: GetSubOrder API Latency Spike
Date:             2026-03-27
Measured:         2026-04-02
```

---

### D12: REINDEX CONCURRENTLY vs VACUUM FULL vs Accept Reusable Pages

```
Title:            REINDEX CONCURRENTLY vs VACUUM FULL vs Accept Reusable Pages
Context:          After VACUUM on stockadjustments (4M rows, spc_inventory), 6 indexes retained
                  63% reusable pages (~1.07 GB). VACUUM marks pages "reusable" but does not
                  shrink the index file or compact the B-tree structure.
                  pkey index: 85% empty pages — every PK lookup traverses 6.7× more pages than needed.
Problem:          How to reclaim ~1.07 GB of index space and restore B-tree density
                  without taking the table offline in a production inventory system?
Scale (BotE):     Total index: 217,353 pages × 8KB = ~1.7 GB
                  Reusable:    137,400 pages × 8KB = ~1.07 GB wasted
                  pkey alone:  65,465 / 76,838 = 85% empty → 2.7× I/O overhead on all PK/FK scans
Options:
  A. REINDEX CONCURRENTLY (chosen)
     No table lock — reads and writes continue during rebuild.
     Rebuilds fresh compact index from live data only.
     Fully reclaims ~1.07 GB. Each index: ~5–20 min on 4M rows.
  B. VACUUM FULL
     EXCLUSIVE table lock — zero reads/writes for 10–60+ min. Unacceptable for production.
  C. Accept Reusable Pages
     Zero effort. B-tree stays sparse until pages naturally refill. Problem recurs next cycle.
Decision:         Option A — REINDEX CONCURRENTLY for all 6 indexes.
                  Only REINDEX builds a genuinely dense, compact B-tree. Non-blocking is mandatory.
Expected Outcome: Index size: ~1.7 GB → ~630 MB. B-tree density restored. 2–3× faster index scans.
Actual Outcome:   Index size: ~1.7 GB → 251 MB (-85%, reclaimed ~1.45 GB).
                  pkey: ~600 MB → 89 MB. dead_ratio: 14.50% → 0.00%.
                  Actual bloat was 85% — estimate was conservative (predicted 63%).
                  Additional finding: 4 of 6 indexes had idx_scan = 0 (potentially unused).
                  Monitor 30 days; consider dropping if still 0 to reduce write amplification.
Related Knowledge:  → K26: PostgreSQL MVCC and Dead Tuples
                    → K27: Autovacuum Scale Factor Trap for Large Tables
Related Pattern:    → P21: Per-Table Storage Hygiene
Related Incidents:  → I2: PostgreSQL Dead Tuple Bloat — stockadjustments
Date:             2026-03-30
```

---

### D13: Apply EF.CompileQuery to GetSubOrderMessage Bulk Query

```
Title:            Apply EF.CompileQuery to GetSubOrderMessage Bulk Query
Context:          heap dump (Order.API-3.dmp) showed 17,557 DynamicMethod objects consuming
                  ~6 MB of non-reclaimable static heap. Cause: the Phase 3 bulk query with
                  16 Include paths + AsSplitQuery was not precompiled — EF recompiled the
                  expression tree on every unique parameter set.
Problem:          Non-reclaimable static heap growing unboundedly. GC cannot reclaim
                  DynamicMethod/DynamicILGenerator/DynamicResolver objects in CompiledQueryCache.
Options:
  A. EF.CompileQuery static field (chosen)
     Extract bulk SubOrder query as private static readonly Func<DbContext, string[], string[], IEnumerable<T>>.
     Compiled exactly once on first call. Subsequent calls use cached IL.
     Cold start: ~106 MB / 5,849ms (one-time). Steady-state: no new DynamicMethod per call.
  B. Leave as-is
     Cache grows unbounded. Under load: thousands of DynamicMethod objects, 6–10+ MB static waste.
  C. Remove AsSplitQuery
     Eliminates split-query entries but reintroduces cartesian join explosion with 16 Include paths.
     Not viable — N×16 rows returned.
Decision:         Option A — EF.CompileQuery static field. EF Core 10 confirmed to support
                  AsSplitQuery in compiled queries.
Expected Outcome: DynamicMethod count reduced from 17,557 to ~50 (just this query's 16 split entries).
Actual Outcome:   DynamicMethod count 17,557 → 7,356 at higher load (load test). Stable ceiling
                  confirmed — remaining 7,356 = other queries across all service endpoints
                  each compiled once. Total static cache ~3.2 MB. No further growth.
                  AllocatedKB per call: 1,808 KB → 1,536 KB (-15%). P50: 1,579ms → 1,224ms (-22%).
Related Knowledge:  → K28: EF Core Compiled Query Cache and DynamicMethod Accumulation
Related Pattern:    → P22: EF Compiled Query Cache Management
Related Incidents:  → I1: GetSubOrder API Latency Spike
Related Tech Assets:→ TA15: EF.CompileQuery Static Field Template
Date:             2026-03-31
```

---

### D14: GetPackageTb — Consolidate 4 Queries to 1 + AsNoTracking on Per-Sub-Order Calls

```
Title:            GetPackageTb — Consolidate 4 Queries to 1 + AsNoTracking on Per-Sub-Order Calls
Context:          Code review of the 3 remaining per-sub-order methods (GetStoreLocation,
                  getPackageInfoByOrderAndSubOrder, GetPackageTb) triggered by heap dump
                  SqlBuffer accumulation investigation. Found GetPackageTb issuing 4 sequential
                  queries per sub-order: Any() + Max(CreatedDate) + Max(UpdatedDate) + ToList().
                  All 3 methods also missing AsNoTracking() on read-only paths.
Problem:          GetPackageTb: 4N DB round-trips instead of N. For N=10 sub-orders = 40 queries
                  instead of 10. Any() + Max queries add latency and hold SqlDataReader connections.
                  Missing AsNoTracking() on 3 methods generates unnecessary tracked entity copies.
Options:
  A. Single ToList() + in-memory Max (chosen)
     Load all rows once with AsNoTracking(). Compute Max(CreatedDate) and Max(UpdatedDate)
     in-memory using LINQ. Apply filter in-memory. Zero additional DB round-trips.
  B. Collapse to single OrderByDescending().Take() query
     Works if only the single latest row is needed. But original logic keeps all rows
     matching both MaxCreatedDate AND MaxUpdatedDate — multiple rows possible.
     Risk of behaviour change — chose Option A for safe equivalence.
Decision:         Option A — single ToList() + in-memory Max. Behaviour-safe refactor.
                  AsNoTracking() added to GetStoreLocation, getPackageInfoByOrderAndSubOrder,
                  GetPackageTb simultaneously.
Actual Outcome:   GetPackageTb: 4N → N queries (-75% query reduction for this method).
                  P50 improvement contribution: part of 1,579ms → 1,224ms (-22%) total.
                  AllocatedKB: 1,808 KB → 1,536 KB (-15%) — AsNoTracking reducing tracking overhead.
                  GC1 per 30 calls: dropped to 0 (was 0.3 after indexes).
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
                  → K28: EF Core Compiled Query Cache and DynamicMethod Accumulation
Related Pattern:    → P22: EF Compiled Query Cache Management
Related Incidents:  → I1: GetSubOrder API Latency Spike
Date:             2026-03-31
```

---

### D15: await using var Scope Rule — Factory DbContext Must Outlive Task.WhenAll

```
Title:            await using var Scope Rule — Factory DbContext Must Outlive Task.WhenAll
Context:          Phase 4 GetSubOrderAsync (target.cs). ctx4 was declared with await using var
                  inside the inner if block that conditionally created the rewardTask.
                  C# disposes await using variables at the end of the enclosing block (}).
                  Task.WhenAll had not yet awaited the task — ctx4 was disposed before the
                  async query ran, causing InvalidOperationException: The connection is closed.
Problem:          How to safely manage lifetime of factory-created DbContext instances when
                  the task using them is conditionally assigned inside a nested block?
Error signature:  System.InvalidOperationException: Invalid operation. The connection is closed.
                  Stack: SingleQueryingEnumerable.AsyncEnumerator.InitializeReaderAsync
                       → ExecuteReaderAsync → SqlCommand.ExecuteDbDataReaderAsync
Options:
  A. Declare await using var inside the if block (WRONG)
     Context disposed when if block exits. Task.WhenAll runs on a closed connection.
     → InvalidOperationException at await time.
  B. Declare all factory contexts at coordinator scope, before any conditional branching (CORRECT)
     Contexts declared alongside ctx1/ctx2/ctx3 before the if block.
     All contexts stay alive until after await Task.WhenAll completes.
     await using disposes them in reverse order after the coordinator method returns.
Decision:         Option B — always declare factory DbContext at coordinator scope.
Rule:             await using var ctx declared inside if/for/while block → disposed at block exit.
                  If the task using ctx outlives the block (e.g., assigned to outer variable,
                  passed to Task.WhenAll), ctx is already disposed when the task runs.
                  Fix: declare ALL parallel contexts together at coordinator scope, even if only
                  conditionally used. The unused context costs one connection open/close — acceptable.
Actual Outcome:   Bug confirmed by connection closed error. Fix (Option B) resolved error completely.
                  Restored full Phase 4 async parallel behaviour with zero connection errors.
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P16: Async Parallel DB Coordinator
                    → P23: Parallel Split Compiled Query
Related Decision:   → D8: Use IDbContextFactory for Parallel GetSubOrderAsync
Related Incidents:  → I1: GetSubOrder API Latency Spike
Date:             2026-04-01
```

---

## DECISION RULES

> Read this section when asked "when should I use X?", "is N too many?", "should I add a cache?",
> or any question that needs a concrete threshold or if/then judgment — not a pattern explanation.
> These rules are extracted from real incidents, KOS knowledge records, and architectural principles.
> They are meant to be fast answers, not full discussions.

---

### Index

| Domain | Rules |
|--------|-------|
| [KOS Cross-Linking](#kos-cross-linking) | Bidirectional link checklist — run after every new record |
| [DB Query & Performance](#db-query--performance) | N+1 threshold, batch size, chunking, AsNoTracking |
| [PostgreSQL Storage & Vacuum](#postgresql-storage--vacuum) | Autovacuum tuning, dead tuple thresholds, REINDEX |
| [EF Core](#ef-core) | When to use Include vs batch, projection, split query |
| [Kafka & Messaging](#kafka--messaging) | Retry count, DLQ routing, partition strategy, Outbox trigger |
| [Caching](#caching) | When to add cache, TTL, invalidation strategy |
| [Data Ingestion (ETL/FTP)](#data-ingestion-etlftp) | Staging trigger, validation gate, chunk size, ETL TX scope |
| [API Design](#api-design) | Pagination threshold, timeout, idempotency trigger |
| [Architecture Patterns](#architecture-patterns) | When to introduce CQRS, Saga, Repository, Circuit Breaker |
| [System Design](#system-design) | Microservice split trigger, event vs direct call, retry strategy |
| [Observability](#observability) | What to always log, alert thresholds, metric naming |
| [Code Review Flags](#code-review-flags) | Immediate flags, questions to always ask |
| [Distributed Systems](#distributed-systems--cap--consistency) | CAP, Consistent Hashing, ID Generation, Distributed Transactions |
| [Rate Limiting](#rate-limiting) | Algorithm selection, token bucket parameters |
| [Real-Time Connections](#real-time-connections) | WebSocket vs SSE vs polling |
| [Storage Strategy](#storage-strategy) | Replication vs erasure coding, DB type by workload |
| [Geospatial Indexing](#geospatial-indexing) | Geohash vs Quadtree, precision levels |
| [Financial Systems](#financial-systems) | Double-entry ledger, idempotency, PCI-DSS, reconciliation |
| [Scalability Thresholds](#scalability-thresholds-back-of-envelope-reference) | QPS formula, storage estimation, availability budgets |

---

### KOS Cross-Linking

```
When adding a NEW record (I#, K#, P#, D#, TA#), always run this checklist before saving:

[ ] 1. Does the new record reference existing records?
       → Add them to the new record's Related/Used in/Based on KV fields.

[ ] 2. Do those existing records need back-links to the new record?
       → Open each referenced file and add the new record's ID to their Related fields.
       → Common missed back-links:
           New P# added  → update I# Related Pattern
           New P# added  → update D# Related Pattern
           New I# added  → update K# Used in Incidents
           New D# added  → update I# Related Decisions
           New TA# added → update I# Related Tech Assets and P# Related Tech Assets

[ ] 3. Typo-check all IDs in Related fields (e.g. P26 vs P16 — a typo that points to a non-existent record)
       → Grep for the ID to confirm it exists before saving.

[ ] 4. Measured/Date fields current?
       → Update Measured date on any D# whose Actual Outcome changed.
       → Update Status on I# if the incident progressed.

Root cause of missed links: new record outbound links are written while writing —
existing record inbound links require going back and editing already-saved files.
The only fix is a forced review pass over all referenced records after the new record is saved.
```

---

### DB Query & Performance

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

### PostgreSQL Storage & Vacuum

```
Autovacuum scale_factor by table size:
  table rows > 5M   → autovacuum_vacuum_scale_factor = 0.005  (trigger at ~0.5% dead rows)
  table rows > 500K → autovacuum_vacuum_scale_factor = 0.01   (trigger at ~1% dead rows)
  table rows > 100K → autovacuum_vacuum_scale_factor = 0.05   (trigger at ~5% dead rows)
  table rows < 100K → default 0.20 is acceptable

  Default trigger formula: 50 + 0.20 × n_live_tup
  Example: 4M rows × 0.20 = 828,932 dead rows before autovacuum fires — too high
  Fix:     4M rows × 0.01 = ~41,000 dead rows → frequent, lightweight passes
```

```
Dead tuple thresholds:
  dead_ratio < 5%   → healthy, no action
  dead_ratio 5–10%  → monitor, check autovacuum settings
  dead_ratio > 10%  → run VACUUM immediately, fix scale_factor
  dead_ratio > 20%  → incident — autovacuum is broken or blocked, investigate

  last_autovacuum IS NULL on large table → always a scale_factor or autovacuum-disabled problem
```

```
VACUUM vs REINDEX decision:
  High dead_ratio → VACUUM (ANALYZE) — cleans heap, updates stats, non-blocking
  High index reusable_pages (> 30%) → REINDEX CONCURRENTLY — compacts index, non-blocking
  Both problems → VACUUM first, then REINDEX
  Need to reclaim heap disk space urgently → VACUUM FULL (blocks table — maintenance window only)

  VACUUM alone does NOT shrink index files — "reusable pages" stay in the file
  REINDEX CONCURRENTLY is safe for production — no table lock, takes 5–20 min on large tables
```

```
Long-running transaction blocking VACUUM:
  Diagnosis: SELECT pid, now() - query_start AS duration, state, query
             FROM pg_stat_activity
             WHERE state != 'idle' AND query_start < now() - interval '5 minutes';
  If found: identify and terminate or wait — VACUUM cannot reclaim tuples visible to open txns
  Dead_ratio grows despite autovacuum running → long transactions are the cause
```

```
Index bloat thresholds:
  reusable / total < 10%  → healthy
  reusable / total 10–30% → monitor
  reusable / total > 30%  → REINDEX CONCURRENTLY
  reusable / total > 70%  → critical — run REINDEX immediately

  Real incident (stockadjustments, 2026-03-30):
    pkey index: 65,465 / 76,838 = 85% reusable → every PK scan traverses 85% empty pages
    Total index waste: ~1.07 GB across 6 indexes — all required REINDEX CONCURRENTLY
```

---

### EF Core

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
Inside a loop → BLOCK — replace with Include() chain (Eager Graph Loading).
Outside a loop (single entity) → acceptable.
```

```
Shared context resolution (e.g. IsExistOrderReference, order header lookup):
Called once for a single request → OK.
Called N times for the same ID in the same request → BLOCK — resolve once at coordinator level, pass result down.
Rule: if two sibling calls resolve the same ID independently, the coordinator must own that resolution.
See D10: Coordinator-Level Resolution.

Real example (target.cs):
  GetOrderHeader, GetOrderMessagePayments, GetOrderPromotion each call IsExistOrderReference
  independently for the same SourceOrderId = 6-9 redundant queries.
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

Measured impact (GetSubOrder, 2026-04-01):
  "All" N≈10: P50 1,242ms → 1,117ms (-10%). Total from baseline: -78%.
  N=1: P50 878ms → 805ms (-8%).
  Gain capped by serial bulk load (GetSubOrderMessageFromBatch ≈ 900ms) dominating total.

See D8: IDbContextFactory, D15: await using var scope rule.
```

```
await using var scope rule (factory DbContext lifetime):

RULE: Declare ALL factory DbContext instances at coordinator scope, BEFORE any
      conditional (if/for/while) branching. Never declare await using var inside a nested block
      when the task using it is assigned to an outer variable.

WHY: C# disposes await using variables at the end of the enclosing block (}).
     If ctx is declared inside an if block, it is disposed when the if block exits —
     even if the task referencing ctx has not yet run.
     await Task.WhenAll then tries to query on a closed connection → exception.

Error signature: System.InvalidOperationException: Invalid operation. The connection is closed.
                 Stack: SingleQueryingEnumerable.AsyncEnumerator.InitializeReaderAsync

WRONG:
  if (condition)
  {
      await using var ctx4 = _contextFactory.CreateDbContext(); // disposed at }
      rewardTask = repo.GetDataAsync(ctx4, id);
  }
  await Task.WhenAll(task1, task2, task3, rewardTask); // ctx4 already closed → CRASH

CORRECT:
  await using var ctx1 = _contextFactory.CreateDbContext();
  await using var ctx2 = _contextFactory.CreateDbContext();
  await using var ctx3 = _contextFactory.CreateDbContext();
  await using var ctx4 = _contextFactory.CreateDbContext(); // all at coordinator scope
  if (condition)
  {
      rewardTask = repo.GetDataAsync(ctx4, id);
  }
  await Task.WhenAll(task1, task2, task3, rewardTask); // all contexts alive ✓

Cost: unused ctx4 opens and closes one connection — acceptable.
See D15. Real incident: ctx4 in GetSubOrderAsync (target.cs), 2026-04-01.
```

```
EF compiled query cache thresholds:
  DynamicMethod objects < 500       → healthy
  DynamicMethod objects 500–2,000   → investigate which hot-path queries lack static compilation
  DynamicMethod objects > 2,000     → apply EF.CompileAsyncQuery to top 5 hottest queries immediately

  DynamicMethod count == DynamicILGenerator count == DynamicResolver count → always (1:1:1 per compiled query)
  These objects are in static cache → GC CANNOT collect them → non-reclaimable heap

  Diagnosis: dotnet-dump → dumpheap -stat → search for System.Reflection.Emit.Dynamic*
  Fix: extract hot query to static readonly Func<> using EF.CompileAsyncQuery / EF.CompileQuery

  Rule: any query called on a hot API path (> 100×/min) with Include chain → compile statically
  Rule: dynamic filter queries (optional .Where) cannot be compiled statically → accept growth, mitigate by limiting filter combinations

  Distinguishing unbounded growth from stable ceiling (load test validation):
    Unbounded growth:  DynamicMethod count increases across multiple heap dumps taken at same load
                       → same queries being recompiled on every call variation → apply EF.CompileQuery
    Stable ceiling:    DynamicMethod count is same (or lower) across heap dumps at same or higher load
                       → each unique query compiled once → no action needed
    How to confirm:    Take two heap dumps 10 minutes apart under steady load; compare DynamicMethod count
                       If delta ≈ 0 → stable; if delta grows linearly with requests → unbounded

  Real incident (2026-03-31 load test):
    Before fix: 17,557 DynamicMethod (unbounded — same bulk query recompiled per call variation)
    After EF.CompileQuery fix under load test: 7,356 DynamicMethod (stable ceiling)
    Remaining 7,356 = service-wide unique query footprint across all endpoints — expected, non-growing
    Total static cache: ~3.2 MB — acceptable for a service with many endpoints
```

```
.NET heap composition — what to expect in dumpheap -stat:
  System.Byte[]                      → HTTP buffers, JSON output, network I/O — normal, GC-managed
  System.String                      → SQL query strings, log messages, JSON keys — normal, GC-managed
  System.Char[]                      → String internals, JsonReader — normal
  System.Reflection.Emit.Dynamic*    → EF compiled query cache — NON-RECLAIMABLE — see threshold above
  Microsoft.Data.SqlClient._SqlMetaData → DB column descriptors — per open SqlDataReader, dispose promptly
  Microsoft.Data.SqlClient.SqlBuffer → Raw column data from SqlDataReader — dispose promptly
  EF entity types in large quantity  → ChangeTracker accumulation — add AsNoTracking() immediately
  IQueryable / IncludableQueryable   → EF query builder objects — GC-collected after materialization (normal)

  SqlClient objects alive at snapshot time:
    Count proportional to concurrent request count → load-proportional, GC-reclaimable, normal
    Count stable / growing between snapshots at same load → potential leak → verify `await using` on all ADO calls
  EF entity counts match expected N   → normal
  EF entity counts >> expected N      → ChangeTracker leak — DbContext not disposed, or missing AsNoTracking()

  Heap fragmentation (large Free block in dumpheap -stat):
    Free block < 30% of total heap → normal post-GC, reusable without growing process
    Free block > 50% of total heap → investigate — LOH fragmentation, consider GC.Collect(2, GCCollectionMode.Forced) in maintenance
    Fragmented block types (String, Byte[], Int32[]) → normal buffers from concurrent request processing
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
  If AsSplitQuery didn't reduce latency → the outer loop is the real bottleneck, apply Bulk Load Then Map

Real incident (target.cs): Phase 3 attempt 1 — replaced 21 Entry().Load() with Include + AsSplitQuery
  inside the per-sub-order loop. Result: ~0% latency change, +19% worse cold start. Reverted.
  Fix: batch the outer loop itself (Bulk Load Then Map). P50: 2,730ms → 1,505ms (-45%).

Phase 5 incident (target.cs): _bulkSubOrderQuery had 16 Include paths → ~27 sequential AsSplitQuery
  queries at ~35ms each ≈ 900ms total. Fix: split into _bulkSubOrderHeaderQuery (~9 queries) +
  _bulkSubOrderItemsQuery (~13 queries) and run both in parallel via Task.WhenAll + IDbContextFactory.
  Result: ~900ms → ~524ms (-42%). Gap vs BotE (~455ms): pool contention — 2 parallel tasks competing
  for connection pool slots simultaneously. Total request: 1,117ms → 741ms (-34%).
  Rule: if AsSplitQuery bulk query still dominates latency → split by Include group and parallelize.
```

```
Outer loop vs inner query optimization:
  Symptoms of inner query bottleneck: each iteration has 1-2 queries, latency ∝ query_count × latency_per_query
  Symptoms of outer loop bottleneck:  each iteration has 5+ queries, latency ∝ N × (queries × latency)
  Diagnosis: if (P50 ÷ N) ≈ constant → outer loop is the bottleneck
  Fix for outer loop: Bulk Load Then Map — eliminate the loop, not the inner queries
```

---

### Kafka & Messaging

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

### Caching

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

### Data Ingestion (ETL/FTP)

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
ETL transaction scope:
  batch_count × avg_batch_latency > 10,000ms  → per-batch commit mandatory
  batch_count × avg_batch_latency < 5,000ms   → single TX acceptable
  MySQL target (default config)                → assume innodb_lock_wait_timeout = 50s

  while(true) batch loop + DB writes?          → TX MUST be inside the loop, never outside
  BeginTransaction() before a while loop?      → architectural bug — move inside loop immediately
  Polly retries on ETL job?                    → only effective with per-batch idempotent cursor
  Airflow retries on .NET subprocess job?      → add retries=2, retry_delay=5min, subprocess timeout=7200s
```

```
Validation gate:
Hard validation failure (missing required field, wrong type) → reject row, log, continue
Soft validation failure (unexpected value, out of range)     → flag row, process with default
All rows in file fail validation                             → reject file, alert, do not partially apply
```

```

```
ETL batch observability (mandatory after any timeout fix):
  Batch loop writing to DB?                    → Prometheus Histogram on TX hold time
  Total records > 100K?                        → Counter + Gauge (round) + GC Summary
  Job orchestrated by scheduler?               → Alerting required — logs alone insufficient
  Alert thresholds:                            → WARN P95 > 5s, CRIT P95 > 30s (for MySQL 50s default)
  Overhead budget:                             → < 0.1% of batch duration for all instrumentation
  5 required metrics: batch_duration_seconds (Histogram), records_processed_total (Counter),
    current_batch_round (Gauge), staging_read_seconds (Histogram), batch_alloc_bytes (Summary)
```

```
Change detection strategy:
Source has reliable timestamps   → filter by updated_at > last_sync
Source has no timestamps         → record-level hash comparison
Source sends full snapshot daily → staging + diff against current state
```

---

### API Design

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

### Architecture Patterns

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

### System Design

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

### Observability

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
GC pressure indicators (live log):
GC.Gen0 delta > 0 per request   → short-lived object churn (EF proxy objects, tracking overhead)
GC.Gen1 delta > 0 per request   → memory pressure — objects surviving Gen0, investigate
GC.Gen2 delta > 0 per request   → serious — large or long-lived allocations, treat as incident
AsNoTracking() on read path      → reduces Gen0 pressure by eliminating EF change tracking objects

Sawtooth MemDelta pattern (grows N KB/call then drops):
  → EF ChangeTracker accumulating entities until DbContext disposed or GC fires
  → Fix: AsNoTracking() on all read-only queries
  → Confirmed safe when sawtooth disappears post-fix (heap stays flat)

Concurrency risk formula:
  concurrent_requests × AllocatedKB_per_call = live unrecollectable heap during burst
  Example: 100 concurrent × 2,600 KB = 260 MB simultaneously held
  If this approaches 70% of process memory limit → GC will fire stop-the-world Gen2 collections
  Fix path: (1) AsNoTracking — eliminate tracking overhead, (2) compiled queries — reduce static heap,
            (3) Phase 4 async parallel — reduce request duration so heap is released faster
```

```
Heap dump analysis workflow (.dmp file):
  1. dotnet-dump analyze <path/to/file.dmp>
  2. dumpheap -stat                    → top types by total size, sorted ascending (largest at bottom)
  3. Look for red flags (see .NET heap composition rule above)
  4. For specific type: dumpheap -type <TypeName>  → lists all instances with addresses
  5. For retention path: gcroot <address>          → who is keeping this object alive
  6. For live strings: dumpheap -type System.String → check for unexpectedly large string sets

  Export heapstat to file (before entering REPL):
    dotnet-dump analyze <file.dmp> --command "dumpheap -stat" > heapstat.txt 2>&1
    (or pipe via: echo "dumpheap -stat" | dotnet-dump analyze <file.dmp>)
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

### Code Review Flags

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

### Distributed Systems — CAP & Consistency

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

### Distributed Systems — Consistent Hashing

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

### Distributed Systems — ID Generation

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

### Distributed Systems — Distributed Transactions

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

### Rate Limiting

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

### Real-Time Connections

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

### Storage Strategy

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

### Geospatial Indexing

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

### Financial Systems

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

### Scalability Thresholds (Back-of-Envelope Reference)

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

---

### D16: Transaction Scope for Bulk ETL Operations — Per-Batch vs Single TX

```
Title:            Transaction Scope for Bulk ETL Operations — Per-Batch vs Single TX
Context:          .NET ETL job syncing large record volumes from staging to MySQL production
                  via EF Core + batch loop, orchestrated by Airflow.
Problem:          Where should the transaction boundary sit — wrapping the entire job (single TX)
                  or wrapping each individual batch (per-batch commit)?
Options Considered:
  A. Single TX — atomic across all records. Simple code.
     Fails at scale: TX hold = batch_count × latency = 210s >> 50s MySQL timeout.
     0 records committed on failure. Eliminated by BotE.
  B. Per-Batch Commit — TX hold = 1 batch duration (~700ms). Safe against all MySQL timeouts.
     Idempotent restart via monotonic cursor. On failure only in-flight batch is lost.
     Trade-off: partial sync visible in prod during run. Acceptable for ETL.
  C. Chunked Multi-Batch TX — commit every N batches. More complex than B, no significant benefit.
Decision:         Option B — Per-Batch Commit.
Rationale:        BotE eliminates Option A (210s >> 50s). Option C adds complexity for no gain.
                  Option B is the canonical ETL pattern, compatible with existing cursor design.
Trade-offs:       Accept partial sync visibility in production during job execution.
                  Accept per-batch (not per-job) atomicity — standard ETL consistency model.
Expected Outcome: Zero MySQL timeout failures. Max 1 batch re-synced on failure. Effective Airflow
                  retry behavior (resumes from cursor, not from zero).
Rules:
  batch_count × avg_batch_latency > 10s?  → per-batch commit mandatory
  while(true) loop with DB writes?         → TX MUST be inside the loop, never outside
  BeginTransaction() before a while loop?  → architectural bug — requires immediate fix
  Polly retries on ETL?                    → only useful with per-batch commit (preserves progress)
  Airflow retries on .NET subprocess job?  → add retries=2, retry_delay=5min, subprocess timeout = BotE_realistic × 3
Related Knowledge:  → K30, K32
Related Pattern:    → P24, P25
Related Incidents:  → I3, I4, I5, I6
Related Tech Assets:→ TA19, TA20
Date:             2026-04-07
```

---

### D17: ETL Batch Observability Strategy — Prometheus Metrics vs Log-Only

```
Title:            ETL Batch Observability Strategy — Prometheus Metrics vs Log-Only
Context:          .NET ETL job (SyncProductMasterJda) syncing 3M records to MySQL via per-batch
                  commit loop. Post-I3 fix: per-batch TX eliminates timeout. But zero metrics
                  on batch resource consumption — no early warning for latency drift.
Problem:          How should we instrument the ETL batch loop — structured logs only (low effort)
                  or Prometheus metrics + logs (slightly more effort, enables alerting)?
Options Considered:
  A. Structured logging only — add Stopwatch + GC to log per batch. No Prometheus.
     Pro: Zero dependency. Con: No alerting, no trend visualization, must grep logs to detect drift.
  B. Prometheus metrics + structured logging — Histogram for TX hold, Counter for records,
     Summary for GC alloc, plus structured log per batch.
     Pro: Real-time dashboard, P95 alerts, trend detection. Con: Requires prometheus-net dependency.
  C. OpenTelemetry traces — span per batch with attributes.
     Pro: Distributed trace context. Con: Heavier setup, ETL is single-process (no distributed trace needed).
Decision:         Option B — Prometheus metrics + structured logging.
Rationale:        Stack already uses Prometheus (tech stack spec). ETL runs unattended on Airflow —
                  alerting is non-negotiable. Logs alone require manual grep to detect trends.
                  Prometheus Histograms give P50/P95/P99 automatically. Overhead: ~0.02% of batch duration.
Trade-offs:       Requires prometheus-net NuGet package. Static metric fields in class. Minimal.
Expected Outcome: Grafana dashboard showing batch duration trend per sync job. Alert fires when
                  P95 batch TX hold > 5s (warn) or > 30s (crit) — well before MySQL 50s timeout.
Rules:
  ETL batch loop writing to DB?                → Prometheus Histogram on TX hold time mandatory
  Total records > 100K?                        → Counter + Gauge (round) mandatory
  Job orchestrated by scheduler (Airflow)?     → Alerting required — logs alone insufficient
  Overhead > 0.1% of batch duration?           → Remove instrument — too expensive
Related Knowledge:  → K31, K32
Related Pattern:    → P25
Related Incidents:  → I3, I4, I5
Related Tech Assets:→ TA20, TA21
Date:             2026-04-08
```


---

### D18: Max Batch Size for MySQL ETL — 10K Records Hard Ceiling

```
Title:       Max Batch Size for MySQL ETL — 10K Records Hard Ceiling
Context:     SyncProductMasterJda / SyncProductBarcodeJda running with BatchSize=20K.
             Airflow logs show TX hold 27-40s per batch (Batch 1: 39,689ms = 79% of
             MySQL 50s innodb_lock_wait_timeout). CRIT alert fires for Batches 1, 9, 10.
Problem:     What is the correct upper bound for batch size in this ETL workload?
Decision:    BatchSize = 10,000 records. Hard ceiling. Never exceed without re-running BotE.
Rationale:   BotE formula: tx_hold approx (batch_size / 10K) x 14s
             Safety margin rule: tx_hold < timeout x 0.5 (50% headroom)
             10K -> 14s = 28% of 50s limit  (safe)
             20K -> 28-40s = 56-80% of limit (CRITICAL — CRIT alert firing)
IF/THEN Rules:
  BatchSize <= 10K AND tx_hold_p95 < 14s  -> batch healthy, no change
  BatchSize <= 10K AND tx_hold_p95 > 14s  -> investigate write-side latency
  BatchSize > 10K                          -> reduce to 10K immediately
  tx_hold_p95 > 30s                        -> CRIT alert, reduce batch size
Related Knowledge:  → K30, K33
Related Pattern:    → P24, P26
Related Incidents:  → I3, I5, I6
Date:               2026-04-08
```

#### BotE

| Batch Size | TX Hold | % of 50s MySQL timeout | Risk |
|---|---|---|---|
| 10K (target) | ~14s | 28% | Safe |
| 20K (current) | ~28-40s | 56-80% | CRITICAL |
| 25K | ~35s | 70% | CRIT alert |
| 36K | ~50s | 100% | Certain timeout |

Safety margin = 50% of timeout -> max safe tx_hold = 25s. Round down to 10K to account
for write-latency variance (index degradation, lock contention, GC pause).

#### Decision

BatchSize = 10000 in appsettings.json. Not a code change — config entry read by
ConfigurationHelper.GetBatchSize(configuration). Never increase without re-running BotE
formula against current observed avg_write_ms from Prometheus etl_sync_batch_duration_seconds.

