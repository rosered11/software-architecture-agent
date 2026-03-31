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
Watch out for:    Connection pool growth: N parallel tasks × concurrent requests.
                  Monitor pool size: pool ≥ expected_concurrent_requests × parallel_tasks.
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P16: Async Parallel DB Coordinator
Date:             2026-03-27
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
                  Phase 1–3 delivered ~750ms improvement. Phase 4 added further ~350ms.
                  Incremental diffs are easier to review, test, and roll back independently.
Expected Outcome: Phase 1–3: ~1,500ms → ~750ms. Phase 4: ~750ms → ~400ms. Total: -73%.
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P17: Batch Query (WHERE IN)
                   → P18: Eager Graph Loading
                   → P19: Coordinator-Level Resolution
                   → P20: Bulk Load Then Map
                   → P16: Async Parallel DB Coordinator
Date:             2026-03-27
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

