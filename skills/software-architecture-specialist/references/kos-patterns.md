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

**Problem**: API endpoints receive burst traffic that exhausts downstream resources (DB connections, third-party API quotas) or monopolises the system for other users.

**Solution**: Assign each client (user ID, API key, or resource key) a bucket of capacity C tokens refilled at rate R per second. Each request consumes 1 token. Reject with HTTP 429 if empty.

**When to USE**:
- Any public or partner-facing API
- Endpoints that call expensive downstream services (DB, external APIs)
- When burst traffic is legitimate (allow it up to capacity, then throttle)

**When NOT to USE**:
- Need constant-rate output regardless of input (use Leaking Bucket instead)
- Rate limit is per-second-exact with no tolerance for burst

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Burst-tolerant — allows spikes up to capacity | Tuning capacity + refill rate requires experimentation |
| Atomic via Redis Lua script | Distributed state needed for multi-instance deployments |
| HTTP 429 + Retry-After header is standard | Key expiry strategy needed to avoid stale buckets |

**Your Stack (Redis + .NET or Go)**:
```lua
-- Redis Lua script (atomic token bucket check)
local tokens = tonumber(redis.call('GET', KEYS[1])) or tonumber(ARGV[1])
if tokens >= 1 then
    redis.call('SET', KEYS[1], tokens - 1, 'EX', ARGV[2])
    return 1  -- allowed
else
    return 0  -- rejected (HTTP 429)
end
-- Background: replenish via scheduled refill or lazy calculation on each request
```

**Rate limit key selection**:
- Per user/API key → most common, fair per-client
- Per resource (e.g., per SourceOrderId) → when one resource being hammered is the bottleneck
- Per IP → edge servers before auth

**Decision Rule**:
- General API, burst acceptable? → Token Bucket
- Strict constant rate? → Leaking Bucket
- Simple per-minute count? → Fixed Window Counter
- Need < 0.01% error at scale? → Sliding Window Counter

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

**Problem**: Adding or removing nodes in a distributed cache or data store remaps most keys with traditional mod-N hashing, causing a cache stampede or massive data rebalancing.

**Solution**: Map both server IDs and keys onto a hash ring (0–2^32). Assign 100–200 virtual nodes per physical server. For each key, walk clockwise to find the owning server. On topology change, only adjacent keys on the ring are remapped (k/n total vs ~all keys with mod-N).

**When to USE**:
- Distributed cache with dynamic node count (autoscaling, failures)
- Data partitioning where servers join/leave regularly
- Load balancing across stateful servers requiring key affinity

**When NOT to USE**:
- Fixed, static server count (mod-N is simpler)
- When you need exact control over which key goes where

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Minimal key remapping on topology change | More complex than mod-N |
| Even distribution with virtual nodes | Storage overhead for ring mapping |
| Battle-tested (DynamoDB, Cassandra, Discord, Akamai) | SHA computation per lookup |

**Your Stack (Go)**:
```go
type Ring struct {
    nodes   []int            // sorted hash positions
    nodeMap map[int]string
    vnodes  int              // virtual nodes per server (100–200)
}

func (r *Ring) GetNode(key string) string {
    hash := hashKey(key)
    idx := sort.SearchInts(r.nodes, hash) % len(r.nodes)
    return r.nodeMap[r.nodes[idx]]
}
```

**Decision Rule**:
- Static server count → mod-N hashing
- Dynamic server count (autoscale) → Consistent hashing
- Need even distribution → virtual nodes (100–200 per server)

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

**Problem**: Followers need to see a new post in their feed with minimal read latency, but building the feed at read time is too slow.

**Solution**: On post creation, immediately write the post ID to all followers' feed caches. Feed reads are O(1) — just fetch from pre-computed Redis list per user.

**When to USE**:
- Users have bounded follower counts (< ~10,000)
- Feed read frequency >> write frequency
- Majority of followers are active (cache writes are not wasted)

**When NOT to USE**:
- Celebrity users with millions of followers (write amplification: 1 post → millions of cache writes)
- Most followers are inactive (wasted writes to rarely-read caches)

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| O(1) feed reads — instant | Write amplification for high-follower users |
| Pre-computed = no fan-out at read time | Memory: N copies of every post ID |
| Predictable read latency | Stale cache risk if invalidation lags |

**Decision Rule**:
- Regular users (< 10K followers)? → Fanout on Write
- Celebrity users (> 1M followers)? → Fanout on Read (P4)
- Mixed platform? → Hybrid Fanout (P5)

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

**Problem**: Pre-computing feeds for all followers wastes resources — especially for high-follower celebrities where 1 post triggers millions of cache writes.

**Solution**: Post is written only to the author's post store. When a user requests their feed, the system fetches recent posts from all followed users, merges, and sorts them. Optionally cache the merged result per user with a short TTL.

**When to USE**:
- Author has very high follower counts (celebrities)
- Low active-user ratio (most users don't read regularly)
- Feed freshness is critical — cannot tolerate staleness

**When NOT to USE**:
- Users follow many highly active users (fan-in too large at read time)
- Low latency is required on every feed read

**Complexity**: Low (write) / High (read merge)

**Trade-offs**:
| Pros | Cons |
|------|------|
| No write amplification | Slow reads — N fetches per feed request |
| Always fresh — reads latest data | Complex merge + sort at read time |
| Works for any follower count | Cannot be pre-warmed for inactive users |

**Decision Rule**:
- Author has > 1M followers? → Fanout on Read
- Read latency must be < 100ms? → Fanout on Write or Hybrid

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

**Problem**: Pure push wastes compute for celebrities; pure pull makes reads slow for regular users. Neither alone works for a platform with both.

**Solution**: Classify users by follower count. Below threshold: fanout on write (push). Above threshold (celebrities): fanout on read (pull). At feed assembly time, merge the pre-computed feed (regular users' posts) with freshly-fetched celebrity posts.

**When to USE**:
- Social platform with power-law follower distribution (a few users have millions, most have hundreds)
- Both fast read AND efficient write are required

**When NOT to USE**:
- Uniform follower distribution (either pure push or pure pull is simpler)
- Celebrity threshold is hard to define (start with > 10,000 followers)

**Complexity**: High (dual path + threshold classification + merge logic)

**Trade-offs**:
| Pros | Cons |
|------|------|
| Optimal for both read speed and write cost | Higher system complexity |
| Scales to any user size | Threshold tuning required |
| Instagram / Twitter production approach | Feed merge at read time adds latency |

**Decision Rule**:
```
follower_count < 10,000   → fanout on write (push)
follower_count > 10,000   → fanout on read (pull)
Feed assembly:             → pre-computed cache + freshly-fetched celebrity posts
Threshold:                 → tune per system; start at 10K, adjust based on write cost
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

**Problem**: Traditional CRUD loses history. You cannot audit what happened, replay to recover from bugs, or derive different read models from the same source data.

**Solution**: Instead of storing current state, store an immutable append-only log of every state-change event. Current state = replay of all events (or snapshot + replay of events since snapshot). Build read projections from the event stream.

**When to USE**:
- Financial systems requiring full audit trail
- Systems needing temporal queries ("what was the state at time T?")
- Systems where a bug fix requires reprocessing historical data
- Systems needing multiple read models from the same source (CQRS)

**When NOT to USE**:
- Simple CRUD with no audit/replay requirement (adds complexity for no gain)
- Real-time systems where event schema evolution is too complex to maintain
- Small systems where snapshot + versioned DB is sufficient

**Complexity**: High

**Trade-offs**:
| Pros | Cons |
|------|------|
| Full audit trail — know exactly what happened and when | Event schema evolution is complex |
| Temporal queries — state at any point in time | Query complexity — need projections for reads |
| Replay — re-derive state after fixing a bug | Storage grows unboundedly (compaction needed) |
| Multiple projections from same events | Eventual consistency for read models |

**Your Stack (PostgreSQL)**:
```sql
-- Event store table (append-only, never UPDATE or DELETE)
CREATE TABLE domain_events (
    id             BIGSERIAL PRIMARY KEY,
    aggregate_id   UUID NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    payload        JSONB NOT NULL,
    sequence_num   BIGINT NOT NULL,
    created_at     TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX ON domain_events(aggregate_id, sequence_num);

-- Snapshot table (periodic materialization to avoid full replay)
CREATE TABLE snapshots (
    aggregate_id   UUID PRIMARY KEY,
    state          JSONB NOT NULL,
    at_sequence    BIGINT NOT NULL,
    created_at     TIMESTAMP DEFAULT NOW()
);
-- Recovery: load snapshot WHERE aggregate_id=X, then replay events WHERE sequence_num > at_sequence
```

**Decision Rule**:
- Financial system with audit requirements? → Event sourcing mandatory
- Need temporal queries? → Event sourcing
- Simple CRUD, no audit, no replay? → Traditional DB state storage
- Gaming score, simple counter? → Regular DB update (event sourcing is overkill)

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

**Problem**: A query cannot be served from a single node — data is partitioned across multiple shards and must be aggregated to answer.

**Solution**: 1. Coordinator receives the query. 2. **Scatter**: broadcast sub-queries to all relevant shards in parallel. 3. **Gather**: collect responses, merge/sort/reduce. 4. Return merged result.

**When to USE**:
- Top-K queries across sharded data (leaderboard, trending)
- Search across multiple index shards
- Aggregations (SUM, MAX) where data is partitioned by key

**When NOT to USE**:
- Query can be routed to a single shard using the shard key (direct routing is always better)
- Fan-out is too wide (N shards = latency bounded by slowest shard)

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Enables arbitrary queries across all shards | Latency = max(shard_latency) not avg |
| No data movement required | All shards must respond; one slow shard delays all |
| Works with consistent hashing for shard selection | Merge logic needed at coordinator |

**Decision Rule**:
```
Query includes shard key → direct shard routing (no scatter needed)
Query is global (top-K, search, aggregation) → Scatter-Gather
Shard count > 50 → add shard sampling (don't scatter to all — too slow)
```

**Real example**: Gaming leaderboard — top 100 globally requires querying all N Redis shards and merging sorted results.

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

**Problem**: In-memory state is lost on crash. Rebuilding state from scratch after every restart is too slow (full replay of all history).

**Solution**: Before modifying in-memory state, append the change to a sequential log on durable storage. On crash recovery, load the latest snapshot and replay only the WAL entries since the snapshot.

**When to USE**:
- Any system with in-memory state that must survive crashes
- Databases (PostgreSQL, MySQL), message queues (Kafka segment files), matching engines
- Financial systems requiring deterministic crash recovery

**When NOT to USE**:
- Stateless systems (nothing to restore)
- Systems where WAL replay would take too long without snapshots (add periodic snapshots)

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Crash recovery without losing in-flight work | WAL file grows unboundedly without truncation |
| Sequential writes = fast (no random I/O) | Recovery time bounded by WAL size since last snapshot |
| Deterministic — same WAL = same state | Adds write latency (must persist to WAL before ack) |

**Your Stack (Go + file-based)**:
```go
// Write entry to WAL before applying to in-memory state
func (w *WAL) Append(entry []byte) error {
    _, err := w.file.Write(entry)       // sequential append — fast
    if err != nil { return err }
    return w.file.Sync()                // fsync — guarantee durability before ack
}

// Recovery: load snapshot, then replay WAL entries since snapshot sequence
func Recover(snapshotPath, walPath string) State {
    state := loadSnapshot(snapshotPath)
    entries := readWALSince(walPath, state.LastSequence)
    for _, e := range entries {
        state = state.Apply(e)
    }
    return state
}
```

**Decision Rule**:
- In-memory state + crash recovery required? → WAL mandatory
- Event log that doubles as WAL? → Event Sourcing (P6) subsumes WAL
- Kafka segment files? → Kafka uses WAL internally (you don't implement it)

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

**Problem**: Nearby location search over millions of businesses requires spatial indexing — scanning all records by lat/lon is O(n) and impractical.

**Solution**: Encode each business location as a geohash string (e.g., "9q9p1y"). Index this string column. For a user at location L, compute the geohash at precision P, compute the 8 neighboring cells, query `WHERE geohash IN (9 cells)`, then filter by exact distance.

**When to USE**:
- Nearby search (restaurants, drivers, points of interest)
- Static or semi-static locations updated infrequently
- Scale up to hundreds of millions of records

**When NOT to USE**:
- Constantly moving entities at high frequency (>1 update/second per entity) — use Quadtree or H3
- Arbitrary polygon regions — use Google S2
- Precision requirements finer than ~100m — use higher precision but be aware of 8-neighbor requirement

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| O(log n) lookup using standard string index | Boundary problem: nearby points may have different prefixes |
| Works on any relational DB | Must always check 8 neighbors, not just center cell |
| Simple to implement and understand | Fixed precision per level (quadtree is density-adaptive) |

**Your Stack (PostgreSQL)**:
```sql
-- Store and index geohash
ALTER TABLE businesses ADD COLUMN geohash_6 CHAR(6);
CREATE INDEX idx_biz_geohash ON businesses(geohash_6);

-- Nearby query (9 cells: center + 8 neighbors computed in application)
SELECT id, name,
    6371 * acos(cos(radians(:lat)) * cos(radians(lat))
        * cos(radians(lon) - radians(:lon))
        + sin(radians(:lat)) * sin(radians(lat))) AS distance_km
FROM businesses
WHERE geohash_6 = ANY(:nine_cells) AND is_active = true
HAVING distance_km < :radius_km
ORDER BY distance_km LIMIT 20;
```

**Decision Rule**:
```
Nearby search, simple range, static locations?       → Geohash level 6
Density-aware indexing, frequent updates?             → Quadtree
Arbitrary polygon, global scale mapping?              → Google S2
Precision < 100m?                                     → Geohash level 7-8 + 8 neighbors
Insufficient results at precision 6?                  → Expand to precision 5 and retry
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
BotE Impact:      4,096 IDs/ms per machine — sufficient for all but the highest-throughput systems
                  64-bit BIGINT: half the storage of UUID (128-bit), faster JOIN/index
                  Time-sortable: enables WHERE id > X range queries with no extra timestamp column
                  Critical dependency: NTP sync. Clock drift → wait loop prevents duplicate IDs.
Decision Rule:    Distributed + time-sortable + 64-bit?       → Snowflake
                  Non-guessable, random?                       → UUID v4
                  Strictly sequential, single server?          → DB auto-increment
                  Clock unreliable across nodes?               → ULID (monotonic, NTP-independent)
Based on Knowledge:  → Distributed Unique ID Generation (K5)
Related Patterns:    → P15: Idempotency Key (Snowflake IDs pair well as idempotency keys — globally unique + time-ordered)
```

**Problem**: Multiple distributed services need globally unique, time-sortable IDs without coordination, without a central DB sequence, and without the 128-bit bulk of UUID.

**Solution**: Compose a 64-bit integer from timestamp (41 bits, ms precision), datacenter ID (5 bits), machine ID (5 bits), and per-ms sequence counter (12 bits). No coordination needed — each machine generates IDs independently.

**When to USE**:
- High-throughput ID generation across distributed services
- Need time-sortable IDs (enables range queries: find all orders after ID X)
- Want to avoid DB auto-increment bottleneck or UUID size overhead

**When NOT to USE**:
- Need strictly sequential IDs with no gaps (use DB sequence)
- Machine count exceeds 1,024 (expand machine bits)
- Clock synchronization is unreliable (consider ULID instead)

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| 64-bit — fits in a BIGINT column | Requires NTP clock synchronization |
| Time-sortable — enables range queries | Not strictly monotonic across machines |
| No coordination needed — zero network hop | ~69-year range before overflow |
| 4,096 IDs/ms per machine | Machine ID assignment must be managed |

**Your Stack (Go)**:
```go
func (s *Snowflake) NextID() int64 {
    s.mu.Lock(); defer s.mu.Unlock()
    now := time.Now().UnixMilli()
    if now == s.lastMs {
        s.seq = (s.seq + 1) & 0xFFF
        if s.seq == 0 { for now <= s.lastMs { now = time.Now().UnixMilli() } }
    } else {
        s.seq = 0
    }
    s.lastMs = now
    // [41-bit ts][5-bit dc][5-bit machine][12-bit seq]
    return (now-s.epoch)<<22 | s.dcID<<17 | s.machineID<<12 | s.seq
}
```

**Decision Rule**:
```
Distributed, time-sortable, 64-bit?        → Snowflake
Non-guessable, random?                     → UUID v4
Strictly sequential, single server?        → DB auto-increment
Clock unreliable across nodes?             → ULID (monotonic, NTP-independent)
```

**KOS Summary**:
- 64-bit integer: [41-bit timestamp ms][5-bit datacenter][5-bit machine][12-bit sequence]
- Max 4,096 IDs/ms per machine — sufficient for all but the highest-throughput systems
- Epoch: custom start date (not Unix epoch) to maximize usable 69-year range
- Time-sortability enables `WHERE id > X` range queries without timestamp column
- Critical dependency: NTP sync. Clock drift → duplicate IDs → use sequence overflow guard + wait loop
- Store as `BIGINT` in PostgreSQL — no UUID column, no JOIN overhead from 128-bit keys

**Related patterns**: P15 Idempotency Key (Snowflake IDs pair well as idempotency keys — globally unique + time-ordered)

---

### P11: Hosted Payment Page

```
Name:             Hosted Payment Page
Category:         API Design
Problem:          Processing raw credit card data requires PCI-DSS Level 1 compliance
                  (expensive, complex, high audit burden).
Solution:         1. Server creates a payment session via PSP API
                  2. Redirect user to PSP's hosted payment page (HTTPS on PSP domain)
                  3. PSP collects and tokenizes card data directly
                  4. PSP redirects back with payment token to your success/failure URL
                  5. Your system calls PSP API with token to confirm/capture charge
                  6. Store idempotency_key + result in your ledger
                  Your system never touches raw card data — PCI scope eliminated
When to Use:      Any system processing credit card payments
                  Team lacks security expertise for PCI-DSS compliance
                  Speed to market is important
When NOT to Use:  Need fully custom payment UI (use PSP's JavaScript SDK instead)
                  Enterprise with existing PCI-DSS compliance (direct API may be better)
Complexity:       Low
Decision Rule:    New team building payments?                 → Hosted Payment Page first, always
                  Need custom UI + avoid PCI?                 → PSP JavaScript SDK
                  Already PCI-compliant + need control?       → Direct PSP API with own form
Key Rules:        Always store idempotency_key before redirecting — prevents double-charge on retry
                  Verify PSP webhook signature before updating order status
                  On redirect failure: show "payment pending", never "failed" — PSP may have charged
                  Never log or persist raw card fields — only store the token
Based on Knowledge:  → Idempotency in Distributed Systems (K20)
                     → Double-Entry Ledger System (K23)
Related Patterns:    → P15: Idempotency Key (token capture must be idempotent)
                     → P12: DLQ with Reconciliation (PSP settlement reconciliation)
```

**Problem**: Processing raw credit card data requires PCI-DSS Level 1 compliance — a costly, time-consuming, and high-risk audit burden for most teams.

**Solution**: Redirect the user to the PSP's (Stripe, PayPal, Braintree) hosted payment form. The PSP collects card data directly and returns a payment token to your system. Your system only handles the token — never touches raw card data.

**When to USE**:
- Any system processing card payments
- Team lacks dedicated security/compliance expertise for PCI-DSS
- Speed to market matters more than fully custom payment UI

**When NOT to USE**:
- Need fully custom, branded payment experience (use PSP's JavaScript SDK instead — still PCI-scope-reduced)
- Enterprise with existing PCI-DSS L1 infrastructure (direct API may be more efficient)

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Eliminates PCI-DSS scope entirely | Redirect interrupts UX flow |
| PSP handles fraud detection, 3D Secure | Less control over payment page design |
| PSP absorbs card data breach risk | PSP downtime = your payment downtime |
| Faster to implement than custom card form | PSP per-transaction fees |

**Implementation flow**:
```
1. Your server creates a payment session via PSP API
2. User redirected to PSP hosted page (HTTPS on PSP's domain)
3. PSP collects and tokenizes card data
4. PSP redirects back to your success/failure URL with payment token
5. Your server calls PSP API with token to confirm/capture charge
6. Store idempotency_key + result in your ledger
```

**Decision Rule**:
- New team building payments? → Hosted Payment Page first, always
- Need custom UI + still avoid PCI? → PSP JavaScript SDK (card data goes PSP, not your server)
- Already PCI-compliant and need control? → Direct PSP API with your own form

**KOS Summary**:
- PCI-DSS scope reduction: your server never touches raw card data — only handles the token returned by PSP
- Flow: create session → redirect user to PSP page → PSP tokenizes → redirect back with token → capture charge
- Always store `idempotency_key` + result before redirecting — prevents double-charge on network retry
- Webhook verification mandatory: validate PSP webhook signature before updating order status
- Failure mode: PSP redirect failure → show user "payment pending" state, never "failed" — PSP may have charged
- Azure AD B2C stack: PSP token stored against user profile; never log or persist raw card fields

**Related patterns**: P15 Idempotency Key (mandatory — token capture must be idempotent)

---

### P12: Dead Letter Queue (DLQ) with Reconciliation

```
Name:             Dead Letter Queue (DLQ) with Reconciliation
Category:         Resilience
Problem:          Some messages permanently fail processing (bad data, downstream unavailable).
                  Without DLQ, the consumer blocks or loses data; without reconciliation,
                  financial discrepancies go undetected.
Solution:         1. Classify errors: permanent (skip retries) vs transient (retry)
                  2. Consumer retries with exponential backoff: 3 attempts, 1s / 4s / 16s
                  3. After max retries or permanent error: route to DLQ topic
                  4. Alert: DLQ depth > 0 for 5 min → page on-call (DLQ must always be empty)
                  5. Fix root cause first, then replay — replaying a broken consumer doubles damage
                  6. For financial: end-of-day reconciliation vs PSP settlement file per currency
                     Any unmatched transaction → create investigation record + escalate
When to Use:      Any Kafka consumer processing financial or critical events
                  Any system where missed messages need audit trail
When NOT to Use:  Non-critical events where loss is acceptable (discard instead of DLQ)
                  Events with TTL that are useless once stale (drop, not DLQ)
Complexity:       Low–Medium
Decision Rule:    Financial Kafka consumer?                 → DLQ + reconciliation mandatory
                  Critical business events (order, inventory)? → DLQ mandatory
                  Analytics/logs?                           → DLQ optional (consider dropping)
Key Rules:        DLQ topic: {original_topic}.DLQ
                  Alert threshold: depth > 0 for 5 min → page on-call
                  Replay must be idempotent — same message processed twice = same result
                  Go stack: use isPermanentError() to skip retries on 400-class errors
Based on Knowledge:  → Message Queue Internals (K18)
                     → Idempotency in Distributed Systems (K20)
Related Patterns:    → P15: Idempotency Key (replay safety)
                     → P11: Hosted Payment Page (PSP reconciliation)
Source:           Financial consumer pattern, Go + Kafka stack
```

**Problem**: Some Kafka messages permanently fail processing (bad payload, downstream permanently unavailable). Without a DLQ they block the partition or cause silent data loss. For financial systems, missed events cause balance discrepancies that are never detected.

**Solution**: After max retries with exponential backoff, route failed messages to a Dead Letter Queue topic. Alert on DLQ depth > 0. For financial systems: add end-of-day reconciliation — compare internal ledger totals against PSP/partner settlement files and alert on any discrepancy.

**When to USE**:
- Any Kafka consumer processing financial or critical events
- Any system where missed messages need an audit trail
- Any system with at-least-once delivery and downstream side effects

**When NOT to USE**:
- Non-critical events where silent loss is acceptable (discard instead of DLQ)
- Events with TTL that are useless once stale (drop, not DLQ)

**Complexity**: Low–Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| No silent data loss — every failure is auditable | DLQ requires monitoring + operational runbook |
| Allows manual inspection + replay after fix | Replay must be idempotent (consumer must handle duplicates) |
| Reconciliation catches discrepancies that DLQ misses | Reconciliation job adds operational complexity |

**Your Stack (Go + Kafka)**:
```go
const maxRetries = 3

func processWithDLQ(msg kafka.Message) {
    var lastErr error
    for attempt := 0; attempt <= maxRetries; attempt++ {
        if err := processMessage(msg); err == nil { return }
        else { lastErr = err }

        if isPermanentError(lastErr) { break }           // don't retry permanent errors
        time.Sleep(backoff(attempt))                     // exponential: 1s, 4s, 16s
    }
    // Route to DLQ after maxRetries or permanent error
    publishToDLQ(msg, lastErr)
}

// DLQ topic: original_topic.DLQ
// Alert: if dlq_depth > 0 for 5 minutes → page on-call
```

**End-of-day reconciliation (financial)**:
```
1. Fetch internal ledger totals for the day
2. Download PSP settlement file (CSV/SFTP)
3. Match: internal_total == psp_total for each currency
4. Any unmatched transaction → create investigation record
5. Alert: if unmatched_count > 0 → escalate immediately
```

**Decision Rule**:
- Financial Kafka consumer? → DLQ + reconciliation mandatory
- Critical business events (order, inventory)? → DLQ mandatory
- Analytics/logs? → DLQ optional (consider dropping instead)

**KOS Summary**:
- DLQ topic naming convention: `{original_topic}.DLQ` — keeps consumer group and alert routing simple
- Max retries: 3 with exponential backoff (1s, 4s, 16s). Permanent errors skip retries immediately
- Alert threshold: DLQ depth > 0 for 5 min → page on-call. DLQ should always be empty in healthy state
- Replay rule: fix the consumer code first, then replay — replaying broken consumer doubles the damage
- Replay must be idempotent: same message processed twice must produce same result (use idempotency key)
- Reconciliation cadence: end-of-day (financial). Compare internal ledger vs PSP settlement file by currency
- Unmatched transactions → create investigation record + escalate immediately (never silently ignore)
- Go stack: use `isPermanentError()` to classify errors before retry loop — avoid retrying 400-class errors

**Related patterns**: P15 Idempotency Key (replay safety), P11 Hosted Payment Page (PSP reconciliation)

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

**Problem**: A business operation spans multiple services (e.g., place order → reserve inventory → charge payment). If one step fails, you need to undo the previous steps — but there's no distributed transaction.

**Solution**: Each service does its local transaction and publishes an event. The next service listens and acts. On failure, compensating transactions are triggered in reverse.

**Types**:
- **Choreography**: Services react to each other's events (decentralized)
- **Orchestration**: A saga orchestrator directs each step (centralized)

**When to USE**:
- Multi-service transaction with rollback requirements
- Long-running business processes
- You can define compensating actions for each step

**When NOT to USE**:
- Single-service operations (just use a DB transaction)
- When steps can't be compensated (irreversible actions)
- Simple workflows with no failure recovery need

**Complexity**: High

**Trade-offs**:
| Pros | Cons |
|------|------|
| No distributed lock needed | Complex to design and debug |
| Each service stays autonomous | Eventual consistency — intermediate states exist |
| Resilient to partial failures | Compensating transactions can fail too |

**Decision Rule**:
- Single service? → DB transaction
- 2-3 services, simple flow? → Choreography Saga
- Complex flow with many steps? → Orchestration Saga

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

**Problem**: Writing to DB and publishing a Kafka event are two separate operations. If the service crashes between them, one side is missing — data inconsistency.

**Solution**: Write the event to an `outbox` table in the same DB transaction as the domain change. A separate background worker polls the outbox and publishes to Kafka, then marks as sent.

**When to USE**:
- You need guaranteed at-least-once event delivery
- DB write and event publish must be atomic
- Cross-service communication where consistency matters

**When NOT to USE**:
- Fire-and-forget notifications (email, push) where loss is acceptable
- When you already have a transactional messaging system
- Low-volume systems where 2PC overhead is acceptable

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Guaranteed delivery (at-least-once) | Adds outbox table + polling worker |
| Simple to reason about | Slight delay between write and publish |
| No distributed transaction needed | Consumer must handle duplicates (idempotency) |

**Your Stack (PostgreSQL + Kafka)**:
```sql
-- outbox table
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    event_type VARCHAR(100),
    payload JSONB,
    created_at TIMESTAMP,
    published_at TIMESTAMP NULL
);
```
```csharp
// In same transaction:
_context.Orders.Add(order);
_context.OutboxEvents.Add(new OutboxEvent {
    EventType = "OrderCreated",
    Payload = JsonSerializer.Serialize(orderEvent)
});
await _context.SaveChangesAsync();
// Background worker picks up unpublished rows and sends to Kafka
```

**Decision Rule**:
- Need atomic DB + event? → Outbox
- Can tolerate occasional loss? → Direct publish
- Need exactly-once? → Outbox + idempotency key on consumer

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

**Problem**: Retries (HTTP or event-driven) can cause the same operation to execute twice — double charges, duplicate orders, double inventory deductions.

**Solution**: Assign a unique key to each operation. Before processing, check if the key was already processed. If yes, return the cached result without re-executing.

**When to USE**:
- Any operation that must be retried (payment, order creation)
- Kafka consumers (at-least-once delivery = duplicates possible)
- HTTP endpoints called by unreliable clients

**When NOT to USE**:
- Pure reads (idempotent by nature)
- Operations where duplicates are harmless

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Safe retries without side effects | Storage overhead for processed keys |
| Enables at-least-once + deduplication | Key expiry policy needed |
| Simple to implement | Doesn't solve ordering issues |

**Your Stack (PostgreSQL)**:
```sql
CREATE TABLE idempotency_keys (
    key VARCHAR(255) PRIMARY KEY,
    result JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
-- TTL via scheduled cleanup or pg_partman
```

**Decision Rule**:
- Mutating operation + retry possible? → Always add idempotency key
- Outbox pattern used? → Consumer needs idempotency key

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
                  3. Declare ALL factory contexts at coordinator scope — before any if/for/while block
                  4. Create one DbContext per task from IDbContextFactory
                  5. Fire all tasks via Task.WhenAll
                  6. Await results and assemble in memory — zero DB calls in assembly
                  7. Expose sync wrapper; migrate callers incrementally
When to Use:      Coordinator calls 2+ independent DB operations sequentially
                  I/O wait % > 80% on hot path
                  Sequential latency > 300ms
When NOT to Use:  Calls have data dependencies (use sequential await instead)
                  Only 1 DB call — parallelism overhead not worth it
                  < 10 req/s low concurrency — sequential async sufficient
Complexity:       Medium
BotE Impact:      Sequential: latency = t1 + t2 + t3 + t4
                  Example: 400+300+250+200 = 1,150ms
                  Parallel:  latency = max(t1, t2, t3, t4) = 400ms  (-65%)
                  Pool pressure unchanged — same total queries, shorter hold time per request
Measured Impact:  GetSubOrder "All" N≈10: P50 1,242ms → 1,117ms (-10%)
                  GetSubOrder N=1: P50 878ms → 805ms (-8%)
                  Total from baseline 5,048ms: → 1,117ms (-78%)
                  Limited gain: GetSubOrderMessageFromBatch (serial bulk load) dominates ~900ms
                  AllocatedKB overhead: +332 KB (N=1) / +442 KB (All) — 4 factory contexts per call
Decision Rule:    2+ independent calls + hot-path             → Async Parallel DB Coordinator
                  Shared _context across tasks                 → BLOCK — use IDbContextFactory
                  Calls have dependency chain                  → sequential await
Scope Pitfall:    await using var ctx declared inside if/for/while block → disposed at block exit,
                  before Task.WhenAll runs → InvalidOperationException: connection is closed.
                  Fix: declare ALL contexts at coordinator scope, before any branching.
                  See D15 for full rule and error signature.
Based on Knowledge:  → K25: EF Core DbContext Thread Safety and IDbContextFactory
Used in Incidents:   → I1: GetSubOrder API Latency Spike
Used in Decisions:   → D8: Use IDbContextFactory for Parallel GetSubOrderAsync
                     → D15: await using var Scope Rule
Source:           target.cs GetSubOrderAsync Phase 4, 2026-04-01
```

**Problem**: A coordinator method fires multiple independent DB calls sequentially — total latency = sum of all call times. Under high concurrency, threads block during I/O and the connection pool exhausts.

**Solution**: Resolve any shared context first (reference lookup, auth), then fire all independent DB calls concurrently via `Task.WhenAll`, each using its own `DbContext` from `IDbContextFactory`. Assemble results in memory after all tasks complete.

**When to USE**:
- Coordinator method calls 2+ independent DB operations sequentially (no data dependency between them)
- Hot-path API endpoint under concurrent load
- I/O wait % > 80% (threads blocking on DB, not CPU-bound)
- Sequential latency > 300ms and at least 2 calls can run in parallel
- .NET + EF Core stack with `IDbContextFactory` available

**When NOT to USE**:
- Calls have data dependencies (one result feeds the next query)
- Single DB call — parallelism adds overhead with zero benefit
- Legacy sync-only codebase where async migration risk is too high
- Low concurrency (< 10 req/s) — sequential async is sufficient

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Latency = max(tasks) not sum(tasks) | Requires IDbContextFactory — extra DI wiring |
| Frees thread pool during I/O wait | Harder to debug — parallel stack traces |
| Higher concurrency ceiling | Each task opens its own DB connection |
| Sync and async paths coexist safely | Async migration of all callers needed over time |

**Your stack (.NET / EF Core / PostgreSQL)**:

```csharp
// Step 1: Register factory in Program.cs
services.AddDbContextFactory<AppDbContext>(options =>
    options.UseNpgsql(connectionString));

// Step 2: Inject in service constructor
private readonly IDbContextFactory<AppDbContext> _contextFactory;

// Step 3: Coordinator method
public async Task<Result> GetSubOrderAsync(string orderId, string subOrderId)
{
    // Serial: must complete first (result feeds parallel tasks)
    var subOrderData = GetSubOrderMessage(orderId, subOrderId);
    string resolvedId = ResolveOnce(orderId); // resolve shared context once

    // Parallel: all independent — each gets its own DbContext
    await using var ctx1 = _contextFactory.CreateDbContext();
    await using var ctx2 = _contextFactory.CreateDbContext();
    await using var ctx3 = _contextFactory.CreateDbContext();

    await Task.WhenAll(
        GetOrderHeaderAsync(ctx1, resolvedId),
        GetOrderPaymentsAsync(ctx2, resolvedId),
        GetOrderPromotionAsync(ctx3, resolvedId)
    );
    // Assemble in memory — zero DB calls
}

// Step 4: Each async private method owns its context
private async Task<OrderModel> GetOrderHeaderAsync(DbContext ctx, string id)
{
    return await ctx.Set<OrderModel>()
        .AsNoTracking()
        .Include(o => o.Customer)
        .Where(o => o.SourceOrderId == id)
        .FirstOrDefaultAsync();
}
```

**BotE Impact**:
```
BEFORE (sequential): latency = t1 + t2 + t3 + t4
  Example: 400 + 300 + 250 + 200 = 1,150ms

AFTER (parallel):   latency = max(t1, t2, t3, t4)
  Example: max(400, 300, 250, 200) = 400ms  (-65%)

Pool pressure:
  BEFORE: 100 concurrent × 4 sequential queries × 0.01s = 4 connections held
  AFTER:  100 concurrent × 4 parallel queries × 0.01s = 4 connections held
  (same pool usage — but latency drops, so throughput improves)
```

**Decision Rule**:
- 2+ independent DB calls in one coordinator method + hot-path → use Async Parallel DB Coordinator
- Only 1 DB call → async/await alone is sufficient, no parallelism needed
- Calls have dependencies → use sequential `await` (dependency chain, not parallel)
- EF Core DbContext shared across tasks → BLOCK — must use `IDbContextFactory` (DbContext is NOT thread-safe)

**Real incident (measured, 2026-04-01)**: `GetSubOrder` (target.cs) — Phase 4 applied to repository-pattern codebase.

Sequential calls to `GetOrderHeaderAsync`, `GetOrderMessagePaymentsAsync`, `GetOrderPromotionAsync`, `GetRewardItemsBatchedAsync` replaced with `Task.WhenAll`. Each task receives its own `OrderRepository(_logger, ctxN)` using a factory-created context.

Results:
| Mode | Before Phase 4 | After Phase 4 | Change | Total from baseline |
|------|---------------|---------------|--------|---------------------|
| N=1 (single sub-order) | P50 878ms | P50 805ms | -8% | — |
| "All" (N≈10 sub-orders) | P50 1,242ms | P50 1,117ms | -10% | -78% from 5,048ms |

AllocatedKB overhead: +332 KB (N=1) / +442 KB (All) — 4 factory `OrderContext` instances per call.

Remaining bottleneck: `GetSubOrderMessageFromBatch` (serial bulk load, 16 Includes, AsSplitQuery) ≈ ~900ms of 1,117ms total. Cannot be parallelized — all parallel tasks depend on its result. Next lever: `IMemoryCache` on `GetStoreLocation` (5-min TTL).

**Pitfall: `await using var` scope inside conditional block**
```
// WRONG — ctx4 disposed when if block exits, before Task.WhenAll runs:
if (condition)
{
    await using var ctx4 = _contextFactory.CreateDbContext();  // ← DISPOSED HERE
    rewardTask = repo.GetRewardItemsBatchedAsync(ctx4, ...);
}
await Task.WhenAll(..., rewardTask);  // ← ctx4 already closed → InvalidOperationException

// CORRECT — all contexts at coordinator scope, before any branching:
await using var ctx1 = _contextFactory.CreateDbContext();
await using var ctx2 = _contextFactory.CreateDbContext();
await using var ctx3 = _contextFactory.CreateDbContext();
await using var ctx4 = _contextFactory.CreateDbContext();  // ← alive until after WhenAll
if (condition)
{
    rewardTask = repo.GetRewardItemsBatchedAsync(ctx4, ...);
}
await Task.WhenAll(..., rewardTask);  // ← all contexts still open
```
Error signature when violated: `System.InvalidOperationException: Invalid operation. The connection is closed.`
See also: D15 in kos-decisions.md.

**Related patterns**: P19 Coordinator-Level Resolution, P20 Bulk Load Then Map
**Related decisions**: D8 (IDbContextFactory choice), D15 (await using scope rule)

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

**Problem**: DB calls inside loops cause N+1 queries — latency grows linearly with record count.

**Solution**: Collect all IDs first, fetch in one `IN` query, map results in memory with a dictionary.

**When to USE**:
- You have a loop that calls the DB per item
- N > 100 records expected
- Read-heavy hot paths (APIs, message processors)

**When NOT to USE**:
- N is provably < 50 and always will be
- Data must be fetched with complex per-item conditions that can't be batched

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Reduces DB roundtrips drastically | Higher memory usage (all records in RAM) |
| Predictable latency | Risk of very large IN clauses (chunk if N > 1000) |
| Easy to implement in EF Core | Slightly more complex mapping code |

**Your Stack (.NET + EF Core)**:
```csharp
// Before (N+1)
foreach (var item in items)
{
    var detail = _context.Details.FirstOrDefault(d => d.ItemId == item.Id);
}

// After (Batch)
var ids = items.Select(i => i.Id).ToList();
var detailMap = _context.Details
    .Where(d => ids.Contains(d.ItemId))
    .AsNoTracking()
    .ToDictionary(d => d.ItemId);

foreach (var item in items)
{
    var detail = detailMap.GetValueOrDefault(item.Id);
}
```

**Decision Rule**:
- N < 50 → N+1 acceptable
- N > 100 → use batch
- N > 1000 → batch + chunk (500 per query)

**Real Incident (target.cs)**: GetSubOrder hot path — `GetRewardItem` called per sub-order in a loop (lines 69-77), `GetSubOrderMessage` called per sub-order (lines 518-540). For N=10 sub-orders, these two loops alone produce 20 sequential DB queries. Fix: batch with `Contains()`:

```csharp
// BEFORE (target.cs:69-77): N queries in loop
for (int i = 0; i < results.SourceSubOrderIdList.Count; i++)
{
    GetRewardItem(SourceOrderId, results.SourceSubOrderIdList[i], ref rewardItemMessageTmp);
}

// AFTER: 1 query
var allRewardItems = _context.PromotionItemTb
    .AsNoTracking()
    .Where(p => p.SourceOrderId == SourceOrderId
        && results.SourceSubOrderIdList.Contains(p.SourceSubOrderId)
        && !p.IsDelete)
    .ToList();
```

Combined with Eager Graph Loading (P18) for promotion Amount and Coordinator-Level Resolution (P19) for reference lookups.

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

**Problem**: EF Core navigation properties loaded lazily inside a loop cause one DB round-trip per property per entity — query count grows as O(n × relations). This is invisible at low volume and catastrophic at scale.

**Solution**: Move all navigation property loads into the `Include()` / `ThenInclude()` chain on the root query. EF Core (with `AsSplitQuery()`) fetches the full object graph in a fixed number of queries regardless of entity count.

**When to USE**:
- A method loops over a collection and accesses navigation properties per item
- The number of entities is unbounded or can grow with order/request size
- Hot-path read methods where latency matters
- Any `Entry().Reference().Load()` or `Entry().Collection().Load()` currently inside a loop

**When NOT to USE**:
- Navigation property is rarely needed (< 10% of calls) — lazy or conditional load is cheaper
- Graph is extremely deep (5+ levels) and most branches are unused — consider projection instead
- Single entity lookup where the property is only sometimes needed

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Fixed query count regardless of N | Loads data you may not always need |
| Works with AsSplitQuery() to avoid cartesian explosion | Deep Include() chains can be hard to read |
| Eliminates all loop-based lazy loads in one change | Must also add AsNoTracking() or tracking overhead increases |

**Your Stack (.NET + EF Core)**:
```csharp
// BEFORE: bare load + lazy loads per item inside loop
SubOrderModel subOrderModel = _context.SubOrder
    .Include(s => s.Items).ThenInclude(i => i.Amount)
    .AsSplitQuery()
    .Where(...).FirstOrDefault();

foreach (var item in subOrderModel.Items)
{
    // Each line = 1 DB call × N items
    _context.Entry(item.Amount).Reference(p => p.Normal).Query().Include(i => i.Taxes).Load();
    _context.Entry(item.Amount).Reference(p => p.Paid).Query().Include(i => i.Taxes).Load();
    _context.Entry(item).Reference(p => p.Promotion).Load();
    _context.Entry(item).Collection(p => p.Promotions).Load();
}

// AFTER: full graph in one query set — delete all Entry().Load() calls
SubOrderModel subOrderModel = _context.SubOrder
    .Include(s => s.Items)
        .ThenInclude(i => i.Amount)
            .ThenInclude(a => a.Normal).ThenInclude(n => n.Taxes)
    .Include(s => s.Items)
        .ThenInclude(i => i.Amount)
            .ThenInclude(a => a.Paid).ThenInclude(p => p.Taxes)
    .Include(s => s.Items).ThenInclude(i => i.Promotion)
    .Include(s => s.Items).ThenInclude(i => i.Promotions)
    .AsSplitQuery()
    .AsNoTracking()
    .Where(...).FirstOrDefault();
// Loop now reads from in-memory graph — zero DB calls
```

**Decision Rule**:
```
Entry().Load() inside a loop            → BLOCK — replace with Include() chain
Include() with 1 collection             → OK, no split query needed
Include() with 2+ collections           → AsSplitQuery() required
Include() chains > 4 levels deep        → consider projection to DTO instead
Eager load + read-only method           → always add AsNoTracking()
```

**Real Incident (target.cs)**: `GetOrderPromotion` (line 209) — `_context.Entry(datalist[i]).Reference(x => x.Amount).Load()` called per promotion inside a for loop. For P=3 promotions, that's 3 extra round-trips. Fix: add `.Include(op => op.Amount)` to the initial query (line 194):

```csharp
// BEFORE (target.cs:194-209): load then lazy-load Amount per item
OrderPromotionModel[] datalist = (from op in _context.OrderPromotion
    where op.SourceOrderId == SourceOrderId select op).ToArray();
for (int i = 0; i < datalist.Length; i++)
{
    _context.Entry(datalist[i]).Reference(x => x.Amount).Load(); // N+1
}

// AFTER: eager load in initial query
OrderPromotionModel[] datalist = _context.OrderPromotion
    .Include(op => op.Amount)
    .AsNoTracking()
    .Where(op => op.SourceOrderId == SourceOrderId)
    .ToArray();
// No loop load needed — Amount is already populated
```

Combined with Batch Query (P17) for reward items and Coordinator-Level Resolution (P19) for reference lookups.

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

**Problem**: Multiple sibling methods independently resolve the same shared context (e.g., looking up a canonical ID, resolving a reference mapping) — each one hits the DB separately for the same answer.

**Solution**: Resolve the shared context once at the coordinator (parent method) level and pass the resolved value down to all sub-calls.

**When to USE**:
- Two or more sibling methods resolve the same ID / reference / lookup
- The resolution is deterministic and doesn't change within the request scope
- The coordinator already has the input needed to perform the resolution

**When NOT to USE**:
- Each sub-call genuinely needs a different resolution (different input)
- The resolved value changes between calls (e.g., updated by a concurrent write)
- The sub-call is used independently in other contexts where the coordinator doesn't exist

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Eliminates redundant DB queries | Slightly changes method signatures (pass resolved ID) |
| Makes the data flow explicit | Sub-methods may need two modes (with/without internal resolution) |
| Easy to audit — resolution happens in one place | Callers outside the coordinator must still resolve independently |

**Your Stack (.NET + EF Core)**:
```csharp
// BEFORE (target.cs:55-57): each sub-call resolves IsExistOrderReference independently
// GetOrderHeader calls IsExistOrderReference internally (line 479)
// GetOrderMessagePayments calls IsExistOrderReference internally (line 131)
// GetOrderPromotion calls IsExistOrderReference internally (line 185)
// = 3 calls × 2-3 queries each = 6-9 redundant queries

var orderHeader = GetOrderHeader(SourceOrderId);
var orderPayments = GetOrderMessagePayments(SourceOrderId);
results.OrderPromotion = GetOrderPromotion(SourceOrderId);

// AFTER: resolve once at coordinator, pass resolved ID down
string resolvedOrderId = SourceOrderId;
string refSourceOrderId = string.Empty;
if (IsExistOrderReference(SourceOrderId, ref refSourceOrderId))
    resolvedOrderId = refSourceOrderId;

var orderHeader = GetOrderHeader(resolvedOrderId, skipRefCheck: true);
var orderPayments = GetOrderMessagePayments(resolvedOrderId, skipRefCheck: true);
results.OrderPromotion = GetOrderPromotion(resolvedOrderId, skipRefCheck: true);
// = 1 query total instead of 6-9
```

**Decision Rule**:
```
Same resolver called 2+ times for same ID in one request → BLOCK
  Fix: hoist to coordinator, pass result down
Same resolver called by independent entry points         → OK, each resolves for itself
Resolver result could change mid-request (race condition) → do NOT cache, resolve per call
```

**Real Incident (target.cs)**: `IsExistOrderReference` called independently by `GetOrderHeader` (line 479), `GetOrderMessagePayments` (line 131), and `GetOrderPromotion` (line 185) — all for the same `SourceOrderId`. Each call performs 2-3 DB queries (`.Any()` + `.Where().FirstOrDefault()`). Hoisting to `GetSubOrder` (the coordinator) eliminates 4-8 redundant queries per request.

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

**Problem**: A method loops over N records, calling the DB once per record — the **outer loop** is the bottleneck, not the queries inside each iteration. Each iteration may load a full entity graph with its own network round-trip, making latency scale as O(N).

**This is distinct from P17 (Batch Query)**: P17 batches a single supporting lookup inside a loop. P20 eliminates the outer loop itself — the entire entity graph for all N records is loaded in one query, then all mapping is done in memory.

**Solution**: Collect all IDs → bulk-load ALL entities with full Include chain in one query + `AsSplitQuery()` → batch all supporting lookups → map ViewModels in memory (zero per-record DB calls in the mapping phase).

**When to USE**:
- A method loops N times and each iteration issues 5+ DB queries
- N is bounded (e.g., 5–50 sub-orders) — not unbounded streaming data
- The full entity graph can fit in memory for N records
- The method is on a hot read path (API endpoint, not background job)

**When NOT to USE**:
- N is unbounded or N > 500 (memory risk — use chunked streaming instead)
- Entity graph is sparse and most Include paths will load nothing (projection is better)
- Per-record conditions are unique and can't be expressed as a bulk `Contains()` query

**Complexity**: High (significant refactor — method structure changes completely)

**Trade-offs**:
| Pros | Cons |
|------|------|
| Eliminates N×queries → O(1) queries regardless of N | Single large query may be slower for N=1 than before |
| Latency becomes nearly independent of sub-record count | All data loaded into RAM at once — watch memory for large N |
| GC pressure stable and predictable | AsSplitQuery generates ~16+ split queries — higher query count but faster total |
| Method structure becomes load → batch → map | Requires full method rewrite, not an incremental fix |

**Your Stack (.NET + EF Core)**:
```csharp
// BEFORE: N outer-loop calls, each with ~44 sequential queries
foreach (var subOrder in subOrders)
{
    GetSubOrderMessage(orderId, subOrder.SourceSubOrderid, ref output);
    // Each call: IsExistOrderReference + GetLatestOrder + GetOrderItemOtherInfo +
    //            multiple Entry().Load() per item + GetStoreLocation + GetPackageTb
}

// AFTER: Bulk Load Then Map (Phase 3 revised — target.cs:593-1331)
// Step 1: Batch resolve all references (1 query)
var orderRefs = _context.OrderReference.AsNoTracking()
    .Where(w => w.NewSourceOrderId == orderId && subOrderIds.Contains(w.NewSourceSubOrderId))
    .ToList();
var refsBySubOrder = orderRefs
    .GroupBy(g => g.NewSourceSubOrderId)
    .ToDictionary(g => g.Key, g => g.OrderByDescending(o => o.CreatedDate).First());

// Step 2: Bulk load ALL sub-orders with full entity graph (~16 split queries total)
var allSubOrders = _context.SubOrder
    .AsNoTracking()
    .Include(so => so.Items).ThenInclude(i => i.Amount).ThenInclude(a => a.Normal).ThenInclude(n => n.Taxes)
    .Include(so => so.Items).ThenInclude(i => i.Amount).ThenInclude(a => a.Paid).ThenInclude(p => p.Taxes)
    // ... 14 more Include paths ...
    .AsSplitQuery()
    .Where(w => loadOrderIds.Contains(w.SourceOrderId) && loadSubOrderIds.Contains(w.SourceSubOrderid))
    .ToList();

// Step 3: Batch load all supporting data (2-3 more queries)
var allItemOtherInfo = _context.ItemOtherInfo.AsNoTracking()
    .Where(w => loadOrderIds.Contains(w.SourceOrderId) && loadSubOrderIds.Contains(w.SourceSubOrderId))
    .ToList();

// Step 4: Map ALL ViewModels in memory — zero DB calls
foreach (var pair in resolvedPairs)
{
    var subOrderModel = allSubOrders.FirstOrDefault(s => ...);
    var itemOtherInfo = allItemOtherInfo.FirstOrDefault(w => ...);  // dictionary lookup, no DB
    // ... build ViewModel from in-memory data ...
}
```

**AsSplitQuery note**: With 16 Include paths, EF Core generates 16 split queries in one bulk load instead of a cartesian join. This produces ~16 SQL statements but they are batched for ALL N records. Without AsSplitQuery, 16 paths × N records would produce N×16 cartesian rows (data explosion).

**Decision Rule**:
```
Outer loop calls DB > 5 times per iteration AND N > 5       → apply Bulk Load Then Map
Entity graph has > 3 collection Include paths               → add AsSplitQuery()
All N records fit in memory (N < 200 and entity < 10KB)     → bulk load safe
N > 500 OR entity very large                                → chunk before bulk loading
Per-record supporting data can be batched with Contains()   → include in bulk approach
Some per-record calls cannot be batched (external API, etc) → keep those as per-record, accept residual latency
```

**Real Incident (target.cs)**: `GetSubOrderMessage` list method (lines 593-634) looped N=10 sub-orders, calling the inner method per sub-order — each inner call issued ~44 queries sequentially = ~440 total. Refactored to bulk-load all 10 sub-orders with 16 Include paths + `AsSplitQuery()` + batch all supporting queries. Result: **P50 dropped from 2,730ms to 1,505ms (-45%)** measured 2026-03-26.

**Failed approach (do not repeat)**: Replacing `Entry().Load()` inside each iteration with an expanded Include chain + `AsSplitQuery()` inside the loop produces **zero improvement** — AsSplitQuery generates the same number of queries as the lazy loads it replaces, 1:1. The outer loop must be eliminated, not optimized per-iteration. See kos-incident.md Phase 3 attempt 1 notes.

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

**Problem**: PostgreSQL's default autovacuum scale factor (0.20) triggers only after 20% of live rows become dead. On large tables (> 500K rows), this means hundreds of thousands of dead tuples accumulate silently — degrading index scan performance and bloating storage — before autovacuum fires. After a VACUUM, index pages are marked "reusable" but the index file does not shrink, leaving a sparse B-tree that wastes I/O on every scan.

**Solution**: Override per-table autovacuum settings to trigger at 1% dead rows. After any high-churn period, run `REINDEX CONCURRENTLY` to compact index files and restore B-tree density.

**When to USE**:
- Any PostgreSQL table exceeding 500K rows with default autovacuum settings
- After detecting dead_ratio > 5% in `pg_stat_user_tables`
- After `last_autovacuum IS NULL` on a large active table (autovacuum never triggered)
- After heavy bulk DELETE or UPDATE migrations
- After index bloat > 30% (reusable_pages / total_pages)

**When NOT to USE**:
- Tables with < 50K rows and infrequent writes — default autovacuum is sufficient
- Read-only tables — no dead tuples generated, no vacuum needed
- Aggressive `autovacuum_vacuum_scale_factor = 0.001` on tiny tables — unnecessary overhead

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Prevents silent bloat accumulation | Autovacuum runs more frequently (but each pass is lighter) |
| Maintains B-tree density for fast index scans | REINDEX CONCURRENTLY takes 5–20 min on large tables |
| No application code changes required | Extra connections opened during REINDEX |
| Non-blocking — VACUUM and REINDEX CONCURRENTLY don't lock table | Requires DBA access to ALTER TABLE |

**Your Stack (PostgreSQL)**:

```sql
-- Step 1: Detect tables with dead tuple problem
SELECT
  relname AS table_name,
  n_live_tup,
  n_dead_tup,
  ROUND(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100, 2) AS dead_ratio_pct,
  last_autovacuum,
  last_analyze
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
   OR (n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0)) > 0.05
ORDER BY n_dead_tup DESC;

-- Step 2: Immediate cleanup
VACUUM (ANALYZE, VERBOSE) stockadjustments;

-- Step 3: Per-table autovacuum tuning (apply to any table > 500K rows)
ALTER TABLE stockadjustments SET (
  autovacuum_vacuum_scale_factor = 0.01,    -- trigger at 1% dead rows
  autovacuum_vacuum_threshold = 1000,
  autovacuum_analyze_scale_factor = 0.005,
  autovacuum_analyze_threshold = 500
);

-- Step 4: Check index bloat
SELECT
  indexrelname AS index_name,
  pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
  idx_scan,
  idx_tup_read
FROM pg_stat_user_indexes
WHERE relname = 'stockadjustments'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Step 5: Rebuild bloated indexes (non-blocking)
REINDEX INDEX CONCURRENTLY stockadjustments_pkey;
REINDEX INDEX CONCURRENTLY stockadjustments_adjusted_at_idx;
-- (repeat for each bloated index)

-- Monitor REINDEX progress
SELECT phase, blocks_done, blocks_total,
       ROUND(blocks_done::numeric / NULLIF(blocks_total, 0) * 100, 1) AS pct
FROM pg_stat_progress_create_index
WHERE relid = 'stockadjustments'::regclass;
```

**BotE Impact**:
```
BEFORE (stockadjustments incident):
  Index size:   ~1.7 GB (217,353 pages)
  Index bloat:  63% — 137,400 reusable pages = ~1.07 GB wasted
  PK scan:      traverses 85% empty pages per lookup
  Heap:         ~140 MB dead tuple bloat

AFTER (VACUUM + REINDEX CONCURRENTLY):
  Index size:   ~630 MB (-63%)
  Index bloat:  < 5%
  PK scan:      dense B-tree, 2–3× fewer page reads
  Heap:         0 dead tuples
```

**Decision Rule**:
```
Table rows > 5M   → autovacuum_vacuum_scale_factor = 0.005
Table rows > 500K → autovacuum_vacuum_scale_factor = 0.01
Table rows > 100K → autovacuum_vacuum_scale_factor = 0.05
Table rows < 100K → default (0.20) is fine

dead_ratio > 10% AND last_autovacuum IS NULL → run VACUUM immediately, then fix scale_factor
dead_ratio > 5% consistently despite autovacuum → check for long-running blocking transactions
index reusable_pages / total_pages > 30%      → run REINDEX CONCURRENTLY
VACUUM FULL (instead of REINDEX CONCURRENTLY)  → only in maintenance window; locks table entirely
```

**Real incident**: `stockadjustments` (spc_inventory, 2026-03-30). 702,783 dead rows (14.5%) — autovacuum never triggered because default threshold = 828,932. After manual VACUUM: heap clean but 63% index bloat (1.07 GB waste) remained. REINDEX CONCURRENTLY queued for all 6 indexes.

**KOS Summary**:
- Root cause of silent bloat: `autovacuum_vacuum_scale_factor = 0.20` default means autovacuum fires only when dead rows > 20% of live rows — on large tables, that threshold is never reached in normal operations
- Detection query: `pg_stat_user_tables` — check `n_dead_tup`, `dead_ratio`, `last_autovacuum`
- VACUUM vs REINDEX: VACUUM cleans dead tuples (heap), REINDEX rebuilds index B-tree (structure). Both needed after high-churn period
- REINDEX CONCURRENTLY: non-blocking, safe for production. Takes 5–20 min per index on 4M rows. Monitor via `pg_stat_progress_create_index`
- VACUUM FULL: exclusive lock — never in production except maintenance window
- Per-table override: `ALTER TABLE t SET (autovacuum_vacuum_scale_factor = 0.01)` — no restart needed, takes effect immediately
- Threshold ladder: > 5M rows → 0.005, > 500K → 0.01, > 100K → 0.05, < 100K → default 0.20

**Related patterns**: none — DB operations pattern, standalone.
**Related decisions**: D12 (REINDEX CONCURRENTLY vs VACUUM FULL — decision record with full incident data)

---

### P22: EF Compiled Query Cache Management

```
Name:             EF Compiled Query Cache Management
Category:         .NET Performance / EF Core
Stack:            .NET / EF Core 7.0+ (AsSplitQuery support in compiled queries)
Summary:          Precompile hot-path EF Core queries as static Func<> fields using
                  EF.CompileQuery or EF.CompileAsyncQuery. Eliminates per-call DynamicMethod
                  allocation in EF's static CompiledQueryCache. Non-reclaimable cache entries
                  are created once at first call and reused for the process lifetime.
When to Use:      Query called > 100×/min on a hot API path.
                  dumpheap -stat shows DynamicMethod count > 2000.
                  Query has a fixed shape (no dynamic filter additions at runtime).
                  EF Core 7.0+ (required for AsSplitQuery in compiled queries).
When NOT to Use:  Query shape changes dynamically (optional .Where clauses based on runtime flags).
                  One-off or infrequent queries (compilation cost is negligible).
                  EF Core < 7.0 with AsSplitQuery (throws at runtime — upgrade or remove split).
Complexity:       Low
Decision Rule:    DynamicMethod count > 2000 AND query is on hot path     → apply EF.CompileQuery
                  Count stable across load test dumps (delta ≈ 0)          → ceiling reached, no action
                  Count grows linearly with requests                        → unbounded, fix immediately
                  Query has optional filters                                → cannot compile statically
Based on Knowledge:  → K28: EF Core Compiled Query Cache and DynamicMethod Accumulation
Used in Incidents:   → I1: GetSubOrder API Latency Spike
Used in Decisions:   → D13: Apply EF.CompileQuery to GetSubOrderMessage Bulk Query
Related Tech Assets: → TA15: EF.CompileQuery Static Field Template
Source:           Order.API-3.dmp + Order.API-11.dmp load test analysis, 2026-03-31
```

**Problem**: EF Core compiles every unique LINQ expression tree into IL at runtime and stores the result in a static `CompiledQueryCache`. Each unique expression tree = 1 `DynamicMethod` + 1 `DynamicILGenerator` + 1 `DynamicResolver` object held in static memory — never collected by GC. Under production load with many query variations, this cache grows into thousands of entries consuming 5–10 MB of non-reclaimable static heap.

**Solution**: Precompile hot-path queries as static `Func<>` fields using `EF.CompileAsyncQuery` (or `EF.CompileQuery` for sync). The expression tree is compiled exactly once per process lifetime regardless of how many times the method is called or how many concurrent requests run.

**When to USE**:
- Any query called on a hot API path (called > 100× / minute)
- Large Include chains with many navigation properties (each variation = new cache entry)
- When heap dump (`dumpheap -stat`) shows DynamicMethod / DynamicILGenerator object count > 1,000
- Batch queries with `Contains()` over ID lists (each unique set → unique expression tree)

**When NOT to USE**:
- One-off admin queries or background jobs called infrequently
- Queries that change shape based on runtime conditions (the compiled signature must be fixed)
- Very simple queries with no Includes (compilation cost is negligible)

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Cache entry created once — eliminates per-call compilation overhead | Query shape is fixed at compile time — cannot add/remove dynamic filters |
| DynamicMethod/ILGenerator objects: N (per unique query) → 1 | All parameters must be passed as `Func<>` arguments — no closures |
| Reduces static heap by 5–10 MB for hot-path queries | Requires static field — not injectable, harder to test in isolation |
| Available as async: `EF.CompileAsyncQuery` | `IAsyncEnumerable` return for multi-row; `Task<T>` for single-row |

**Your Stack (.NET + EF Core)**:
```csharp
// BEFORE: new expression tree compiled on every call (per unique parameter set)
public async Task<List<SubOrderModel>> GetSubOrdersAsync(string[] ids)
{
    return await _context.SubOrders
        .AsNoTracking()
        .Include(so => so.Items).ThenInclude(i => i.Amount)
        .Where(so => ids.Contains(so.SourceSubOrderId))
        .ToListAsync();
}
// Heap: +1 DynamicMethod + 1 DynamicILGenerator per unique call

// AFTER: compiled once, reused on every call
private static readonly Func<AppDbContext, string[], IAsyncEnumerable<SubOrderModel>> _getSubOrdersBulk =
    EF.CompileAsyncQuery((AppDbContext ctx, string[] ids) =>
        ctx.SubOrders
           .AsNoTracking()
           .Include(so => so.Items).ThenInclude(i => i.Amount)
           .Where(so => ids.Contains(so.SourceSubOrderId)));

public async Task<List<SubOrderModel>> GetSubOrdersAsync(string[] ids)
{
    var results = new List<SubOrderModel>();
    await foreach (var item in _getSubOrdersBulk(_context, ids))
        results.Add(item);
    return results;
}
// Heap: +1 DynamicMethod + 1 DynamicILGenerator total — never increases again
```

**Diagnosing from heap dump (`dotnet-dump analyze`)**:
```
// In dotnet-dump REPL:
dumpheap -stat

// Red flags in output:
System.Reflection.Emit.DynamicMethod       > 1,000 objects → compiled query cache pressure
System.Reflection.Emit.DynamicILGenerator  > 1,000 objects → (always matches DynamicMethod count)
System.Reflection.Emit.DynamicResolver     > 1,000 objects → (always matches DynamicMethod count)

// Healthy service: < 500 DynamicMethod objects
// Incident: heapstat-3.txt showed 17,557 DynamicMethod objects (6 MB, non-reclaimable)
```

**Decision Rule**:
```
DynamicMethod count < 500        → healthy, no action needed
DynamicMethod count 500–2,000    → investigate — which queries are not compiled statically?
DynamicMethod count > 2,000      → apply EF.CompileAsyncQuery to top 5 hottest queries
DynamicMethod count = DynamicILGenerator count → always true (1:1 relationship)

Query called > 100×/min AND has Include chain → compile it as static Func<>
Query with dynamic filters (optional .Where clauses) → cannot compile statically → accept cache growth
```

**Real incident (Order.API-3.dmp → Order.API-11.dmp, 2026-03-31)**:
- Before fix (heapstat-3): 17,557 `DynamicMethod` objects — bulk query with 16 Include paths recompiled per unique call variation. Unbounded growth.
- Fix applied: `_bulkSubOrderQuery = EF.CompileQuery(...)` static field. Cold start first call allocated 106 MB (one-time IL compilation). Steady-state AllocatedKB dropped from 1,808 KB → 1,536 KB per call.
- Load test validation (heapstat-4): `DynamicMethod` count 17,557 → **7,356 (-58%)** at higher load. Count is **stable** — confirmed ceiling, not unbounded growth. Remaining 7,356 = service-wide unique query footprint across all endpoints.
- Heap: 112 MB → 90 MB (-20%). SubOrderMessageViewModel: 836 → 50 (-94%) — no ChangeTracker leak under concurrency.

**KOS Summary**:
- Static field pattern: `private static readonly Func<DbContext, params, IAsyncEnumerable<T>> _query = EF.CompileAsyncQuery(...)`
- Compiled exactly once per process lifetime regardless of call count or concurrency
- Cold start cost: ~106 MB one-time IL compilation on first call — acceptable, happens once at warmup
- Steady-state gain: eliminates per-call DynamicMethod allocation → AllocatedKB drops per call
- Limitation: query shape must be fixed. Cannot add optional `.Where()` clauses at runtime
- Multi-row async: return `IAsyncEnumerable<T>`, enumerate with `await foreach`. Single-row: return `Task<T>`
- Diagnose with `dotnet-dump analyze` → `dumpheap -stat` → look for DynamicMethod / DynamicILGenerator count
- Healthy ceiling: DynamicMethod count stabilizes at N×(unique query shapes across all endpoints) — stable is fine, unbounded growth is the problem
- AsSplitQuery + CompileQuery: supported in EF Core 10. Generates multiple compiled split queries, one per Include batch

**Related patterns**: P20 Bulk Load Then Map, P16 Async Parallel DB Coordinator
**Related decisions**: D13 (EF.CompileQuery static field — decision record with full heap dump incident data)

---
