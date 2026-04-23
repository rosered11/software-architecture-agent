# KOS — Knowledge Records

> Cross-linked per the Incident → Knowledge → Pattern → Decision → Reuse loop.

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
                  → P23: Parallel Split Compiled Query
Related Incidents:→ I1: GetSubOrder API Latency Spike
Source:           incident2.cs Phase 4, 2026-03-27; EF Core Microsoft documentation
```

---

### K26: PostgreSQL MVCC and Dead Tuples

```
Title:            PostgreSQL MVCC and Dead Tuples
Type:             Concept
Domain:           DB Performance
Difficulty:       Intermediate
Summary:          PostgreSQL's MVCC model never overwrites rows in place — every UPDATE and DELETE
                  creates a dead tuple that remains in the heap and indexes until VACUUM reclaims it.
                  Uncleaned dead tuples degrade scan performance and bloat storage silently.
Deep Dive:        In MVCC, UPDATE = insert new row version + mark old version dead.
                  DELETE = mark row dead. Dead tuples remain visible to open transactions
                  that started before the operation — VACUUM cannot remove them until all such
                  transactions close (the "removable cutoff" XID).
                  Dead heap tuples: cause sequential scans to read wasted pages (+dead_ratio% I/O).
                  Dead index entries: remain in the B-tree, requiring visibility checks on every
                  index lookup — slowing range queries and PK lookups even when data is indexed.
                  VACUUM cleans heap + marks index pages "reusable" — but does NOT shrink index files.
                  Only REINDEX CONCURRENTLY produces a genuinely compact, dense B-tree.
                  Monitor via: pg_stat_user_tables (n_dead_tup, last_autovacuum, dead_ratio_pct)
Example:          SELECT relname, n_live_tup, n_dead_tup,
                    ROUND(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100, 2) AS dead_ratio_pct,
                    last_autovacuum
                  FROM pg_stat_user_tables ORDER BY n_dead_tup DESC;
Trade-offs:       Pros: MVCC enables non-blocking reads alongside writes (no read locks needed)
                  Cons: Dead tuples accumulate silently; require periodic VACUUM + REINDEX to reclaim
Decision Rule:    dead_ratio < 5%  → healthy
                  dead_ratio 5–10% → monitor, check autovacuum settings
                  dead_ratio > 10% → run VACUUM immediately
                  dead_ratio > 20% → incident — autovacuum is broken or blocked
Related Concepts: → K27: Autovacuum Scale Factor Trap for Large Tables
Related Patterns: → P21: Per-Table Storage Hygiene
Related Incidents:→ I2: PostgreSQL Dead Tuple Bloat — stockadjustments (2026-03-30)
Related Decisions:→ D12: REINDEX CONCURRENTLY vs VACUUM FULL
Related Tech Assets: → TA12: Dead Tuple Health Monitor Query
Source:           stockadjustments incident, spc_inventory, 2026-03-30
```

---

### K27: Autovacuum Scale Factor Trap for Large Tables

```
Title:            Autovacuum Scale Factor Trap for Large Tables
Type:             Framework Knowledge
Domain:           DB Performance
Difficulty:       Intermediate
Summary:          PostgreSQL's default autovacuum_vacuum_scale_factor = 0.20 requires 20% of live
                  rows to be dead before vacuum fires. On large tables this means hundreds of
                  thousands of dead rows accumulate silently — the default is calibrated for small
                  tables and must be overridden per-table in production.
Deep Dive:        Autovacuum trigger formula:
                    threshold = autovacuum_vacuum_threshold + autovacuum_vacuum_scale_factor × n_live_tup
                    Default:   50 + 0.20 × n_live_tup
                  Real incident: 4M-row table → threshold = 828,932 dead rows to trigger.
                  At incident detection: 702,783 dead rows (14.5%) — still 126,149 below threshold.
                  Autovacuum never fired — working as configured, but configuration was wrong.
                  Fix: per-table override with ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = 0.01)
                  This triggers at ~1% dead rows (~41K for a 4M-row table):
                  frequent, lightweight passes vs. one massive deferred cleanup.
                  Global postgresql.conf affects all tables; per-table settings override for that table only.
Example:          ALTER TABLE stockadjustments SET (
                    autovacuum_vacuum_scale_factor = 0.01,
                    autovacuum_vacuum_threshold = 1000,
                    autovacuum_analyze_scale_factor = 0.005,
                    autovacuum_analyze_threshold = 500
                  );
                  -- Verify:
                  SELECT relname, reloptions FROM pg_class WHERE relname = 'stockadjustments';
Trade-offs:       Pros: Prevents large bloat accumulation; each vacuum pass is small and fast
                  Cons: Autovacuum worker fires more often (negligible overhead on modern hardware)
Decision Rule:    table rows > 5M   → autovacuum_vacuum_scale_factor = 0.005
                  table rows > 500K → autovacuum_vacuum_scale_factor = 0.01
                  table rows > 100K → autovacuum_vacuum_scale_factor = 0.05
                  table rows < 100K → default 0.20 is fine
                  last_autovacuum IS NULL on large active table → scale_factor is almost certainly too high
Related Concepts: → K26: PostgreSQL MVCC and Dead Tuples
Related Patterns: → P21: Per-Table Storage Hygiene
Related Incidents:→ I2: PostgreSQL Dead Tuple Bloat — stockadjustments (2026-03-30)
Related Decisions:→ D12: REINDEX CONCURRENTLY vs VACUUM FULL
Related Tech Assets: → TA13: Per-Table Autovacuum Configuration SQL
Source:           stockadjustments incident, spc_inventory, 2026-03-30; PostgreSQL documentation
```

---

### K28: EF Core Compiled Query Cache and DynamicMethod Accumulation

```
Title:            EF Core Compiled Query Cache and DynamicMethod Accumulation
Category:         .NET / EF Core
Difficulty:       Intermediate
Summary:          EF Core compiles every unique LINQ expression tree into IL at runtime using
                  System.Reflection.Emit. Each unique query shape produces one DynamicMethod +
                  one DynamicILGenerator + one DynamicResolver object stored in a static
                  CompiledQueryCache. These objects are non-reclaimable by GC — they live for
                  the process lifetime. Without static precompilation, the same hot-path query
                  recompiles on every call variation, growing the cache unboundedly.
Deep Dive:        EF Core compiled query cache lifecycle:
                    1. LINQ expression tree is constructed from lambda on first call
                    2. EF Core hashes the expression tree (shape + parameter types)
                    3. If not in cache: compile to IL via Reflection.Emit (expensive)
                    4. Cache: DynamicMethod + DynamicILGenerator + DynamicResolver (all static, non-GC)
                    5. On subsequent calls with same shape: cache hit, IL invoked directly

                  Unbounded growth causes:
                    - Dynamic query construction (optional .Where chains) → unique tree per combination
                    - AsSplitQuery with 16 Include paths, not compiled statically → N entries per call

                  Static compilation with EF.CompileQuery / EF.CompileAsyncQuery:
                    - One static Func<DbContext, TParam, IEnumerable<T>> field per query shape
                    - Compiled exactly once on first call, reused forever
                    - Remaining DynamicMethod count = service-wide unique query footprint (stable ceiling)

                  Diagnosis via dotnet-dump:
                    dumpheap -stat → count System.Reflection.Emit.DynamicMethod
                    Threshold: < 500 healthy | 500–2000 investigate | > 2000 apply EF.CompileQuery
                    Stable vs unbounded: compare count across two dumps at same load — delta ≈ 0 = stable
Example:          // BEFORE: recompiles per call
                  var result = ctx.SubOrder.AsNoTracking()
                      .Include(...).AsSplitQuery()
                      .Where(x => ids.Contains(x.SourceOrderId)).ToList();

                  // AFTER: compiled once
                  private static readonly Func<AppDbContext, string[], IEnumerable<SubOrderModel>>
                      _q = EF.CompileQuery((AppDbContext ctx, string[] ids) =>
                          ctx.SubOrder.AsNoTracking()
                              .Include(...).AsSplitQuery()
                              .Where(x => ids.Contains(x.SourceOrderId)));
Trade-offs:       Pros: Non-reclaimable static heap fixed to one allocation per unique shape.
                       Eliminates per-call expression compilation overhead.
                  Cons: Query shape must be fixed at compile time — no dynamic filter additions.
                       First call still pays compilation cost (cold start).
                       AsSplitQuery in compiled queries requires EF Core 7.0+.
Decision Rule:    DynamicMethod count > 2000 AND hot-path query → apply EF.CompileQuery
                  Query has optional/conditional .Where clauses → cannot compile statically
                  EF Core version < 7 + AsSplitQuery → remove AsSplitQuery or upgrade first
Related Patterns: → P22: EF Compiled Query Cache Management
Related Decisions:→ D13: Apply EF.CompileQuery to GetSubOrderMessage Bulk Query
Related Incidents:→ I1: GetSubOrder API Latency Spike
Related Tech Assets: → TA15: EF.CompileQuery Static Field Template
Source:           Order.API-3.dmp + Order.API-11.dmp heap analysis, 2026-03-31
```

---

### K29: .NET Heap Dump Analysis — Reading dumpheap -stat

```
Title:            .NET Heap Dump Analysis — Reading dumpheap -stat
Category:         .NET Observability
Difficulty:       Intermediate
Summary:          dumpheap -stat in dotnet-dump lists all managed heap types sorted by total size
                  (ascending — largest at bottom). Each line: MethodTable | Count | TotalSize | TypeName.
                  Knowing what each type family means allows rapid diagnosis of memory problems
                  without deep GC expertise.
Deep Dive:        Type families and what they indicate:

                  System.Byte[] / System.String / System.Char[]
                    → HTTP buffers, JSON output, SQL query text, log messages.
                    → GC-reclaimable. Normal for an API service. No action unless unusually large.

                  System.Reflection.Emit.DynamicMethod / DynamicILGenerator / DynamicResolver
                    → EF Core compiled query cache. NON-RECLAIMABLE (static, lives until process exit).
                    → Count must match 1:1:1. > 2000 = too many unique query shapes being compiled.
                    → Fix: EF.CompileQuery / EF.CompileAsyncQuery static fields.

                  Microsoft.Data.SqlClient._SqlMetaData / SqlBuffer / SqlParameter
                    → Column descriptors + raw data from open SqlDataReader objects.
                    → GC-reclaimable. Proportional to concurrent request count — normal under load.
                    → If count grows between snapshots at same load → verify `await using` on ADO.NET.

                  EF entity types (SubOrderModel, OrderModel, etc.) in large quantity
                    → ChangeTracker accumulation. EF holding entity + snapshot copy.
                    → Fix: AsNoTracking() on all read-only queries.
                    → Confirmed absent = AsNoTracking() working correctly.

                  Free (large block, e.g. 32 MB)
                    → Post-GC fragmentation. Heap space reclaimed but not yet returned to OS.
                    → Reusable without growing process. Normal after load test.
                    → Free > 50% of heap → investigate LOH fragmentation.

                  AutoMapper.PropertyMap / System.Linq.Expressions.*
                    → Startup-time mapping compilation cache. Static. Expected to be large.

                  Load test vs single-request dump interpretation:
                    Single request → transient per-request objects (SqlBuffer, TaskStateMachine)
                    Load test      → all concurrent request objects visible simultaneously
                    Compare counts proportional to concurrent requests → confirms GC-reclaimable
                    Compare counts equal across load levels → confirms static/leaked
Example:          heapstat-3 vs heapstat-4 comparison (Order.API):
                    DynamicMethod: 17,557 → 7,356 at higher load = stable ceiling (fix confirmed)
                    SubOrderMessageViewModel: 836 → 50 = AsNoTracking working under concurrency
                    SqlBuffer: 8,188 → 5,442 at lower load = load-proportional, not a leak
Trade-offs:       Pros: Fast diagnosis without profiler. Works on production .dmp files.
                  Cons: Snapshot in time — misses transient allocations between GC cycles.
                       Does not show who is holding references (use gcroot <address> for that).
Decision Rule:    Always read dumpheap -stat bottom-up (largest first).
                  Take two dumps 10 min apart at same load to distinguish leak from load-proportional.
                  If DynamicMethod count grows between dumps → unbounded EF cache → apply EF.CompileQuery.
Related Knowledge:→ K28: EF Core Compiled Query Cache and DynamicMethod Accumulation
Related Patterns: → P22: EF Compiled Query Cache Management
Related Incidents:→ I1: GetSubOrder API Latency Spike
Related Tech Assets: → TA16: dotnet-dump heapstat Analysis Workflow
Source:           Order.API-3.dmp + Order.API-11.dmp, 2026-03-31
```

---

### K30: MySQL Transaction Scope Anti-Patterns in Long-Running ETL Jobs

```
Title:            MySQL Transaction Scope Anti-Patterns in Long-Running ETL Jobs
Type:             Framework Knowledge
Domain:           DB Performance / ETL
Difficulty:       Intermediate
Summary:          Wrapping a multi-batch ETL loop in a single DB transaction guarantees failure
                  at scale. MySQL enforces wall-clock timeouts (innodb_lock_wait_timeout default
                  50s, net_read_timeout default 30s) independent of query count. TX hold =
                  batch_count × batch_latency. For 3M records at 700ms/batch = 210s >> any
                  timeout. Fix: per-batch commit — each batch is its own atomic unit.
Decision Rule:    batch_count × avg_batch_latency > 10s → per-batch commit mandatory
                  batch_count × avg_batch_latency < 5s  → single TX acceptable
                  MySQL target (default timeouts)         → assume innodb_lock_wait_timeout = 50s
Related Patterns: → P24, P25
Related Incidents:→ I3, I4, I5, I6
Related Decisions:→ D16, D17
Related Tech Assets: → TA19, TA20
Source:           SyncProductMasterJda incident, 2026-04-03
```

#### MySQL Timeout Hierarchy (most likely to trigger in ETL)

| Timeout | Default | Trigger |
|---|---|---|
| `net_read_timeout` | 30s | No network read from client for 30s continuous |
| `innodb_lock_wait_timeout` | 50s | Write TX waits too long for row lock |
| `wait_timeout` | 28,800s | Idle connection timeout |

**Key insight:** These are wall-clock timers, not per-query counters. A TX open for 210s will trigger `innodb_lock_wait_timeout` at the ~50s mark regardless of how many queries ran successfully before the timeout fired.

#### Why `RollbackAsync()` itself fails

When MySQL kills a connection due to timeout, the TCP session is closed. When the `catch` block calls `tx.RollbackAsync()`, `MySqlConnector` tries to send `ROLLBACK` to a dead session — this throws a second exception. The stack trace in the error log confirms this: two entries for `MySqlTransaction` — one for the original failure, one for the failed rollback attempt. Both appear in the final exception chain.

#### Correct Pattern (per-batch commit)

```csharp
// Anti-pattern — NEVER wrap a batch loop in a single TX
await using var tx = await ctx.Database.BeginTransactionAsync(ct);  // OUTSIDE loop
while (true) {
    var batch = await ReadBatch();
    await WriteBatch(batch);   // all 300 batches open under same TX
}
await tx.CommitAsync(ct);     // unreachable for 3M records — times out at batch ~43

// Correct — per-batch commit
while (true) {
    var batch = await ReadBatch(lastId, ct);
    if (batch.Count == 0) break;
    await using var tx = await ctx.Database.BeginTransactionAsync(ct);  // INSIDE loop
    await WriteBatch(batch, ct);
    await tx.CommitAsync(ct);
    lastId = batch.Last().Id;   // advance cursor after commit
}
```

#### EF Core + MySQL Connection String Parameters for ETL

```
ConnectionTimeout=30;         -- time to establish connection
DefaultCommandTimeout=120;    -- per-statement timeout (prevent runaway queries)
ConnectionLifeTime=300;       -- max age of pooled connection (avoid stale connections)
```

Set via `UseMySql(..., o => o.CommandTimeout(120))` in `AddDbContext<T>` options registration.

---

### K32: EF Core ChangeTracker Accumulation in Per-Batch ETL Loops

```
Title:            EF Core ChangeTracker Accumulation in Per-Batch ETL Loops
Type:             Framework Knowledge
Domain:           EF Core / Memory Management
Difficulty:       Intermediate
Summary:          In a per-batch commit loop, EF Core's ChangeTracker accumulates tracked entities
                  from every batch — even after CommitAsync(). Committed entities are no longer
                  useful but remain in memory until DbContext is disposed or ChangeTracker.Clear()
                  is called. For 300 batches × 10K entities = 3M tracked objects. Combined with
                  an activity tracking Dictionary that also grows unbounded, heap grows linearly
                  with batch count — predictable OOM for any large ETL job.
Decision Rule:    After tx.CommitAsync() in a batch loop → always call context.ChangeTracker.Clear()
                  Activity tracking Dictionary passed across batches → call .Clear() after each commit
                  Heap delta > 200MB per batch → investigate ChangeTracker accumulation first
Related Patterns: → P24, P25, P28
Related Incidents:→ I3, I4, I5, I8
Related Decisions:→ D16, D20
Related Tech Assets: → TA20, TA24
Source:           SyncProductMasterJda live production incident, 2026-04-08
```

#### Why ChangeTracker Doesn't Auto-Clear After Commit

EF Core's ChangeTracker tracks entities to detect changes for the next `SaveChangesAsync()`. After `CommitAsync()`, the entities are in the database — but EF doesn't know you're done with them. It keeps tracking in case you modify and re-save them in the same DbContext scope.

In a batch loop where the DbContext lives for the entire job (not scoped per batch), this means:
- Batch 1 commit: 10K entities tracked
- Batch 2 commit: 20K entities tracked
- Batch 300 commit: 3M entities tracked — all in heap

#### The Fix

```csharp
await tx.CommitAsync(cancellationToken);

// Detach all tracked entities — they're committed, no future use in this DbContext scope
context.ChangeTracker.Clear();

// Flush activity tracking dictionary — same unbounded growth problem
activityTracking.Clear();
```

`ChangeTracker.Clear()` detaches all entities from the context (sets their state to `Detached`). GC can then reclaim the memory. Heap returns to near-baseline after each batch.

#### Heap Pattern Before vs After

```
Before ChangeTracker.Clear():        After ChangeTracker.Clear():
  Batch 1: 1,191MB (+1,175)            Batch 1: 150MB (+134)
  Batch 2: 1,780MB (+589)              Batch 2: 148MB (-2)   ← flat
  Batch 3: ~2,200MB (OOM)              Batch 3: 151MB (+3)   ← flat
```

---

### K31: ETL Batch Observability — The 4 Metrics That Predict Timeout Recurrence

```
Title:            ETL Batch Observability — The 4 Metrics That Predict Timeout Recurrence
Type:             Operational Knowledge
Domain:           Observability / ETL
Difficulty:       Beginner–Intermediate
Summary:          After fixing an ETL timeout (per-batch commit), you must instrument 4 signals
                  per batch to detect the next timeout before it happens: (1) TX hold time,
                  (2) staging read latency, (3) cumulative records counter, (4) GC allocation.
                  TX hold is the critical metric — if P95 drifts toward DB timeout threshold,
                  alert before failure. Without these metrics, the fix is a black box.
Decision Rule:    Any batch loop writing to DB → must have per-batch Stopwatch + Histogram
                  ETL job > 100K records → Prometheus metrics mandatory (not just logs)
                  Overhead budget: < 0.1% of batch duration for all instrumentation combined
Related Patterns: → P25
Related Incidents:→ I3, I4, I5
Related Decisions:→ D17
Related Tech Assets: → TA20, TA21
Source:           SyncProductMasterJda follow-up, 2026-04-08
```

#### The 4 Predictive Signals

| # | Metric | Type | Why It Predicts Failure |
|---|---|---|---|
| 1 | **Per-batch TX hold time** | Histogram | Directly maps to the variable that caused I3. If this drifts toward `innodb_lock_wait_timeout`, you have minutes to act. |
| 2 | **Staging read latency** | Histogram | Slow reads extend total batch time. Detects index degradation on staging table. |
| 3 | **Cumulative records counter** | Counter | Detects sync stalls (no progress), data volume growth (unexpected batch count). |
| 4 | **GC allocation per batch** | Summary | Catches memory pressure from large batches. EF Core tracking overhead accumulates. |

#### Metric Naming Convention for ETL

```
etl_sync_{metric_name}_{unit}
```

Labels: `sync_name`, `business_unit` — allows per-job filtering in Grafana.

Examples:
- `etl_sync_batch_duration_seconds` (Histogram)
- `etl_sync_records_processed_total` (Counter)
- `etl_sync_staging_read_seconds` (Histogram)
- `etl_sync_batch_alloc_bytes` (Summary)

#### Overhead Budget

All instrumentation must stay under **0.1% of batch duration**. For a 700ms batch:

| Instrument | Cost | % of batch |
|---|---|---|
| Stopwatch.StartNew() + Stop | ~0.001ms | 0.0001% |
| GC.GetTotalAllocatedBytes(precise: false) × 2 | ~0.01ms | 0.001% |
| Prometheus Observe/Inc × 5 | ~0.005ms | 0.0007% |
| Structured log × 1 | ~0.1ms | 0.014% |
| **Total** | **~0.12ms** | **0.017%** |

---

### K33: Copy-Paste DbSet Reference Propagation in EF Core ETL Service Clones

```
Title:            Copy-Paste DbSet Reference Propagation in EF Core ETL Service Clones
Type:             Failure Mode / Code Quality
Domain:           EF Core / ETL / Code Quality
Difficulty:       Beginner
Summary:          When an EF Core ETL sync service is cloned, the staging DbSet in
                  GetProductStaging() and the DbSet in CheckPendingAsync() are independent
                  call sites. Updating one does not update the other. Missing this causes
                  a silent wrong-table query — job runs without error but processes no data.
                  Fix: after cloning, grep for all source DbSet references and verify each
                  independently. Six touch points must all be audited (→ P26 checklist).
Decision Rule:    Cloned an EF Core ETL service? → audit every DbSet reference independently.
                  Any staging query + CheckPendingAsync → must reference same DbSet.
                  Grep for original DbSet name in cloned file — any hit = copy-paste bug.
Related Incidents:→ I6
Related Patterns: → P26
Related Decisions:→ D18
Related Tech Assets: → TA22
Source:           SyncProductBarcodeJda copy-paste incident, 2026-04-08
```

#### Concept

When an EF Core ETL sync service is cloned (e.g., `SyncProductMasterJda` → `SyncProductBarcodeJda`), the DbSet reference in the staging query method and the DbSet reference in `CheckPendingAsync` are **independent call sites**. Updating one does not update the other.

#### Failure Pattern

```csharp
// GetProductStaging — updated correctly:
var products = await stagingContext.SpcJdaBarcodeStaging   // ✓ correct
    .AsNoTracking().Where(x => x.Id > lastId)...

// CheckPendingAsync — NOT updated (copy-paste leftover):
return await stagingContext.SpcJdaProductStaging            // ✗ wrong table
    .AnyAsync(x => x.Id > lastId, cancellationToken);
```

#### Silent Failure Modes

| Scenario | Observed behavior | Actual cause |
|---|---|---|
| Product staging empty, barcode staging has rows | "No data to sync" — 0 rows processed | `CheckPendingAsync` returns false on wrong table |
| Both tables have rows | Sync appears healthy | Lucky path — pending check passes by coincidence |
| Product staging has rows, barcode staging empty | Enters loop, reads 0, exits | Wrong table returns true; correct table empty |

The third scenario is dangerous: the job appears healthy but processes nothing.

#### Detection

Grep for the original DbSet name after cloning:
```bash
grep -n "SpcJdaProductStaging" SyncProductBarcodeJda.cs
# Any hit in a Barcode file = copy-paste bug
```

#### Rule

After cloning any EF Core ETL service, audit **every DbSet reference** independently — staging query, `CheckPendingAsync`, and any other `AnyAsync`/`CountAsync`/`FirstOrDefaultAsync` call. See → P26 for full clone checklist.


### K34: Airflow DAG Local Debugging — Stub-Based Runner Pattern

```
Title:       Airflow DAG Local Debugging — Stub-Based Runner Pattern
Type:        Technique
Domain:      ETL / Airflow / Python
Stack:       Python, Apache Airflow, SQLAlchemy, pymysql
Summary:     Airflow DAG files import airflow.* at module level and call
             MySqlHook, BaseHook, Variable at runtime. Running them locally
             requires either a full Airflow installation (complex) or a
             stub layer that replaces airflow.* modules in sys.modules before
             import, substituting real DB connections for Airflow hooks.
             This enables full VS Code debugger support — breakpoints,
             variable inspection, step-through — with zero Airflow dependency.
When It Applies:
             → Debugging ETL logic in Airflow PythonOperator tasks locally
             → Reproducing production bugs without deploying to Airflow server
             → Testing DAG task functions with controlled input data
             → Debugging triggered child DAGs by mocking dag_run.conf (XCom values
               are baked into conf by TriggerDagRunOperator before child DAG receives them)
Related Incident: → I7
Related Pattern:  → P27
Related Decision: → D19
Related TA:       → TA23
```

#### Core Technique

**Step 1 — Stub airflow modules before import**
```python
# # Snippet:
import sys, types

def _stub(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

for name in ["airflow", "airflow.models.dag", "airflow.operators.python",
             "airflow.providers.mysql.hooks.mysql", "airflow.hooks.base"]:
    _stub(name)

# Attach no-op classes to DAG/Operator stubs
class _NoOp:
    def __init__(self, *a, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __rshift__(self, other): return other

sys.modules["airflow.models.dag"].DAG = _NoOp
sys.modules["airflow.operators.python"].PythonOperator = _NoOp
```

**Step 2 — Replace MySqlHook with real pymysql**
```python
# # Snippet:
import pymysql, pandas as pd
from sqlalchemy import create_engine

CONNECTIONS = {
    "spc_mysql_ds": {"host": "localhost", "port": 3306,
                     "user": "root", "password": "", "database": "spc_ds"},
}

class _RealMySqlHook:
    def __init__(self, mysql_conn_id=None):
        self._cfg = CONNECTIONS[mysql_conn_id]
    def _connect(self):
        return pymysql.connect(**self._cfg, charset="utf8mb4", autocommit=False)
    def get_first(self, sql, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
                return cur.fetchone()
    def get_pandas_df(self, sql, parameters=None):
        with self._connect() as conn:
            return pd.read_sql(sql, conn, params=parameters)
    def run(self, sql, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
            conn.commit()
    def get_sqlalchemy_engine(self):
        c = self._cfg
        url = f"mysql+pymysql://{c['user']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}?charset=utf8mb4"
        return create_engine(url, future=True)  # future=True: enables conn.commit() on SQLAlchemy 1.4.x

sys.modules["airflow.providers.mysql.hooks.mysql"].MySqlHook = _RealMySqlHook
```

**Step 3 — Mock TaskInstance (parent DAG) or dag_run.conf (child DAG)**
```python
# # Snippet:
# For PythonOperator tasks (parent DAG) — mock ti.xcom_push
class _MockTaskInstance:
    def xcom_push(self, key, value):
        print(f"  [XCom] {key!r} = {value!r}")

# For triggered child DAGs — mock dag_run.conf
# (TriggerDagRunOperator resolves XCom and bakes values into conf)
class _MockDagRun:
    def __init__(self, conf):
        self.conf = conf

MOCK_CONF = {
    "dih_batch_id": "spcmock26042001",
    "total_outbound_order_success": "10",
    "owner_id": "CDS-CDS",
}
```

#### Windows Environment Rules

| Issue | Wrong fix | Correct fix |
|---|---|---|
| Thai locale (cp874) crashes debugpy | `PYTHONUTF8=1` | `PYTHONIOENCODING=utf-8` in launch.json |
| Why PYTHONUTF8 wrong | Breaks venv path handling in importlib._bootstrap_external._path_join | PYTHONIOENCODING only affects stdin/stdout/stderr |

#### SQLAlchemy Version Compatibility

```
flask-appbuilder 4.6.3 pins SQLAlchemy<1.5 → cannot upgrade to 2.x
Production Airflow 3.x runs SQLAlchemy 2.x → conn.commit() works there

Local debug fix: create_engine(url, future=True)
→ SQLAlchemy 1.4 "future" mode exposes Connection.commit() / Connection.rollback()
→ No version conflict, no production code change needed
```

---

### K35: Two-Pass EF Core Batch Pattern for FK-Dependent Inserts

```
Title:            Two-Pass EF Core Batch Pattern for FK-Dependent Inserts
Type:             Framework Knowledge
Domain:           EF Core / Data Access
Difficulty:       Intermediate
Summary:          When child entities need a DB-generated parent ID (IDENTITY/SEQUENCE) as a foreign
                  key, you cannot batch both parent and child inserts into a single SaveChangesAsync.
                  EF Core only populates entity.Id after the DB returns the generated identity value
                  from INSERT. Two-pass approach: save parents first (Pass 1) to get real Ids, then
                  batch all children using those Ids (Pass 2). Total: 2 SaveChangesAsync per batch
                  regardless of batch_size — replaces N saves (one per header).
Deep Dive:        Pass 1: foreach headers → context.Add(headerActivity) + context.Add(order)
                           → await context.SaveChangesAsync()  ← headerActivity.Id now real DB value
                  Pass 2: foreach headers → CollectOrderActivities(... headerActivity ...)
                           → context.AddRange(allItemActivities)
                           → context.AddRange / update / delete item masters
                           → await context.SaveChangesAsync()  ← all items in one batch
                  Boundary: if parent PK is application-assigned Guid, skip two-pass — use single-pass.
Related Patterns: → P28: Two-Pass Batch Commit
Related Incidents:→ I8: OrderJda ETL — N+1 SELECT + SaveChanges-in-Loop
Related Tech Assets: → TA24: OrderJda Two-Pass Per-Batch Commit Template
```

#### Why You Cannot Do It in One Pass

EF Core populates `entity.Id` from the DB-generated identity value only AFTER `SaveChangesAsync` commits the INSERT and the DB returns the identity. If you add both parent and child to the change tracker before saving, EF Core will attempt to SET FOREIGN KEY for child rows using `0` (default int) — causing a constraint violation or silent data corruption.

#### The Two-Pass Invariant

```
Pass 1: foreach headers → context.Add(headerActivity) + context.Add(order)
        → await context.SaveChangesAsync()   ← headerActivity.Id is now a real DB value
Pass 2: foreach headers → CollectOrderActivities(... headerActivity ...)
        → context.AddRange(allItemActivities)
        → context.AddRange / update / delete item masters
        → await context.SaveChangesAsync()   ← all items saved in one batch
```

Total: **2 SaveChangesAsync per batch** regardless of batch_size. This replaces `N` saves (one per header) = 2 vs N×batch_size writes.

#### When NOT to Use Two-Pass

- Children do NOT reference a DB-generated parent ID (e.g., GUID keys set by application) → single-pass is fine
- Parent IDs are application-assigned before insert → single-pass with `Add(parent)` + `Add(child)` works
- EF Core shadow properties or owned entities handle FK → EF resolves automatically in single pass

#### Boundary Condition

If `headerActivity.Id` is a Guid set by the application (`Guid.NewGuid()`), EF Core does NOT need a DB round-trip. Use single-pass and add everything before the single `SaveChangesAsync`.

---

### K36: Python sys.path and Nested Package Module Resolution

```
Title:         Python sys.path and Nested Package Module Resolution
Type:          Language Mechanics
Domain:        Python / Airflow DAG Authoring
Difficulty:    Beginner
Summary:       Python resolves `import` statements by searching directories listed in sys.path
               in order. When a DAG file lives inside a sub-package, its parent is not
               automatically on sys.path, so cross-package imports fail unless the correct
               ancestor is inserted.
Deep Dive:
  sys.path is a list of directory strings Python searches left-to-right for module names.
  `sys.path.insert(0, path)` prepends path so it is checked before everything else.

  The idiom:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
  decodes as:
    __file__                          → absolute path to current .py file
    os.path.abspath(__file__)         → resolve symlinks / relative refs
    os.path.dirname(...)  (1st call)  → parent directory (the DAG's own folder)
    os.path.dirname(...)  (2nd call)  → grandparent directory (the package root)
    sys.path.insert(0, grandparent)   → make grandparent the priority import root

  Example layout:
    /airflow/dags/                           ← grandparent inserted into sys.path
        common/
            team_notification_operator.py    ← resolved as dags.common.team_notification_operator
        spc_order_inbound/
            dags.py                          ← __file__

  Without the insert: Python searches only spc_order_inbound/ → dags.common not found →
    ModuleNotFoundError: No module named 'dags'

When to Apply:
  - DAG file is nested two or more levels below the Airflow dags root.
  - Cross-package import from a sibling sub-package (e.g. dags.common.*).
  - No pip-installed shared package available.

Better Alternatives (in priority order):
  1. Install common/ as a pip package in the Airflow worker venv.
  2. Set AIRFLOW__CORE__DAGS_FOLDER or PYTHONPATH env var to the parent.
  3. Use sys.path.insert as a last resort — fragile if the file moves.

Related Incident:    → I9: Airflow DAG — Dead subprocess.TimeoutExpired Branch
Related TA:          → TA25: Airflow PythonOperator — Thread-Based Subprocess with Hard Timeout
```

