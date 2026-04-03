# 📚 KOS — System Design Knowledge Base

> Generated from 37 source PDFs covering System Design Interview Vol. 1 & 2 topics.
> This file follows the Notion KOS format: Knowledge → Pattern → Decision Log → Tech Assets.
> Each record is complete and cross-linked per the Incident → Knowledge → Pattern → Decision → Reuse loop.

---

## KNOWLEDGE RECORDS

---

### K1: Back-of-the-Envelope Estimation

```
Title:            Back-of-the-Envelope Estimation
Type:             Technique
Domain:           Scalability
Difficulty:       Beginner
Summary:          Quick approximation technique using power-of-two and latency numbers to
                  validate whether a system design is feasible at a given scale before committing
                  to detailed design.
Deep Dive:        Core method:
                  1. Clarify scale (DAU, QPS, storage, bandwidth)
                  2. Convert to per-second metrics (DAU × actions / 86,400)
                  3. Estimate storage and bandwidth
                  4. Identify bottlenecks from the numbers

                  Key numbers to memorize:
                  LATENCY HIERARCHY:
                  - L1 cache:             0.5 ns
                  - Main memory:          100 ns      (200x slower than L1)
                  - SSD read:             150 µs      (300,000x slower than L1)
                  - Network in DC:        500 µs
                  - HDD seek:             10 ms       (20,000,000x slower than L1)
                  - Cross-datacenter:     150 ms

                  AVAILABILITY (nines):
                  - 99%    = 3.65 days downtime/year
                  - 99.9%  = 8.7 hours downtime/year
                  - 99.99% = 52.6 minutes downtime/year
                  - 99.999%= 5.26 minutes downtime/year

                  STORAGE UNITS:
                  - 1 KB = 2^10  bytes (~10^3)
                  - 1 MB = 2^20  bytes (~10^6)
                  - 1 GB = 2^30  bytes (~10^9)
                  - 1 TB = 2^40  bytes (~10^12)
                  - 1 PB = 2^50  bytes (~10^15)

                  COMMON ESTIMATIONS:
                  - Twitter: 300M DAU, 600 tweets/sec write, 60K tweets/sec read
                  - QPS formula: DAU × actions / 86,400
                  - Storage formula: QPS × object_size × seconds_per_day × retention_days

Example:          URL Shortener:
                  - Write: 100M/day → 100M/86400 ≈ 1,160 QPS
                  - Read:  10:1 ratio → 11,600 QPS
                  - Storage: 100M × 365 × 10 years × 100 bytes = 36.5 TB

Trade-offs:       Pros: Fast validation, prevents over-engineering, shows bottlenecks early
                  Cons: Approximations can mislead if base assumptions are wrong
Decision Rule:    Always do estimation before detailed design.
                  If QPS > 1,000 → consider caching.
                  If storage > 1 TB → consider sharding or object storage.
                  If latency requirement < 100ms → eliminate cross-datacenter calls.
Related Concepts: → CAP Theorem
                  → Database Sharding Strategies
                  → CDN Strategy
Source:           System Design Interview Vol. 1, Chapter 2
```

---

### K2: CAP Theorem

```
Title:            CAP Theorem
Type:             Concept
Domain:           Distributed Systems
Difficulty:       Intermediate
Summary:          A distributed system can guarantee at most two of three properties:
                  Consistency (all nodes see same data), Availability (every request gets a response),
                  and Partition Tolerance (system works despite network splits).
Deep Dive:        Since network partitions are unavoidable in distributed systems, the real
                  trade-off is between Consistency (CP) and Availability (AP):

                  CP SYSTEMS (choose consistency over availability):
                  - During partition, refuse to respond (error) to avoid stale data
                  - Use case: banking, inventory systems, any system where stale = wrong
                  - Examples: HBase, ZooKeeper, MSSQL with 2PC

                  AP SYSTEMS (choose availability over consistency):
                  - During partition, return possibly stale data
                  - Use case: social media feeds, shopping carts, DNS
                  - Examples: Cassandra, DynamoDB, CouchDB (with eventual consistency)

                  EVENTUAL CONSISTENCY:
                  - All replicas eventually converge to the same value
                  - Acceptable when stale reads cause no financial/correctness harm
                  - Requires conflict resolution (Last-Write-Wins, vector clocks, CRDT)

                  STRONG CONSISTENCY:
                  - All reads reflect the latest write
                  - Requires quorum (W + R > N) or single-leader replication
                  - Higher latency and lower availability

Example:          Hotel reservation system:
                  - Chose CP (MySQL + pessimistic locking) for room inventory
                  - Reason: overbooking is worse than returning an error
                  Social feed:
                  - Chose AP (eventual consistency) for news feed
                  - Reason: seeing a slightly stale post is acceptable

Trade-offs:       CP: Correct data, may be unavailable during partition
                  AP: Always available, may serve stale data
Decision Rule:    Data correctness = money/safety? → CP
                  User experience > strict correctness? → AP
                  Multi-region active-active? → AP with conflict resolution
Related Concepts: → Quorum Consensus (N, W, R)
                  → Vector Clocks
                  → Distributed Transactions
Related Patterns:  → P6: Event Sourcing Pattern
                  → P13: Saga Pattern
Source:           System Design Interview Vol. 1, Chapters 6, 8
```

---

### K3: Consistent Hashing

```
Title:            Consistent Hashing
Type:             Technique
Domain:           Distributed Systems
Difficulty:       Intermediate
Summary:          A hashing scheme where adding/removing nodes only remaps k/n keys
                  (not all keys), making it ideal for distributed caches and data stores.
Deep Dive:        HOW IT WORKS:
                  1. Map servers AND keys onto the same hash ring (0 to 2^32-1)
                  2. To find which server owns a key: traverse clockwise from key position
                  3. When a server is added: only keys between new server and its predecessor are moved
                  4. When a server is removed: only keys belonging to it are moved to the next server

                  VIRTUAL NODES:
                  - Problem: standard consistent hashing creates uneven partitions
                  - Solution: assign each physical server multiple positions on the ring (virtual nodes)
                  - Standard: 100-200 virtual nodes per server
                  - Effect: standard deviation of distribution drops to 5-10%
                  - Trade-off: more virtual nodes = more storage for the ring mapping

                  TRADITIONAL HASHING COMPARISON:
                  - Traditional (mod N): adding/removing 1 server remaps ~all keys
                  - Consistent: adding/removing 1 server remaps k/n keys on average

                  REAL-WORLD USE:
                  - Amazon DynamoDB partitioning
                  - Apache Cassandra data distribution
                  - Discord chat routing
                  - Akamai CDN cache key routing
                  - Maglev load balancer

Example:          // Pseudocode for ring lookup
                  ring = SortedMap<int, Server>
                  for server in servers:
                      for replica in range(VIRTUAL_NODES):
                          hash = SHA1(server.id + replica)
                          ring[hash] = server

                  def get_server(key):
                      hash = SHA1(key)
                      entry = ring.ceiling(hash)  // first server >= hash
                      return entry if entry else ring.first()  // wrap around

Trade-offs:       Pros: Minimal key remapping on topology change, even distribution with vnodes
                  Cons: More complex than mod-N, storage overhead for ring, SHA1 computation
Decision Rule:    Static server count? → Simple mod-N hashing is fine
                  Dynamic server count (autoscale, failures)? → Consistent hashing
                  Need even distribution? → Use virtual nodes (100-200 per server)
Related Concepts: → Database Sharding Strategies
                  → CAP Theorem
Related Patterns:  → P2: Consistent Hashing Ring
Source:           System Design Interview Vol. 1, Chapter 5
```

---

### K4: Rate Limiting Algorithms

```
Title:            Rate Limiting Algorithms
Type:             Concept
Domain:           API Design
Difficulty:       Intermediate
Summary:          Five algorithms for controlling API request rates, each with different
                  trade-offs between accuracy, memory usage, and burst handling.
Deep Dive:        1. TOKEN BUCKET (most widely used):
                  - Bucket of capacity C tokens, refilled at rate R
                  - Each request consumes 1 token; if empty, reject
                  - Allows burst up to capacity C
                  - Parameters: bucket_size, refill_rate
                  - Used by: Amazon, Stripe

                  2. LEAKING BUCKET:
                  - Requests enter a FIFO queue of fixed capacity
                  - Processed at a fixed rate (output)
                  - Overflow is discarded
                  - Produces stable outflow rate
                  - Trade-off: old requests may starve new ones under burst

                  3. FIXED WINDOW COUNTER:
                  - Divide time into fixed windows (e.g., 1 minute)
                  - Count requests per window; reject if over limit
                  - Simple, memory efficient
                  - Edge case: 2× limit requests possible at window boundary

                  4. SLIDING WINDOW LOG:
                  - Track timestamps of every request in sorted set
                  - Remove timestamps older than window size
                  - Count remaining = current request count
                  - Accurate but high memory (stores all timestamps)

                  5. SLIDING WINDOW COUNTER:
                  - hybrid: current window count + previous window count × overlap %
                  - Example: 70% of current window elapsed → 30% of prev window counts
                  - Memory efficient, approximately accurate
                  - Cloudflare study: only 0.003% error rate on 400M requests

                  DISTRIBUTED RATE LIMITING:
                  - Use Redis INCR + EXPIRE for centralized counter
                  - Lua scripts for atomic operations
                  - Place limiters at API gateways, edge servers

Example:          // Redis-based token bucket (Go pseudocode)
                  key = "rate_limit:" + user_id
                  tokens = redis.GET(key) || bucket_capacity
                  if tokens > 0:
                      redis.DECR(key)
                      return allow
                  else:
                      return reject (HTTP 429)
                  // Background: refill tokens at rate R per second

Trade-offs:       Token bucket: burst-friendly, complex tuning
                  Leaking bucket: stable outflow, may starve new requests
                  Fixed window: simple, edge-case vulnerability
                  Sliding log: accurate, high memory
                  Sliding counter: memory efficient, slightly inaccurate
Decision Rule:    Need burst tolerance? → Token Bucket
                  Need stable processing rate? → Leaking Bucket
                  Simple per-minute limit? → Fixed Window Counter
                  High accuracy required? → Sliding Window Log
                  Scale + accuracy balance? → Sliding Window Counter
Related Concepts: → Back-of-the-Envelope Estimation
Related Patterns:  → P1: Token Bucket Rate Limiting
Source:           System Design Interview Vol. 1, Chapter 4
```

---

### K5: Distributed Unique ID Generation — Snowflake

```
Title:            Distributed Unique ID Generation — Snowflake
Type:             Concept
Domain:           Distributed Systems
Difficulty:       Intermediate
Summary:          Twitter's Snowflake algorithm generates 64-bit globally unique, time-sortable
                  IDs without coordination between nodes, supporting 4,096 IDs/ms per machine.
Deep Dive:        SNOWFLAKE 64-BIT LAYOUT:
                  [1 bit sign][41 bits timestamp ms][5 bits datacenter][5 bits machine][12 bits sequence]

                  - Sign bit (1): always 0 (reserved for future use)
                  - Timestamp (41): milliseconds since epoch → 69 years before overflow
                  - Datacenter ID (5): supports 32 datacenters
                  - Machine ID (5): supports 32 machines per datacenter
                  - Sequence (12): 4,096 IDs per millisecond per machine
                  - Max throughput: 32 DC × 32 machines × 4,096/ms = 4.2 billion IDs/ms globally

                  ALTERNATIVES COMPARED:
                  - Multi-master DB: hard to scale, single point of failure
                  - UUID (128-bit): too large, not numeric, not time-sortable, random
                  - Ticket server: SPOF, network hop required

                  CLOCK SYNCHRONIZATION:
                  - Snowflake depends on machine clocks being synchronized (NTP)
                  - Clock skew < 1ms acceptable
                  - Clock going backwards: wait until current time > last_timestamp

                  TIME SORTABILITY:
                  - IDs are roughly ordered by creation time
                  - Enables range queries: find all orders after ID X
                  - Not strictly monotonic across machines (different machine clocks)

Example:          // Go pseudocode
                  func nextID() int64 {
                      mu.Lock(); defer mu.Unlock()
                      now := currentTimeMs()
                      if now == lastTimestamp {
                          sequence = (sequence + 1) & 0xFFF  // 12-bit mask
                          if sequence == 0 { now = waitNextMs(lastTimestamp) }
                      } else {
                          sequence = 0
                      }
                      lastTimestamp = now
                      return (now - epoch) << 22 | datacenterID << 17 | machineID << 12 | sequence
                  }

Trade-offs:       Pros: No coordination needed, time-sortable, 64-bit (fits long), high throughput
                  Cons: Requires clock sync, IDs not strictly monotonic, ~69 year limit
Decision Rule:    Need sortable IDs without a central coordinator? → Snowflake
                  Need exact monotonic sequence? → DB auto-increment (single server)
                  Need globally unique but don't care about order? → UUID v4
Related Concepts: → Back-of-the-Envelope Estimation
                  → Database Sharding Strategies
Related Patterns:  → P10: Snowflake ID Generation
Source:           System Design Interview Vol. 1, Chapter 7
```

---

### K6: Quorum Consensus (N, W, R)

```
Title:            Quorum Consensus (N, W, R)
Type:             Concept
Domain:           Distributed Systems
Difficulty:       Advanced
Summary:          Three parameters control the consistency/latency trade-off in replicated
                  systems: N replicas, W write quorum, R read quorum. W + R > N guarantees
                  strong consistency.
Deep Dive:        PARAMETERS:
                  N = total number of replicas
                  W = minimum replicas that must acknowledge a write (write quorum)
                  R = minimum replicas that must respond to a read (read quorum)

                  STRONG CONSISTENCY CONDITION: W + R > N
                  - At least one replica in any read set overlaps with the write set
                  - Guarantees at least one replica has the latest write

                  CONFIGURATION TRADE-OFFS:
                  - R=1, W=N → Optimize for fast reads (read from 1, write to all)
                  - R=N, W=1 → Optimize for fast writes (write to 1, read from all)
                  - R=2, W=2, N=3 → Balanced (most common production config)
                  - R=1, W=1, N=3 → High availability, eventual consistency (no quorum)

                  COMMON PRODUCTION CONFIG (N=3, W=2, R=2):
                  - Write: 2 out of 3 replicas must ack before success
                  - Read: take latest from 2 out of 3 replicas
                  - Tolerates 1 replica failure for both reads and writes

                  COORDINATOR:
                  - In DynamoDB/Cassandra, client routes to a coordinator node
                  - Coordinator manages the quorum negotiation

Example:          DynamoDB write with W=2, N=3:
                  1. Client writes to coordinator
                  2. Coordinator forwards to 3 replicas in parallel
                  3. Returns success after 2 replicas acknowledge
                  4. Third replica syncs asynchronously (anti-entropy)

Trade-offs:       W + R > N: Strong consistency, higher latency (wait for quorum)
                  W + R ≤ N: Eventual consistency, lower latency, possible stale reads
                  Large W: Slow writes, great read performance
                  Large R: Slow reads, great write performance
Decision Rule:    Financial/inventory data? → W=2, R=2, N=3 (balanced + consistent)
                  Social feed, analytics? → W=1, R=1 (fast, eventual)
                  Audit log? → W=N, R=1 (write to all, fast read)
Related Concepts: → CAP Theorem
                  → Vector Clocks
                  → Gossip Protocol
Source:           System Design Interview Vol. 1, Chapter 6
```

---

### K7: Vector Clocks & Conflict Resolution

```
Title:            Vector Clocks & Conflict Resolution
Type:             Concept
Domain:           Distributed Systems
Difficulty:       Advanced
Summary:          Vector clocks track causality between events across nodes, enabling conflict
                  detection and resolution in systems where network partitions cause diverging writes.
Deep Dive:        VECTOR CLOCK FORMAT:
                  D([S1, v1], [S2, v2], ...) — a list of (server, version) pairs

                  RULES:
                  - Increment server's own counter on every write
                  - Merge clocks on read (take max of each server's counter)
                  - Event A causally precedes B if all of A's counters ≤ B's counters
                  - Conflict: neither A ≤ B nor B ≤ A (concurrent writes)

                  CONFLICT RESOLUTION STRATEGIES:
                  1. Last-Write-Wins (LWW): take the version with latest timestamp
                     - Simple, lossy (may discard valid updates)
                  2. Merge: client merges conflicts (Amazon shopping cart)
                  3. CRDT (Conflict-free Replicated Data Types): data structures that
                     auto-merge without conflicts (counters, sets with tombstones)

                  SLOPPY QUORUM + HINTED HANDOFF:
                  - During partition, writes go to reachable nodes even if not preferred
                  - Hint is stored: "deliver to node X when it recovers"
                  - Improves availability at cost of potential divergence

                  MERKLE TREES for anti-entropy:
                  - Hash tree of data segments
                  - Quickly identify which segments differ between replicas
                  - Used in DynamoDB, Cassandra for background synchronization

Example:          Write conflict scenario:
                  - Server1 writes: D([S1,1])
                  - Server1 writes: D([S1,2])
                  - Network partition — Server2 also writes
                  - Server2: D([S1,1],[S2,1]) — conflict with D([S1,2])
                  - System detects conflict, asks client to resolve

Trade-offs:       Pros: Detects all conflicts, enables automatic merge for CRDTs
                  Cons: Clock size grows with server count, complex conflict resolution logic
Decision Rule:    Shopping cart / collaborative doc? → CRDT or client-merge
                  Audit trail, financial? → Last-Write-Wins is too risky → use Saga instead
                  Key-value store needing eventual consistency? → Vector clocks
Related Concepts: → CAP Theorem
                  → Quorum Consensus
                  → Gossip Protocol
Source:           System Design Interview Vol. 1, Chapter 6
```

---

### K8: Gossip Protocol for Failure Detection

```
Title:            Gossip Protocol for Failure Detection
Type:             Concept
Domain:           Distributed Systems
Difficulty:       Intermediate
Summary:          Decentralized failure detection where each node periodically shares its
                  membership list with random peers, achieving eventual global awareness
                  without a central coordinator.
Deep Dive:        HOW IT WORKS:
                  1. Each node maintains a membership table: [node_id, heartbeat_counter, timestamp]
                  2. Every T seconds, each node increments its own heartbeat
                  3. Node sends its full membership table to a random subset of peers
                  4. Receivers merge: take max(heartbeat) for each node
                  5. A node is marked "suspect" if heartbeat not updated for Tfail seconds
                  6. A node is declared "offline" after Tcleanup seconds

                  PROPERTIES:
                  - O(log N) rounds for information to reach all N nodes
                  - Tolerates arbitrary node failures and network partitions
                  - No single coordinator — fully decentralized
                  - Bandwidth: O(N × k) per round where k = fanout

                  TUNING PARAMETERS:
                  - T (gossip interval): lower = faster detection, higher CPU/bandwidth
                  - Tfail: false-positive vs. detection speed trade-off
                  - Tcleanup: must be > Tfail to avoid premature removal

                  USED IN: Amazon DynamoDB, Apache Cassandra, Consul

Example:          Node S0 health check via gossip:
                  S1 sees S0 heartbeat stale → tells S2, S3
                  S2 also confirms stale → S0 suspected
                  After Tcleanup passes → S0 declared offline
                  Ring rebalances: consistent hashing redistributes S0's data

Trade-offs:       Pros: Decentralized, fault-tolerant, scales to large clusters
                  Cons: Eventual detection (not instant), gossip bandwidth grows with N
Decision Rule:    Cluster > 10 nodes with no dedicated health-check service? → Gossip
                  Small cluster with ZooKeeper available? → ZooKeeper watchers
Related Concepts: → Consistent Hashing
                  → Quorum Consensus
Source:           System Design Interview Vol. 1, Chapter 6
```

---

### K9: Geospatial Indexing — Geohash & Quadtree

```
Title:            Geospatial Indexing — Geohash & Quadtree
Type:             Technique
Domain:           Distributed Systems
Difficulty:       Intermediate
Summary:          Two approaches to indexing 2D geographic coordinates for efficient
                  nearby search: Geohash (string-based, fixed grid) and Quadtree
                  (tree-based, density-adaptive).
Deep Dive:        GEOHASH:
                  - Encodes (lat, lon) into a base-32 string
                  - Longer string = smaller area = higher precision
                  - Precision levels:
                    Level 4: ~39km × 20km
                    Level 5: ~4.9km × 4.9km
                    Level 6: ~1.2km × 609m
                  - Nearby search: use prefix matching + check 8 neighbors
                  - Boundary problem: nearby points may have different prefixes
                  - Fix: always check all 8 neighboring geohash cells

                  QUADTREE:
                  - Recursively subdivide map into 4 quadrants
                  - Keep subdividing until each cell has ≤ 100 items
                  - Adapts to density (dense cities = deeper tree)
                  - ~2M leaf nodes, 0.67M internal nodes = ~1.71GB in memory for full index
                  - O(log n) lookup, O(n) build time

                  GOOGLE S2:
                  - Maps sphere to Hilbert curve (space-filling curve)
                  - Most flexible: arbitrary region shapes, not just rectangles
                  - Higher complexity, harder to explain in interviews

                  SEARCH EXPANSION:
                  - If insufficient results in geohash precision 6, expand to precision 5
                  - Keep expanding until enough results found or max radius exceeded

Example:          Yelp search within 5km:
                  1. Convert user location to geohash (precision 6)
                  2. Compute 8 neighbors of geohash
                  3. Fetch all businesses in those 9 cells
                  4. Filter by exact distance (haversine formula)
                  5. Sort by relevance/distance

Trade-offs:       Geohash: Simple, fast string comparison, fixed precision per level
                  Quadtree: Adapts to density, more complex updates (add/remove business)
                  S2: Most accurate shapes, hardest to implement and explain
Decision Rule:    Need simple range search with fixed precision? → Geohash
                  Need density-aware partitioning? → Quadtree
                  Need arbitrary polygon regions? → Google S2
Related Concepts: → Consistent Hashing
                  → Back-of-the-Envelope Estimation
Related Patterns:  → P9: Geohash Bucketing
Source:           System Design Interview Vol. 2, Chapters on Proximity Service, Nearby Friends
```

---

### K10: Event Sourcing

```
Title:            Event Sourcing
Type:             Framework Knowledge
Domain:           Architecture
Difficulty:       Advanced
Summary:          Instead of storing current state, store an immutable append-only log of
                  events that caused each state change. Current state is derived by replaying events.
Deep Dive:        CORE CONCEPT:
                  - Every state change is an event: OrderPlaced, PaymentReceived, ItemShipped
                  - Events are immutable, append-only (never update or delete)
                  - Current state = replay of all events from the beginning (or from snapshot)
                  - Snapshots: periodic materialized state to avoid replaying from beginning

                  KEY PROPERTIES:
                  - Full audit trail: know exactly what happened and when
                  - Temporal queries: "what was the state at time T?"
                  - Replay: re-derive state after fixing a bug in processing logic
                  - Event schema evolution: must handle old events with new processors

                  SNAPSHOTS:
                  - Periodic materialized state saved to avoid full replay
                  - Trigger: after N events, or on scheduled interval
                  - Recovery: load latest snapshot + replay events after it

                  CQRS + EVENT SOURCING:
                  - Write side: emits events (commands → events)
                  - Read side: projections built from event stream
                  - Multiple projections possible from same events

                  USED IN: Stock exchange sequencer, digital wallet, payment system

Example:          Stock exchange order:
                  Events: OrderReceived → MatchFound → OrderFilled → TradeSettled

                  // Recovery from crash (mmap event store):
                  1. Load last snapshot (state at event #9,423)
                  2. Replay events #9,424 to #9,501 from WAL
                  3. State is restored deterministically — no manual intervention

Trade-offs:       Pros: Full audit, temporal queries, deterministic replay, decouples read/write
                  Cons: Event schema evolution complexity, query complexity (need projections),
                        storage grows unboundedly (compaction needed), eventual consistency for reads
Decision Rule:    Financial system with audit requirements? → Event sourcing mandatory
                  Gaming leaderboard? → Too complex, Redis sorted sets sufficient
                  Need temporal queries ("show me order history")? → Event sourcing
                  Simple CRUD with no audit need? → Traditional DB state storage
Related Concepts: → CAP Theorem
                  → Distributed Transactions
                  → Message Queue Internals
Related Patterns:  → P6: Event Sourcing Pattern
                  → P8: Write-Ahead Log
Source:           System Design Interview Vol. 2, Chapters on Digital Wallet, Stock Exchange
```

---

### K11: Distributed Transactions — 2PC, Saga, TC/C

```
Title:            Distributed Transactions — 2PC, Saga, TC/C
Type:             Concept
Domain:           Distributed Systems
Difficulty:       Advanced
Summary:          Three approaches to maintaining ACID-like guarantees across multiple services
                  or databases, each with different consistency/availability/complexity trade-offs.
Deep Dive:        1. TWO-PHASE COMMIT (2PC):
                  Phase 1 (Prepare): Coordinator asks all participants "can you commit?"
                  Phase 2 (Commit): If all say yes, coordinator sends commit; else abort

                  Problems:
                  - Blocking: if coordinator fails after prepare, participants are locked
                  - Slow: 2 round trips + synchronous coordination
                  - Not partition-tolerant (CP system behavior)

                  When to use: Small number of resources (2-3 DBs), internal services,
                  latency is acceptable, rollback is cheap

                  2. SAGA PATTERN (existing in kos-patterns.md — extended here):
                  Choreography: Each service publishes events, next service listens
                  Orchestration: Central orchestrator sends commands, waits for replies
                  Compensating transactions: On failure, reverse each completed step

                  Payment saga example:
                  PaymentInitiated → ReserveBalance → ChargeCard → UpdateLedger
                  On card failure: ChargeCardFailed → ReleaseBalance → RefundInitiated

                  3. TC/C (TRY-CONFIRM/CANCEL):
                  - Business-specific version of 2PC
                  - Phase 1 (Try): tentatively reserve resources (e.g., hold $100)
                  - Phase 2 (Confirm): finalize if all succeed, or Cancel to release
                  - Application code implements compensating cancel logic
                  - More flexible than 2PC: each service defines its own try/confirm/cancel

                  Advantage over 2PC: No blocking protocol coordinator needed
                  Disadvantage: Application must implement cancel logic for every operation

                  WHICH TO CHOOSE:
                  - All in one DB? → Local ACID transaction (no distributed needed)
                  - 2-3 services, simple flow? → Choreography Saga
                  - Many services, complex flow? → Orchestration Saga or TC/C
                  - Strict atomicity + small service count? → 2PC

Example:          Hotel room reservation (chose database constraints + idempotency):
                  - Avoided distributed transactions by putting inventory + reservation
                    in same DB schema (hybrid microservices approach)
                  - Single SQL update with WHERE remaining > 0 is atomic at DB level

Trade-offs:       2PC: Strict atomicity, blocking failure mode, slow
                  Saga: Available, eventually consistent, complex compensation
                  TC/C: Flexible, no blocking, requires custom cancel logic per operation
Decision Rule:    Single DB (even if multiple services use it)? → DB transaction
                  Cross-DB, accept eventual? → Saga choreography
                  Cross-DB, strict business rules? → TC/C or Orchestration Saga
                  Payments? → TC/C + Idempotency keys + Reconciliation
Related Concepts: → CAP Theorem
                  → Event Sourcing
                  → Idempotency in Distributed Systems
Related Patterns:  → P13: Saga Pattern
                  → P8: Write-Ahead Log
Source:           System Design Interview Vol. 2, Chapters on Payment, Digital Wallet, Hotel Reservation
```

---

### K12: Stream vs Batch Processing

```
Title:            Stream vs Batch Processing
Type:             Concept
Domain:           Data Pipeline
Difficulty:       Intermediate
Summary:          Two fundamental paradigms for processing large data sets: batch (process
                  accumulated data periodically) and stream (process data continuously as it arrives).
Deep Dive:        BATCH PROCESSING (MapReduce / Spark):
                  - Processes bounded datasets (files, DB snapshots)
                  - High throughput, tolerates latency
                  - Re-runnable (deterministic on same input)
                  - Good for: daily reports, ML training, historical aggregation

                  STREAM PROCESSING (Flink / Kafka Streams / Storm):
                  - Processes unbounded data continuously
                  - Low latency (seconds to sub-second)
                  - Must handle: late events, out-of-order events, exactly-once semantics
                  - Window types: Tumbling (non-overlapping), Sliding (overlapping), Session

                  LAMBDA ARCHITECTURE:
                  - Both layers running in parallel
                  - Batch layer: accurate historical data (cold path)
                  - Stream layer: real-time approximation (hot path)
                  - Serving layer: merges results
                  - Problem: maintain two codebases, complex merging

                  KAPPA ARCHITECTURE:
                  - Unified streaming pipeline only
                  - Reprocessing done by replaying Kafka events
                  - Simpler: one codebase handles both real-time and historical
                  - Trade-off: Kafka must retain data long enough for reprocessing

                  LATE EVENTS & WATERMARKS:
                  - Events arrive out of order due to network delays
                  - Watermark: system's estimate of "how far behind" events can be
                  - Typical watermark: 15 seconds (configurable per use case)
                  - Events beyond watermark: dropped or sent to DLQ for later correction

                  WINDOWING:
                  - Tumbling: [0-60s], [60-120s] — non-overlapping, full coverage
                  - Sliding: [0-60s], [30-90s] — overlapping, good for moving averages
                  - Session: grouped by user inactivity gap

Example:          Ad click aggregation:
                  - Stream path: Kafka → Flink → aggregate per 1-minute tumbling window
                  - Daily reconciliation: batch job recalculates from raw logs
                  - Watermark of 15s handles delayed mobile click events

Trade-offs:       Batch: Simple, accurate, latency measured in hours/minutes
                  Stream: Low latency, complex (late events, state management, exactly-once)
                  Lambda: Maximum accuracy at maximum complexity
                  Kappa: Simplified operations, Kafka storage cost
Decision Rule:    Latency requirement < 1 minute? → Stream processing
                  Historical analysis / ML training? → Batch processing
                  Both real-time AND historical accuracy? → Lambda (accept complexity) or Kappa
                  Ad click / financial event aggregation? → Kappa with watermarking
Related Concepts: → Message Queue Internals
                  → Event Sourcing
Related Patterns:  → P8: Write-Ahead Log (WAL)
                  → P12: Dead Letter Queue (late events + DLQ)
Source:           System Design Interview Vol. 2, Chapter on Ad Click Event Aggregation
```

---

### K13: Fanout Strategies — Push vs Pull vs Hybrid

```
Title:            Fanout Strategies — Push vs Pull vs Hybrid
Type:             Concept
Domain:           Architecture
Difficulty:       Intermediate
Summary:          When a user posts content that N followers must receive, three delivery
                  strategies determine when and how that delivery happens, each optimizing
                  differently for write latency, read latency, and resource use.
Deep Dive:        FANOUT ON WRITE (Push model):
                  - On post: immediately compute and push to all followers' feed caches
                  - Read: instant (pre-computed, just read from cache)
                  - Write: slow and expensive (10M followers = 10M cache writes on one post)
                  - Celebrity problem: one write causes 10M operations
                  - Memory: stores N copies of every post (one per follower feed)

                  FANOUT ON READ (Pull model):
                  - On read: fetch posts from all people user follows, merge, sort
                  - Write: instant (just write to author's store)
                  - Read: slow (fan out on read time, N network calls)
                  - Fresh data: always up-to-date
                  - Good for: inactive users (no waste computing their feeds)

                  HYBRID (Instagram/Twitter approach):
                  - Regular users (< threshold followers): fanout on write
                  - Celebrities (> threshold): fanout on read
                  - Threshold: typically 10,000-100,000 followers
                  - On read: merge pre-computed feed + freshly-fetched celebrity posts

                  CACHE ARCHITECTURE for feeds (5 tiers common):
                  1. Newsfeed cache: sorted list of post IDs per user
                  2. User cache: user profile data
                  3. Post cache: post metadata
                  4. Social graph cache: follower/following lists
                  5. Counter cache: likes, comments counts

Example:          Twitter hybrid fanout:
                  - Katy Perry (100M followers) posts → only write to her post DB
                  - Regular users' posts → immediately pushed to followers' feed caches
                  - On read: combine pre-computed feed + Perry's latest post

Trade-offs:       Push: Fast reads, expensive writes, wastes compute for inactive users
                  Pull: Fast writes, slow reads, always fresh
                  Hybrid: Balanced, adds complexity for celebrity detection
Decision Rule:    Social platform with celebrities (some users >> followers)? → Hybrid
                  All users have similar follower counts? → Push (fast reads)
                  Low DAU, mostly read-heavy? → Pull
Related Concepts: → CDN Strategy
                  → CAP Theorem
Related Patterns:  → P3, P4, P5: Fanout patterns
Source:           System Design Interview Vol. 1, Chapter 11 (News Feed)
```

---

### K14: WebSocket vs HTTP Polling vs Long Polling

```
Title:            WebSocket vs HTTP Polling vs Long Polling
Type:             Concept
Domain:           API Design
Difficulty:       Intermediate
Summary:          Three protocols for server-to-client communication with different
                  trade-offs between real-time latency, connection overhead, and complexity.
Deep Dive:        1. SHORT POLLING:
                  - Client repeatedly sends HTTP requests every T seconds
                  - Server responds immediately (empty if nothing new)
                  - Simple, works everywhere
                  - Wasteful: most responses are empty, consumes server resources

                  2. LONG POLLING:
                  - Client sends request, server holds it open until data is available
                  - Server responds when there's data (or after timeout ~30s)
                  - Reduces empty responses vs polling
                  - Still HTTP overhead per message, connection held open
                  - Better for: infrequent updates (file sync notifications, Google Drive)

                  3. WEBSOCKET:
                  - Full-duplex persistent connection over single TCP connection
                  - Low overhead: no HTTP headers after handshake
                  - Bidirectional: server and client can send anytime
                  - Stateful: server must track active connections
                  - Scaling challenge: sticky sessions or shared connection state
                  - Best for: chat, real-time location, collaborative editing

                  MEMORY COST:
                  - Each WebSocket connection: ~10KB server-side memory
                  - 1M concurrent connections = ~10GB RAM
                  - Plan connection servers at 100K-1M connections per server

                  SERVER-SENT EVENTS (SSE):
                  - One-way stream from server to client
                  - Simpler than WebSocket (HTTP-based)
                  - Good for: live scores, stock tickers, news feeds

Example:          Chat system (50M DAU, 1M concurrent):
                  - WebSocket for message delivery (bidirectional, low latency)
                  - REST API for everything else (login, profile, history)
                  - Presence server via heartbeat over WebSocket (every 5s)
                  - Service discovery (Zookeeper) to route user to correct chat server

Trade-offs:       Short polling: Simple, high server load, high latency
                  Long polling: Lower load than polling, still HTTP overhead
                  WebSocket: Low latency, full-duplex, stateful (complex scaling)
Decision Rule:    Message delivery, live location, collaborative editing? → WebSocket
                  File sync notifications, infrequent server push? → Long polling
                  One-way data feed (prices, scores)? → Server-Sent Events
                  Simple read API? → REST (no persistent connection needed)
Related Concepts: → Back-of-the-Envelope Estimation
                  → CDN Strategy
Source:           System Design Interview Vol. 1, Chapter 12 (Chat), Vol. 2 (Nearby Friends, Maps)
```

---

### K15: CDN Strategy & Cache Layers

```
Title:            CDN Strategy & Cache Layers
Type:             Concept
Domain:           Scalability
Difficulty:       Intermediate
Summary:          Multi-tier caching architecture using CDNs for static assets and distributed
                  caches for dynamic data, reducing DB load and improving global latency.
Deep Dive:        CDN (CONTENT DELIVERY NETWORK):
                  - Geographically distributed proxy servers
                  - Cache static content (HTML, CSS, JS, images, videos) close to users
                  - Push CDN: pre-populate on publish
                  - Pull CDN: lazy populate on first request, then cache by TTL
                  - Cost consideration: CDN egress is expensive (~$0.02-0.08/GB)
                    YouTube CDN: ~$150,000/day at full scale
                  - Strategy: popular content (top 20%) → CDN; long-tail → S3 only

                  CACHE HIERARCHY:
                  L1: Client-side (browser cache, mobile app cache) — 0ms latency
                  L2: CDN edge nodes — ~10ms (nearest PoP)
                  L3: API gateway cache — ~1ms (same datacenter)
                  L4: Application-level (Redis/Memcached) — ~1ms (same datacenter)
                  L5: Database query cache — part of DB, limited size

                  CACHE INVALIDATION STRATEGIES:
                  - TTL (Time-to-Live): simple, may serve stale data
                  - Cache-aside (lazy): miss → DB → cache; stale on write
                  - Write-through: write to cache + DB simultaneously; consistent, slower write
                  - Write-behind (write-back): write to cache first, async to DB; fast write, data loss risk
                  - Event-driven invalidation (CDC): Debezium watches DB changes, invalidates cache

                  CACHE EVICTION POLICIES:
                  - LRU (Least Recently Used): evict item not accessed longest — most common
                  - LFU (Least Frequently Used): evict item accessed least often
                  - FIFO: evict oldest inserted item

                  HOT KEY / HOTSPOT:
                  - Popular key (celebrity tweet) overwhelms single cache shard
                  - Solutions: replicate to multiple shards, client-side caching, Bloom filter

Example:          Google Maps CDN:
                  - 100 PB of precomputed map tiles
                  - Popular areas cached at CDN edge nodes globally
                  - Long-tail areas served from regional S3 on first request
                  - Vector tiles smaller than raster → lower CDN egress cost

Trade-offs:       CDN: Lower latency globally, expensive, invalidation complexity
                  Redis: Fast dynamic data, memory limited, single-region
                  Write-through: Consistent, slower writes
                  Write-behind: Fast writes, risk of data loss on crash
Decision Rule:    Static assets (images, videos, CSS, tiles)? → CDN
                  Dynamic hot data (sessions, feed IDs, leaderboard)? → Redis
                  Read > write by 10:1? → Add caching layer
                  Cache hit ratio < 80%? → Increase TTL or cache size
Related Concepts: → Database Sharding Strategies
                  → Back-of-the-Envelope Estimation
Related Patterns:  → P3: Fanout on Write (Push Model)
                  → P5: Hybrid Fanout
Source:           System Design Interview Vol. 1, Ch. 1, 11; Vol. 2, Maps, YouTube
```

---

### K16: Database Sharding Strategies

```
Title:            Database Sharding Strategies
Type:             Concept
Domain:           DB Performance
Difficulty:       Intermediate
Summary:          Horizontal partitioning splits data across multiple DB nodes using a shard
                  key. Strategy selection determines query patterns, hot spot risk, and
                  operational complexity.
Deep Dive:        SHARDING STRATEGIES:

                  1. HASH SHARDING:
                  - shard = hash(key) % num_shards
                  - Uniform distribution
                  - Resharding is expensive (most keys move)
                  - Fix resharding with consistent hashing

                  2. RANGE SHARDING:
                  - Shard by value range (e.g., user_id 0-1M → shard 1)
                  - Good for range queries (find all users in region X)
                  - Risk: hot shards if data isn't uniformly distributed

                  3. DIRECTORY SHARDING:
                  - Lookup table maps key → shard
                  - Maximum flexibility (move data without rehashing)
                  - Lookup table is a single point of failure

                  4. GEO SHARDING:
                  - Shard by geography (US users → US shard)
                  - Minimizes cross-region latency
                  - Data sovereignty compliance (GDPR)

                  RESHARDING:
                  - Required when: single shard too large, traffic too high for one shard
                  - Consistent hashing minimizes key movement
                  - Double-write during migration: write to old + new shard

                  HOTSPOT / CELEBRITY PROBLEM:
                  - All writes go to one shard (e.g., Justin Bieber → shard 3 overloaded)
                  - Solution: add virtual ID suffix (key + "_1", key + "_2")
                  - This distributes hot key across multiple shards, requiring scatter-gather on read

                  JOIN COMPLEXITY:
                  - Cross-shard joins are expensive (scatter-gather or denormalization)
                  - Best practice: denormalize heavily in sharded systems

Example:          Hotel reservation system:
                  - Shard by hotel_id (geo-locality, all rooms for a hotel in one shard)
                  - Reservation query: always has hotel_id → direct shard lookup
                  - 73M rows / 10 shards = 7.3M rows per shard (manageable)

Trade-offs:       Hash: Even distribution, no range queries, resharding cost
                  Range: Range queries, hot shards possible
                  Directory: Flexible, lookup table bottleneck
                  Geo: Compliance, cross-region queries needed for global users
Decision Rule:    Queries always include shard key? → Hash sharding
                  Need range queries on shard key? → Range sharding
                  Need to relocate data? → Directory sharding
                  Compliance / latency per region? → Geo sharding
Related Concepts: → Consistent Hashing
                  → Back-of-the-Envelope Estimation
Related Patterns:  → P2: Consistent Hashing Ring
                  → P7: Scatter-Gather
Source:           System Design Interview Vol. 1, Ch. 1; Vol. 2, Email, Hotel
```

---

### K17: LSM Tree & SSTables

```
Title:            LSM Tree & SSTables
Type:             Concept
Domain:           DB Performance
Difficulty:       Advanced
Summary:          Log-Structured Merge-Tree converts random writes into sequential disk writes,
                  making it ideal for write-heavy workloads like email indexing, time-series data,
                  and wide-column stores.
Deep Dive:        LSM TREE COMPONENTS:
                  1. MemTable: in-memory sorted write buffer (balanced BST)
                  2. WAL (Write-Ahead Log): durability for MemTable before flush
                  3. SSTables: immutable sorted files on disk
                  4. Compaction: periodic merge of SSTables to remove duplicates/tombstones

                  WRITE PATH:
                  1. Write to WAL (for crash recovery)
                  2. Write to MemTable (in-memory sorted structure)
                  3. When MemTable full → flush to disk as SSTable
                  4. Background: compact multiple SSTables into larger ones

                  READ PATH:
                  1. Check MemTable (latest writes)
                  2. Check SSTables in level order (newest first)
                  3. Bloom filter optimization: skip SSTables that provably don't contain key
                  4. Sparse index: jump to approximate position in SSTable

                  BLOOM FILTER:
                  - Probabilistic data structure: tells if key "definitely not" in SSTable
                  - False positive possible, false negative impossible
                  - Dramatically reduces unnecessary SSTable reads

                  COMPACTION STRATEGIES:
                  - Size-tiered: merge similarly-sized SSTables
                  - Leveled: SSTables organized by level, each level 10x larger
                    Cassandra default, good for read-heavy workloads after compaction

                  USED IN: RocksDB, LevelDB, Cassandra, HBase, BigTable

Example:          Email search (Elasticsearch under the hood uses Lucene which uses LSM):
                  - 82% of queries access data < 16 days old → hot data in upper levels
                  - Compaction in background keeps read performance stable
                  - Bloom filter prevents reading all segments for unknown keys

Trade-offs:       Pros: High write throughput, sequential I/O, no random disk seeks
                  Cons: Read amplification (check multiple SSTables), compaction I/O spikes,
                        higher space amplification (multiple copies during compaction)
Decision Rule:    Write-heavy (time series, logs, events)? → LSM-based DB (Cassandra, RocksDB)
                  Read-heavy with complex queries? → B-Tree DB (PostgreSQL, MySQL)
                  Need full-text search? → Elasticsearch (Lucene = LSM-based)
Related Concepts: → Message Queue Internals
                  → Event Sourcing
Related Patterns:  → P8: Write-Ahead Log (WAL)
Source:           System Design Interview Vol. 2, Email Service, Distributed Message Queue
```

---

### K18: Message Queue Internals — WAL, Partitions, ISR

```
Title:            Message Queue Internals — WAL, Partitions, ISR
Type:             Framework Knowledge
Domain:           Event-Driven
Difficulty:       Advanced
Summary:          How Kafka achieves high throughput, durability, and exactly-once semantics
                  through append-only logs, partitioned topics, and in-sync replica management.
Deep Dive:        CORE COMPONENTS:
                  - Topic: logical stream of messages
                  - Partition: ordered, append-only log (physical unit of parallelism)
                  - Segment: partition split into bounded files (compaction and retention)
                  - Offset: position of a message within a partition

                  WRITE PATH:
                  1. Producer sends to partition (by key or round-robin)
                  2. Leader writes to WAL (disk, sequential = fast)
                  3. Followers replicate from leader
                  4. ACK returned based on ack level (0, 1, all)

                  ACK LEVELS:
                  - ack=0: fire and forget (fastest, can lose data)
                  - ack=1: leader ack only (fast, lose data if leader crashes before replication)
                  - ack=all: all ISR replicas must ack (slowest, safest)

                  IN-SYNC REPLICAS (ISR):
                  - Set of replicas that are caught up with leader
                  - ISR criteria: replica lag < threshold (configurable)
                  - If replica falls behind: removed from ISR, catches up asynchronously
                  - min.insync.replicas: minimum ISR size for ack=all writes to succeed

                  BATCHING:
                  - Producers batch messages before sending (configurable linger.ms and batch.size)
                  - Higher batching = higher throughput, higher latency
                  - Trade-off: batch.size=64KB is good starting point

                  PULL MODEL (consumers pull from broker):
                  - Consumers control their own pace (no broker push overload)
                  - Consumer can catch up at its own speed
                  - Compare: push model can overwhelm slow consumers

                  CONSUMER GROUPS:
                  - Multiple consumers in same group share partitions
                  - Each partition owned by exactly one consumer per group
                  - Rebalancing on consumer join/leave

                  RETENTION:
                  - Kafka retains messages for configurable duration (e.g., 2 weeks)
                  - Allows consumer replay (Kappa architecture)

Example:          Metrics monitoring system:
                  - 250,000 writes/second into Kafka
                  - Stream processors (Flink) consume and aggregate into 1-minute windows
                  - Kafka retention: 7 days (for replay after bug fix)
                  - ack=1 for metrics (acceptable to lose a few data points)

Trade-offs:       ack=all: Durable, higher write latency
                  ack=1: Fast writes, possible data loss on leader crash
                  Large batch: High throughput, higher end-to-end latency
                  Many partitions: High parallelism, high resource overhead (file handles, memory)
Decision Rule:    Financial events (payment, order)? → ack=all + min.insync.replicas=2
                  Metrics, logs (loss-tolerant)? → ack=1 or ack=0
                  High throughput analytics? → Large batches + many partitions
                  Need ordered processing per entity? → Partition by entity key
Related Concepts: → Stream vs Batch Processing
                  → Event Sourcing
                  → Retry + DLQ (kos-patterns.md #5)
Related Patterns:  → P14: Transactional Outbox
                  → P12: Dead Letter Queue (DLQ) with Reconciliation
Source:           System Design Interview Vol. 2, Chapter on Distributed Message Queue
```

---

### K19: Erasure Coding vs Replication

```
Title:            Erasure Coding vs Replication
Type:             Concept
Domain:           Distributed Systems
Difficulty:       Advanced
Summary:          Two durability strategies for distributed storage. Replication (3x copies)
                  is simple but expensive. Erasure coding (4+2, 8+4) reduces overhead to
                  ~50% while maintaining durability, at the cost of read/write complexity.
Deep Dive:        3× REPLICATION:
                  - Store 3 copies on 3 different nodes
                  - Overhead: 200% (3 bytes stored per 1 byte of data)
                  - Durability: survive 2 node failures
                  - Read: read from any replica (fast, simple)
                  - Write: write to all 3 replicas (simple)
                  - Recovery: copy from surviving replica (fast)

                  ERASURE CODING (Reed-Solomon):
                  - Split data into k data chunks + m parity chunks
                  - Can reconstruct from any k chunks out of (k+m)
                  - Common configs:
                    4+2: 6 chunks, tolerate 2 failures, overhead = 50%
                    8+4: 12 chunks, tolerate 4 failures, overhead = 50%
                  - Overhead: 50% (much cheaper than 3x = 200%)
                  - Write: compute parity across all chunks (CPU-intensive)
                  - Read: reconstruct from fragments (slower than direct copy)
                  - Recovery: rebuild from k surviving chunks (complex, CPU-intensive)

                  WHEN TO USE EACH:
                  - Replication: hot data, frequent reads, simplicity needed
                  - Erasure coding: cold/warm data, storage cost matters, batch reads OK

                  HYBRID (AWS S3 approach):
                  - Hot buckets: replication for fast access
                  - Cold/Glacier: erasure coding for cost efficiency

Example:          S3-like object storage:
                  - New uploads: 3x replication for immediate durability + fast access
                  - After 30 days if not accessed: migrate to erasure coding (4+2)
                  - Saves 50% storage cost for 80% of data (long tail)

Trade-offs:       Replication: Simple, fast recovery, expensive (200% overhead)
                  Erasure coding: 50% overhead, slow recovery, CPU-intensive writes, complex
Decision Rule:    Hot data (accessed daily)? → Replication
                  Cold data (accessed monthly or less)? → Erasure coding
                  Storage cost is primary concern? → Erasure coding
                  Simplicity and fast recovery? → Replication
Related Concepts: → Quorum Consensus
                  → CAP Theorem
Source:           System Design Interview Vol. 2, Chapter on S3-like Object Storage
```

---

### K20: Idempotency in Distributed Systems

```
Title:            Idempotency in Distributed Systems
Type:             Concept
Domain:           Resilience
Difficulty:       Intermediate
Summary:          An operation is idempotent if executing it multiple times produces the
                  same result as executing it once. Critical for safe retries in at-least-once
                  delivery systems.
Deep Dive:        WHY IT MATTERS:
                  - Kafka: at-least-once delivery = same message may be processed twice
                  - HTTP: retries after timeout = operation may execute twice
                  - Payment: double-charge = catastrophic
                  - Order creation: duplicate order = inventory incorrect

                  IDEMPOTENCY KEY APPROACHES:

                  1. CLIENT-GENERATED KEY:
                  - Client generates UUID per request (idempotency_key header)
                  - Server checks if key exists in DB before processing
                  - If exists: return cached result
                  - If not: process and store result with key

                  2. DATABASE CONSTRAINT:
                  - UNIQUE constraint on natural key (order_id, payment_id)
                  - Duplicate insert fails with constraint violation
                  - Return existing record on constraint violation

                  3. CONDITIONAL UPDATE:
                  - Only update if current state matches expected state
                  - SQL: UPDATE orders SET status='paid' WHERE id=X AND status='pending'
                  - Returns 0 rows updated if already paid (safe re-execution)

                  4. EVENT DEDUPLICATION TABLE:
                  - Track processed event IDs (Kafka offset or correlation ID)
                  - Before processing: check if event_id already in processed_events table
                  - TTL on processed events (keep for duplicate window, e.g., 24h)

                  PAYMENT IDEMPOTENCY:
                  - Idempotency key = client-generated UUID per payment attempt
                  - Stored with transaction result
                  - On retry: return same result without re-charging
                  - Key expires after 24-48 hours (payment retries happen quickly)

Example:          // Hotel reservation double-booking prevention
                  // Database constraint approach:
                  UPDATE room_inventory
                  SET reserved_count = reserved_count + 1
                  WHERE hotel_id = X AND date = Y AND reserved_count < total_count
                  -- Returns 0 rows if full → application raises "no rooms available"
                  -- Safe to retry: if already booked, returns 0 rows (no duplicate)

Trade-offs:       Key storage: Extra DB table for processed keys (storage overhead)
                  TTL: Keys must expire (choose window carefully — too short = duplicate allowed)
                  Natural key: Cleanest, only works when natural key exists
Decision Rule:    Payment or order creation? → Client-generated idempotency key mandatory
                  Kafka consumer? → Deduplication table with TTL
                  State machine transition? → Conditional update (most robust)
Related Concepts: → Distributed Transactions
                  → Message Queue Internals
Related Patterns:  → P15: Idempotency Key
                  → P12: Dead Letter Queue (DLQ) with Reconciliation
Source:           System Design Interview Vol. 2, Payment System, Hotel Reservation
```

---

### K21: Trie Data Structure for Autocomplete

```
Title:            Trie Data Structure for Autocomplete
Type:             Concept
Domain:           Data
Difficulty:       Intermediate
Summary:          A tree where each node represents a character prefix. Stores top-K most
                  frequent queries at each node, enabling O(prefix_length) autocomplete
                  with bounded memory.
Deep Dive:        BASIC TRIE:
                  - Root node represents empty string
                  - Each edge = one character
                  - Node at depth d = prefix of length d
                  - Terminal nodes marked (end of word)
                  - Search for "tree": follow t → r → e → e

                  OPTIMIZED TRIE FOR AUTOCOMPLETE:
                  - Store top-K (e.g., 5) most frequent queries at every node
                  - Trade-off: O(1) retrieval vs. extra storage per node
                  - Update: weekly batch recalculation (not real-time)
                  - Why weekly: freshness < 1 week is fine for search suggestions

                  MEMORY ESTIMATE:
                  - 100M DAU × 10 searches × 0.4GB daily = ~40 GB (compressed)
                  - Only top 5 suggestions per node → bounded memory
                  - Cache entire trie in Redis/Memcached

                  SHARDING BY PREFIX:
                  - Historical data (queries starting with 'a') → shard 1
                  - Queries starting with 'b' → shard 2
                  - Up to 26 shards for first character
                  - Uneven distribution: further split ('aa'-'ag' → shard 1, etc.)

                  DATA COLLECTION PIPELINE:
                  - Analytics logs (append-only raw query log)
                  - Aggregators: batch aggregate by week
                  - Workers: rebuild trie from aggregated data
                  - Trie storage: document or key-value store
                  - Serving: cached in memory, rebuilt weekly

                  FILTER LAYER:
                  - Block inappropriate content
                  - Applied at trie build time (not at query time)
                  - Allowlist/blocklist of banned terms

Example:          Search QPS: 24,000 avg, 48,000 peak
                  Response requirement: < 100ms
                  Solution: trie built weekly, served from memory cache
                  On miss (new prefix never seen): return empty suggestions

Trade-offs:       Pros: O(1) top-K lookup per prefix, pre-sorted, bounded memory
                  Cons: Weekly rebuild = slight staleness, large memory for full trie
Decision Rule:    Search bar autocomplete with millions of queries? → Trie with top-K per node
                  Real-time suggestions required? → Trie + streaming update (complex)
                  Simple exact-match completion? → Hash map is sufficient
Related Concepts: → CDN Strategy (cache the trie)
                  → Stream vs Batch Processing
Source:           System Design Interview Vol. 1, Chapter 13 (Search Autocomplete)
```

---

### K22: Time-Series Database Design

```
Title:            Time-Series Database Design
Type:             Concept
Domain:           DB Performance
Difficulty:       Intermediate
Summary:          Time-series data (metric name + timestamp + value) has unique patterns:
                  write-heavy, mostly sequential reads, high cardinality, and queries by
                  time range. Specialized TSDBs (InfluxDB, Prometheus) outperform RDBMS
                  by 10-100x for this workload.
Deep Dive:        CHARACTERISTICS OF TIME-SERIES DATA:
                  - Write: continuous high-rate inserts (no updates/deletes)
                  - Read: range queries (last 5 minutes, last 24 hours)
                  - Cardinality: millions of metric label combinations
                  - Retention: raw data (7 days) → downsampled (30 days, 1 year)

                  WHY NOT RELATIONAL DB:
                  - No updates needed → append-only is more efficient
                  - Range queries → B-tree is poor, time-series compression is better
                  - High cardinality → relational indexes too large
                  - InfluxDB writes at 250,000+ per second; MySQL/PostgreSQL ~10,000/second

                  DOWNSAMPLING:
                  - Raw data: every 10 seconds (7 days retention)
                  - 1-minute resolution: 30 days retention
                  - 1-hour resolution: 1 year retention
                  - Purpose: reduce storage 6x at each level
                  - Done by: aggregation jobs (min, max, avg, p99 per window)

                  METRICS COLLECTION:
                  Pull model (Prometheus):
                  - Collector scrapes each service's /metrics endpoint
                  - Service must expose HTTP endpoint
                  - Simpler debugging (you can see what's being exported)
                  Push model (StatsD, DataDog agent):
                  - Service pushes to central collector
                  - Better for short-lived jobs, serverless, strict firewall

                  ALERTING PIPELINE:
                  - Alert rules: IF cpu_usage > 80% for 5 minutes → alert
                  - Alert manager: deduplicates, groups, routes alerts
                  - Channels: email, PagerDuty, Slack, OpsGenie

Example:          System monitoring (100M DAU, 10M metrics):
                  - 250,000 writes/second into Kafka
                  - Flink aggregates into 1-minute windows
                  - InfluxDB for raw + aggregated time-series
                  - Grafana for visualization
                  - Alert rules in YAML, evaluated every 60 seconds

Trade-offs:       TSDB: Fast writes, efficient range queries, downsampling support
                  RDBMS: Complex queries, joins, familiar tools — poor at scale for metrics
Decision Rule:    Infrastructure metrics, IoT telemetry, financial ticks? → TSDB
                  Business events with complex joins? → RDBMS + aggregation pipeline
Related Concepts: → Stream vs Batch Processing
                  → LSM Tree & SSTables (most TSDBs use LSM internally)
Source:           System Design Interview Vol. 2, Metrics Monitoring and Alerting System
```

---

### K23: Double-Entry Ledger System

```
Title:            Double-Entry Ledger System
Type:             Concept
Domain:           Architecture
Difficulty:       Advanced
Summary:          Every financial transaction records both a debit and a credit to ensure
                  the sum of all entries is always zero. This provides correctness guarantees
                  and auditability for financial systems.
Deep Dive:        PRINCIPLE:
                  - For every transaction: debit one account + credit another account
                  - Sum of all debits == sum of all credits (always)
                  - Account balance = sum of all credits - sum of all debits
                  - Never delete entries (append-only ledger)

                  SCHEMA:
                  ledger table:
                    id, from_account, to_account, amount, currency,
                    transaction_id, timestamp, balance_snapshot

                  For $1 transfer (A → B):
                    INSERT (from=A, to=B, amount=1.00)  -- debit A, credit B
                    Account A balance: -1.00
                    Account B balance: +1.00
                    Invariant: sum = 0

                  RECONCILIATION:
                  - End-of-day: recalculate all balances from ledger entries
                  - Compare with expected balances
                  - Any discrepancy = system bug or data corruption
                  - PSP settlement files reconciled against internal ledger

                  CURRENCY REPRESENTATION:
                  - NEVER store money as float (floating point arithmetic errors)
                  - Store as integer cents (100 = $1.00) or use Decimal type
                  - String representation for display only

                  IDEMPOTENCY IN PAYMENTS:
                  - Each transaction has unique idempotency_key
                  - Retry with same key → return same ledger entry, no new entry

Example:          Digital wallet transfer $100 (A → B):
                  -- Atomic transaction:
                  INSERT INTO ledger (from='A', to='B', amount=100, tx_id='uuid-1')
                  UPDATE accounts SET balance = balance - 100 WHERE id='A'
                  UPDATE accounts SET balance = balance + 100 WHERE id='B'
                  -- If crash: replay from ledger (event sourcing)

Trade-offs:       Pros: Mathematically correct, auditable, tamper-evident
                  Cons: More complex queries for balance, storage grows with transactions
Decision Rule:    Any financial transfer system? → Double-entry ledger mandatory
                  Simple counter or game score? → Single-row balance update is sufficient
Related Concepts: → Event Sourcing (ledger IS an event log)
                  → Idempotency in Distributed Systems
                  → Distributed Transactions
Related Patterns:  → P11: Hosted Payment Page
Source:           System Design Interview Vol. 2, Payment System, Digital Wallet
```

---

### K24: Matching Engine & Order Book Design

```
Title:            Matching Engine & Order Book Design
Type:             Concept
Domain:           Architecture
Difficulty:       Advanced
Summary:          The core of a stock exchange: an order book is a sorted data structure
                  of buy/sell orders, and a matching engine finds counterparts. Both must
                  operate at microsecond latency with deterministic behavior.
Deep Dive:        ORDER BOOK STRUCTURE:
                  - Bid side (buyers): sorted descending by price
                  - Ask side (sellers): sorted ascending by price
                  - Each price level: doubly-linked list of orders (FIFO at same price)
                  - Match when: highest bid >= lowest ask

                  DATA STRUCTURES:
                  - Price levels: Red-Black Tree or Skip List → O(log n) insert/delete
                  - Orders at same price: Doubly-linked list → O(1) add/remove
                  - Price-to-orders lookup: HashMap → O(1) access to any price level

                  PERFORMANCE:
                  - Target: 1 million orders/second
                  - Solution: keep entire order book in RAM
                  - Avoid GC: pre-allocate object pools
                  - CPU pinning: pin matching engine thread to dedicated core
                  - Lock-free: use ring buffers (Disruptor pattern) between components

                  SEQUENCER:
                  - All incoming orders assigned a strictly monotonic sequence number
                  - Sequence number = canonical order of events
                  - Replay from sequence 1 = deterministic reconstruction of order book
                  - Critical for: crash recovery, hot/warm standby sync

                  FAIRNESS:
                  - Market data distributed via UDP multicast (all subscribers receive simultaneously)
                  - Prevents latency arbitrage from sequential delivery

                  HOT-WARM STANDBY:
                  - Hot standby: processes same events, in-memory state mirrors primary
                  - Warm standby: receives events, doesn't process (faster failover on switch)
                  - Failover: promote hot standby (sub-second) or warm (seconds)

Example:          NYSE matching engine:
                  - 43,000 average QPS, 215,000 peak QPS
                  - 100 symbols, 1B orders/day
                  - Single thread on dedicated core (no lock contention)
                  - mmap on /dev/shm for sub-microsecond inter-process messaging
                  - Ring buffer (Disruptor) for sequencer → matching engine → market data

Trade-offs:       Single server: Ultra-low latency, not horizontally scalable
                  Distributed: Scalable, complex coordination, higher latency
Decision Rule:    Ultra-low latency financial matching? → Single server + ring buffer + CPU pin
                  General-purpose order processing (e-commerce)? → Distributed, eventual
Related Concepts: → Event Sourcing (sequencer = event log)
                  → Message Queue Internals
Source:           System Design Interview Vol. 2, Chapter on Stock Exchange
```

---

### K25: EF Core DbContext Thread Safety and IDbContextFactory

```
Title:            EF Core DbContext is Not Thread-Safe — IDbContextFactory Required
Type:             Framework Knowledge
Domain:           DB Performance
Difficulty:       Intermediate
Summary:          A single EF Core DbContext cannot be used concurrently from multiple threads.
                  Parallel DB tasks require separate DbContext instances from IDbContextFactory.
Deep Dive:        EF Core DbContext maintains internal state: change tracker, query cache, connection.
                  Concurrent access from multiple threads causes race conditions and corrupted state.
                  IDbContextFactory<TContext> creates a fresh, isolated DbContext per task.
                  Register as Singleton: services.AddDbContextFactory<AppDbContext>(options => ...);
                  Use with await using to ensure disposal: await using var ctx = _factory.CreateDbContext();
                  Rule: 1 parallel task = 1 DbContext. No exceptions.
                  Sequential code with one scoped DbContext remains safe and preferred for single-path methods.
Example:          await using var ctx1 = _contextFactory.CreateDbContext();
                  await using var ctx2 = _contextFactory.CreateDbContext();
                  await Task.WhenAll(
                      GetOrderHeaderAsync(ctx1, orderId),
                      GetOrderPaymentsAsync(ctx2, orderId)
                  );
Trade-offs:       Pros: Enables true parallel DB queries; isolated change tracker per task
                  Cons: More connections per request (N tasks = N connections); extra DI registration
Decision Rule:    Single sequential method → injected _context (scoped, safe)
                  Parallel Task.WhenAll → IDbContextFactory, 1 context per task
                  Shared _context across Task.WhenAll → BLOCK, guaranteed race condition
Related Concepts: → Change Tracking and ORM Overhead
                  → Connection Pool Math (K — DB Performance)
Related Patterns: → P16: Async Parallel DB Coordinator
                  → P17: Batch Query (WHERE IN)
                  → P18: Eager Graph Loading
                  → P20: Bulk Load Then Map
Source:           incident2.cs Phase 4, 2026-03-27; EF Core Microsoft documentation
```

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

## TECH ASSETS

---

### TA1: Snowflake ID Generator (Go)

```
Name:             Snowflake ID Generator
Type:             Code Snippet
Language:         Go
Usage:            Use when service needs to generate globally unique, time-sortable 64-bit IDs.
                  One instance per machine — machine_id must be unique across cluster.

// Snippet:
const (
    epoch      int64 = 1700000000000 // custom epoch (ms)
    machineBits = 12
    sequenceBits = 12
)

type Snowflake struct {
    mu           sync.Mutex
    lastMs       int64
    machineID    int64
    sequence     int64
}

func (s *Snowflake) NextID() int64 {
    s.mu.Lock()
    defer s.mu.Unlock()

    now := time.Now().UnixMilli()
    if now == s.lastMs {
        s.sequence = (s.sequence + 1) & 0xFFF // 12-bit mask
        if s.sequence == 0 {
            for now <= s.lastMs {
                now = time.Now().UnixMilli()
            }
        }
    } else {
        s.sequence = 0
    }
    s.lastMs = now
    return (now-epoch)<<22 | s.machineID<<12 | s.sequence
}

Related Knowledge:  → Distributed Unique ID Generation (K5)
Related Pattern:   → P10: Snowflake ID Generation
```

---

### TA2: Redis Token Bucket Rate Limiter (Lua Script)

```
Name:             Redis Token Bucket Rate Limiter
Type:             Code Snippet
Language:         Lua / Redis
Usage:            Atomic rate limiting check using Redis. Execute via EVAL command.
                  Arguments: KEYS[1]=bucket_key, ARGV[1]=capacity, ARGV[2]=refill_rate,
                  ARGV[3]=current_timestamp

-- Snippet:
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

-- Refill tokens based on elapsed time
local elapsed = now - last_refill
local new_tokens = math.min(capacity, tokens + elapsed * refill_rate)

if new_tokens >= 1 then
    redis.call('HMSET', key, 'tokens', new_tokens - 1, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) + 1)
    return 1  -- allowed
else
    return 0  -- rejected
end

Related Knowledge:  → Rate Limiting Algorithms (K4)
Related Pattern:   → P1: Token Bucket Rate Limiting
```

---

### TA3: Geohash Neighbor Search (PostgreSQL)

```
Name:             Geohash Neighbor Search
Type:             Code Snippet
Language:         SQL / PostgreSQL
Usage:            Given a user's geohash, find all businesses within nearby cells.
                  Requires geohash extension or application-level neighbor computation.

-- Snippet:
-- Assume businesses table has geohash_6 column indexed
-- Given user's geohash '9q9p' and 8 neighbors computed in application:

SELECT id, name, lat, lon,
       (6371 * acos(
           cos(radians(:user_lat)) * cos(radians(lat))
           * cos(radians(lon) - radians(:user_lon))
           + sin(radians(:user_lat)) * sin(radians(lat))
       )) AS distance_km
FROM businesses
WHERE geohash_6 = ANY(:neighbor_hashes)  -- 9 geohash cells
  AND is_active = true
HAVING distance_km < :radius_km
ORDER BY distance_km
LIMIT 20;

-- Index:
CREATE INDEX idx_businesses_geohash ON businesses (geohash_6);

Related Knowledge:  → Geospatial Indexing (K9)
Related Pattern:   → P9: Geohash Bucketing
```

---

### TA4: Idempotency Key Table (PostgreSQL)

```
Name:             Idempotency Key Table with TTL cleanup
Type:             Pattern Implementation
Language:         SQL / PostgreSQL
Usage:            Prevent duplicate processing of payment or order creation requests.
                  Check before processing; insert after; cleanup with scheduled job.

-- Snippet:
CREATE TABLE idempotency_keys (
    key         VARCHAR(255) PRIMARY KEY,
    response    JSONB NOT NULL,
    status_code INT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Index for cleanup
CREATE INDEX idx_idempotency_created ON idempotency_keys (created_at);

-- Application logic (pseudocode):
-- 1. Check: SELECT response FROM idempotency_keys WHERE key = $1
-- 2. If found: return cached response (skip processing)
-- 3. Process request
-- 4. Insert: INSERT INTO idempotency_keys (key, response, status_code) VALUES ($1, $2, $3)
--    ON CONFLICT (key) DO NOTHING  -- handles race condition

-- Cleanup job (run daily):
DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours';

Related Knowledge:  → Idempotency in Distributed Systems (K20)
Related Pattern:   → P15: Idempotency Key
                  → P12: Dead Letter Queue with Reconciliation
```

---

### TA5: Double-Entry Ledger Schema (PostgreSQL)

```
Name:             Double-Entry Ledger Schema
Type:             Pattern Implementation
Language:         SQL / PostgreSQL
Usage:            Any financial transfer system. Every transaction creates two rows.
                  Balance = SUM of all entries for account. Never update or delete rows.

-- Snippet:
CREATE TABLE accounts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    UUID NOT NULL,
    currency    CHAR(3) NOT NULL,
    balance     BIGINT NOT NULL DEFAULT 0  -- stored in minor units (cents)
);

CREATE TABLE ledger_entries (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL,
    account_id     UUID NOT NULL REFERENCES accounts(id),
    amount         BIGINT NOT NULL,  -- positive = credit, negative = debit
    balance_after  BIGINT NOT NULL,  -- snapshot for quick audit
    currency       CHAR(3) NOT NULL,
    created_at     TIMESTAMP DEFAULT NOW(),
    idempotency_key VARCHAR(255) UNIQUE  -- prevent duplicate entries
);

-- Transfer $100 from A to B (atomic):
BEGIN;
  INSERT INTO ledger_entries (transaction_id, account_id, amount, balance_after, currency)
  VALUES (:tx_id, :account_a, -10000, :new_balance_a, 'USD');  -- debit A

  INSERT INTO ledger_entries (transaction_id, account_id, amount, balance_after, currency)
  VALUES (:tx_id, :account_b, +10000, :new_balance_b, 'USD');  -- credit B

  UPDATE accounts SET balance = balance - 10000 WHERE id = :account_a;
  UPDATE accounts SET balance = balance + 10000 WHERE id = :account_b;
COMMIT;

-- Invariant check: SUM(amount) = 0 for any transaction_id

Related Knowledge:  → Double-Entry Ledger System (K23)
                  → Idempotency in Distributed Systems (K20)
Related Pattern:   → P6: Event Sourcing Pattern
```

---

### TA6: Consistent Hashing Ring (Go)

```
Name:             Consistent Hashing Ring with Virtual Nodes
Type:             Pattern Implementation
Language:         Go
Usage:            Distribute keys across dynamic set of nodes.
                  Use for cache sharding, load balancing, or data partitioning.

// Snippet:
import (
    "crypto/sha256"
    "fmt"
    "sort"
)

type Ring struct {
    nodes    []int       // sorted hash positions
    nodeMap  map[int]string
    replicas int
}

func New(replicas int) *Ring {
    return &Ring{replicas: replicas, nodeMap: make(map[int]string)}
}

func (r *Ring) AddNode(node string) {
    for i := 0; i < r.replicas; i++ {
        hash := hashKey(fmt.Sprintf("%s-%d", node, i))
        r.nodes = append(r.nodes, hash)
        r.nodeMap[hash] = node
    }
    sort.Ints(r.nodes)
}

func (r *Ring) GetNode(key string) string {
    hash := hashKey(key)
    idx := sort.SearchInts(r.nodes, hash) % len(r.nodes)
    return r.nodeMap[r.nodes[idx]]
}

func hashKey(key string) int {
    h := sha256.Sum256([]byte(key))
    return int(h[0])<<24 | int(h[1])<<16 | int(h[2])<<8 | int(h[3])
}

Related Knowledge:  → Consistent Hashing (K3)
Related Pattern:   → P2: Consistent Hashing Ring
```

---

### TA7: Async Parallel DB Coordinator (.NET / EF Core)

```
Name:             Async Parallel DB Coordinator
Type:             Code Snippet
Language:         C#
Usage:            Coordinator method that fires independent DB calls in parallel using
                  Task.WhenAll + IDbContextFactory. Each task owns its own DbContext.
// Snippet:
// Register in Program.cs
services.AddDbContextFactory<AppDbContext>(options =>
    options.UseNpgsql(connectionString));

// Service constructor
private readonly IDbContextFactory<AppDbContext> _contextFactory;

// Async coordinator
public async Task<Result> GetSubOrderAsync(string orderId, string subOrderId)
{
    // Step 1: Serial prerequisites
    var subOrders = GetSubOrderMessage(orderId, subOrderId);
    string resolvedId = ResolveOnce(orderId);

    // Step 2: Parallel independent DB calls — each with own DbContext
    await using var ctx1 = _contextFactory.CreateDbContext();
    await using var ctx2 = _contextFactory.CreateDbContext();
    await using var ctx3 = _contextFactory.CreateDbContext();
    await using var ctx4 = _contextFactory.CreateDbContext();

    await Task.WhenAll(
        GetOrderHeaderAsync(ctx1, resolvedId),
        GetOrderPaymentsAsync(ctx2, resolvedId),
        GetOrderPromotionAsync(ctx3, resolvedId),
        GetRewardItemsBatchedAsync(ctx4, resolvedId, subOrders)
    );

    // Step 3: Assemble in memory — zero DB calls
}

// Private async method owns its context
private async Task<OrderModel> GetOrderHeaderAsync(DbContext ctx, string id)
{
    return await ctx.Set<OrderModel>()
        .AsNoTracking()
        .Include(o => o.Customer)
        .Where(o => o.SourceOrderId == id)
        .FirstOrDefaultAsync();
}
Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P16: Async Parallel DB Coordinator
```

---

### TA8: Stopwatch + GC Instrumentation (.NET)

```
Name:             Stopwatch + GC Instrumentation
Type:             Code Snippet
Language:         C#
Usage:            Measure wall-clock latency and GC allocation pressure on a hot-path method.
                  Use during diagnosis to confirm whether slowness is DB-bound or CPU/GC-bound.

// Snippet:
var sw = Stopwatch.StartNew();
long gcBefore = GC.GetTotalAllocatedBytes(precise: false);

// ... method under test ...

sw.Stop();
long gcAfter = GC.GetTotalAllocatedBytes(precise: false);
_logger.LogInformation(
    "GetSubOrder elapsed={ElapsedMs}ms alloc={AllocBytes}B",
    sw.ElapsedMilliseconds,
    gcAfter - gcBefore);

Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P17: Batch Query (WHERE IN)
```

---

### TA9: Prometheus Latency Histogram (.NET)

```
Name:             Prometheus Latency Histogram
Type:             Code Snippet
Language:         C# / Prometheus-net
Usage:            Record request latency distribution with labeled histograms.
                  Enables P50/P95/P99 breakdown per endpoint in Grafana.

// Snippet:
// Registration (startup):
private static readonly Histogram _latency = Metrics
    .CreateHistogram("getsuborder_duration_seconds",
        "GetSubOrder handler latency",
        new HistogramConfiguration
        {
            Buckets = Histogram.LinearBuckets(0.1, 0.1, 20), // 0.1s–2.0s
            LabelNames = new[] { "status" }
        });

// Usage (handler):
using (_latency.WithLabels("success").NewTimer())
{
    return await GetSubOrderAsync(sourceOrderId, sourceSubOrderId);
}

Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P16: Async Parallel DB Coordinator
```

---

### TA10: EF Core LogTo Diagnostic Configuration (.NET)

```
Name:             EF Core LogTo Diagnostic Configuration
Type:             Code Snippet
Language:         C# / EF Core
Usage:            Enable EF Core query logging to stdout or ILogger during local diagnosis.
                  Reveals generated SQL, parameter values, and round-trip count per request.

// Snippet:
// In DbContext.OnConfiguring (dev/staging only):
optionsBuilder
    .LogTo(Console.WriteLine, LogLevel.Information)
    .EnableSensitiveDataLogging()   // shows parameter values
    .EnableDetailedErrors();

// Or via ILogger (production-safe — filter by category):
optionsBuilder.LogTo(
    (eventId, _) => eventId.Id == RelationalEventId.CommandExecuted.Id,
    msg => _logger.LogDebug(msg));

Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P18: Eager Graph Loading
```

---

### TA11: GetSubOrderAsync Coordinator + Map Functions (.NET / EF Core)

```
Name:             GetSubOrderAsync Coordinator + Map Functions
Type:             Code Snippet
Language:         C#
Usage:            Full async coordinator with parallel DB calls and pure in-memory map functions.
                  Core output of the GetSubOrder Phase 1–4 refactor (incident2.cs).

// MapPayments — pure in-memory, no DB calls
private static List<PaymentModel> MapPayments(List<OrderMessagePayment> rows) =>
    rows.Select(r => new PaymentModel
    {
        PaymentId   = r.PaymentId,
        Amount      = r.Amount,
        Method      = r.PaymentMethod,
        PaidAt      = r.CreatedAt,
    }).ToList();

// MapPromotions — pure in-memory
private static List<PromotionModel> MapPromotions(List<OrderPromotion> rows) =>
    rows.Select(r => new PromotionModel
    {
        PromotionId = r.PromotionId,
        Discount    = r.Amount?.DiscountValue ?? 0,
        Type        = r.PromotionType,
    }).ToList();

// MapRewardItems — pure in-memory
private static List<RewardItemModel> MapRewardItems(List<RewardItem> rows) =>
    rows.Select(r => new RewardItemModel
    {
        RewardId    = r.RewardId,
        Points      = r.Points,
        ExpiresAt   = r.ExpiryDate,
    }).ToList();

Related Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Related Pattern:    → P16: Async Parallel DB Coordinator
                   → P20: Bulk Load Then Map
```

---

## 📎 Suggested Notion relations for this KOS

When importing into Notion, wire up these cross-database relations:

```
Knowledge → Knowledge (Related Concepts):
  K2 ↔ K6 ↔ K7 ↔ K8          (CAP, Quorum, Vector Clocks, Gossip — distributed consistency cluster)
  K3 ↔ K16 ↔ P2               (Consistent Hashing, Sharding, Ring Pattern)
  K10 ↔ K18 ↔ K23 ↔ P6 ↔ P8  (Event Sourcing, WAL, Ledger — financial correctness cluster)
  K11 ↔ K20 ↔ P12             (Distributed Transactions, Idempotency, DLQ)
  K12 ↔ K18 ↔ K22             (Stream/Batch, Kafka, Time-Series — data pipeline cluster)
  K13 ↔ P3 ↔ P4 ↔ P5          (Fanout strategies)

Knowledge → Pattern:
  K4 → P1 (Rate Limiting → Token Bucket)
  K3 → P2 (Consistent Hashing → Ring)
  K10 → P6 (Event Sourcing → Pattern)
  K16 → P7 (Sharding → Scatter-Gather)
  K5 → P10 (Snowflake ID → Pattern)
  K9 → P9 (Geospatial → Geohash Bucketing)

Decision Log → Knowledge + Pattern:
  D1 → K2 (CAP Theorem)
  D4 → K11 + K20 (Distributed Transactions + Idempotency)
  D3 → K19 (Erasure Coding)
  D5 → K4 + P1 (Rate Limiting Algorithms + Token Bucket)

Tech Assets → Knowledge + Pattern:
  TA1 → K5 + P10
  TA2 → K4 + P1
  TA3 → K9 + P9
  TA4 → K20 + Idempotency Key
  TA5 → K23 + P6
  TA6 → K3 + P2
```
