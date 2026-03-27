# 🧩 Pattern Library

> Read this file when the user asks about a specific pattern, asks "should I use X?",
> or when Pattern Guidance mode is triggered. Use the quick index to jump to the right section.

---

## Quick Index

| # | Pattern | Category | TL;DR |
|---|---------|----------|-------|
| 1 | [Batch Query](#1-batch-query) | Performance | Replace N+1 with bulk IN clause |
| 2 | [Outbox](#2-outbox) | Messaging | Guarantee event publish with DB write |
| 3 | [CQRS](#3-cqrs) | Architecture | Separate read and write models |
| 4 | [Saga](#4-saga) | Distributed | Manage multi-service transactions |
| 5 | [Retry + DLQ](#5-retry--dlq) | Resilience | Kafka consumer failure recovery |
| 6 | [Idempotency Key](#6-idempotency-key) | Resilience | Safe-to-repeat operations |
| 7 | [Staging → Validate → Apply](#7-staging--validate--apply) | Data | ETL / FTP ingestion pipeline |
| 8 | [Repository](#8-repository) | Architecture | Isolate data access from business logic |
| 9 | [Circuit Breaker](#9-circuit-breaker) | Resilience | Protect against failing dependencies |
| 10 | [Competing Consumers](#10-competing-consumers) | Messaging | Scale Kafka consumers horizontally |
| 11 | [Eager Graph Loading](#11-eager-graph-loading) | Performance | Load full entity graph in one shot via Include() chain |
| 12 | [Coordinator-Level Resolution](#12-coordinator-level-resolution) | Performance | Resolve shared context once at parent, pass down |
| 13 | [Bulk Load Then Map](#13-bulk-load-then-map) | Performance | Replace N outer-loop DB calls with one bulk query + in-memory mapping |
| 14 | [Token Bucket Rate Limiting](#14-token-bucket-rate-limiting) | API Design | Protect APIs from burst traffic with refillable token budget |
| 15 | [Consistent Hashing Ring](#15-consistent-hashing-ring) | Scalability | Minimize key remapping when nodes are added or removed |
| 16 | [Fanout on Write (Push)](#16-fanout-on-write-push) | Architecture | Pre-compute follower feeds at write time for fast reads |
| 17 | [Fanout on Read (Pull)](#17-fanout-on-read-pull) | Architecture | Assemble feed at read time — avoid write amplification |
| 18 | [Hybrid Fanout](#18-hybrid-fanout) | Architecture | Push for regular users, pull for celebrities |
| 19 | [Event Sourcing](#19-event-sourcing) | Architecture | Immutable event log as the source of truth |
| 20 | [Scatter-Gather](#20-scatter-gather) | Distributed | Fan-out query across shards, merge results |
| 21 | [Write-Ahead Log (WAL)](#21-write-ahead-log-wal) | Resilience | Persist intent before applying — enables crash recovery |
| 22 | [Geohash Bucketing](#22-geohash-bucketing) | Data | Encode lat/lon as string prefix for efficient nearby search |
| 23 | [Snowflake ID Generation](#23-snowflake-id-generation) | Distributed | 64-bit time-sortable IDs with no coordination |
| 24 | [Hosted Payment Page](#24-hosted-payment-page) | API Design | Delegate card data to PSP — eliminate PCI scope |
| 25 | [DLQ with Reconciliation](#25-dlq-with-reconciliation) | Resilience | Dead letter queue + end-of-day financial reconciliation |

---

## 1. Batch Query

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

Combined with Eager Graph Loading (Pattern #11) for promotion Amount and Coordinator-Level Resolution (Pattern #12) for reference lookups.

---

## 2. Outbox

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

## 3. CQRS

**Problem**: Read and write operations have very different shapes — writes need validation and consistency, reads need speed and projection. Forcing both through the same model creates friction.

**Solution**: Separate the write model (commands) from the read model (queries). They can share the same DB or use different stores.

**When to USE**:
- Read/write ratio is very asymmetric (e.g., 100:1 reads)
- Read shape is very different from write shape
- You need to optimize read performance independently
- You're building event-sourced systems

**When NOT to USE**:
- Simple CRUD with no complex queries
- Small teams where added complexity isn't justified
- Early-stage systems (premature optimization)

**Complexity**: High

**Trade-offs**:
| Pros | Cons |
|------|------|
| Read and write can scale independently | More code, more complexity |
| Read models optimized for query patterns | Eventual consistency between write and read |
| Clear separation of concerns | Harder to debug sync issues |

**Architecture Evolution** (from GetSubOrderMessage):
```
Before:  API → EF → DB (many queries, write model used for reads)
After:   API → Batch Load → In-memory mapping
Next:    API → Read Model → (optional cache)  ← this is CQRS
```

**Decision Rule**:
- Same model works fine for reads and writes? → Skip CQRS
- Reads are slow because write model is complex? → CQRS read model
- Need real-time consistency? → Same DB, two models
- Can tolerate lag? → Separate read store, event-driven sync

---

## 4. Saga

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

## 5. Retry + DLQ

**Problem**: Kafka consumers fail on some messages (transient DB error, bad payload, downstream timeout). Without a strategy, messages are lost or block the partition.

**Solution**: Retry with backoff on transient failures. After max retries, route to a Dead Letter Queue (DLQ) for manual inspection and reprocessing.

**When to USE**:
- Any Kafka consumer that calls external systems (DB, APIs)
- Messages that may have transient failures
- You need audit trail of failed messages

**When NOT to USE**:
- Idempotency isn't guaranteed (retrying causes side effects)
- Poison pill messages that will always fail (route to DLQ immediately)

**Complexity**: Low–Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Handles transient failures automatically | DLQ requires monitoring + manual intervention |
| Prevents data loss | Retry storms can overload downstream |
| Clear failure audit trail | Ordering may break if retries interleave |

**Your Stack (Go + Kafka)**:
```go
const maxRetries = 3

for attempt := 0; attempt <= maxRetries; attempt++ {
    err := processMessage(msg)
    if err == nil {
        break
    }
    if attempt == maxRetries || isPoisonPill(err) {
        publishToDLQ(msg, err)
        break
    }
    time.Sleep(backoff(attempt)) // exponential backoff
}
```

**Decision Rule**:
- Transient error (timeout, lock)? → Retry with backoff
- Permanent error (bad schema, business rule violation)? → DLQ immediately
- Unknown? → Retry 3x, then DLQ

---

## 6. Idempotency Key

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

## 7. Staging → Validate → Apply

**Problem**: Raw data from external sources (FTP, API, partner systems) is often dirty, incomplete, or duplicated. Writing it directly to the main DB corrupts production data.

**Solution**: Three-phase pipeline: load raw data into a staging table, validate and transform it, then apply only clean records to the main DB. Failed records stay in staging for review.

**When to USE**:
- FTP / file-based ingestion
- External partner data with unknown quality
- Large batch imports
- Data sync with change detection

**When NOT to USE**:
- Real-time, low-latency ingestion where staging delay is unacceptable
- Fully trusted internal sources with schema guarantees

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Production DB always has clean data | Extra storage for staging table |
| Failed records are auditable | More pipeline steps to maintain |
| Easy to reprocess after fixing bugs | Latency added by staging phase |

**Your Stack (FTP → PostgreSQL)**:
```
FTP File → Staging Table (raw insert, no validation)
         → Validation Job (flag invalid rows)
         → Transform Job (normalize, enrich)
         → Apply Job (upsert to main DB, mark staging row as processed)
         → Event (OrderSynced published to Kafka)
```

**Decision Rule**:
- External/untrusted source? → Always use staging
- Internal/trusted source? → Can skip staging, add validation inline
- Need replay on bug fix? → Staging is mandatory

---

## 8. Repository

**Problem**: Business logic is tightly coupled to EF Core / SQL queries. Testing is hard, swapping data sources is hard, and query logic bleeds into services.

**Solution**: Abstract data access behind a repository interface. The service depends on the interface, not the ORM.

**When to USE**:
- You want to unit test services without hitting the DB
- Data access logic is complex and repeated
- You may need to swap data sources (e.g., add cache, switch ORM)

**When NOT to USE**:
- Simple CRUD apps where abstraction adds no value
- When you're already using CQRS with dedicated query handlers

**Complexity**: Low

**Trade-offs**:
| Pros | Cons |
|------|------|
| Testable services (mock the repo) | Extra layer, more files |
| Consistent query interface | Risk of becoming a "God repo" with too many methods |
| Encapsulates ORM details | EF Core's Unit of Work can leak through |

**Decision Rule**:
- Complex query logic repeated in multiple services? → Repository
- Simple, one-off queries? → Direct DbContext is fine
- Need unit tests for business logic? → Repository with interface

---

## 9. Circuit Breaker

**Problem**: Calling a slow or failing external service causes your service to also slow down or fail — cascading failures across the system.

**Solution**: Track failure rate. After threshold is exceeded, "open" the circuit and fail fast without calling the dependency. After a cooldown, allow one test request ("half-open"). If it succeeds, close the circuit.

**States**: Closed → Open → Half-Open → Closed

**When to USE**:
- Calling external APIs, partner services, or slow microservices
- You need to fail fast instead of waiting for timeout
- Downstream service has known instability

**When NOT to USE**:
- Internal in-process calls (no network, no need)
- Operations where failing fast causes more harm than waiting

**Complexity**: Medium

**Trade-offs**:
| Pros | Cons |
|------|------|
| Prevents cascade failures | Adds state management complexity |
| Fast failure = better UX | Threshold tuning required |
| Allows downstream to recover | Half-open logic needs careful design |

**Your Stack (.NET)**:
```csharp
// Using Polly
var policy = Policy
    .Handle<HttpRequestException>()
    .CircuitBreakerAsync(
        exceptionsAllowedBeforeBreaking: 3,
        durationOfBreak: TimeSpan.FromSeconds(30)
    );
```

**Decision Rule**:
- Calling external service? → Add circuit breaker
- Timeout > 2s expected? → Circuit breaker + timeout policy
- Internal service mesh? → Circuit breaker at mesh level (not app level)

---

## 10. Competing Consumers

**Problem**: A single Kafka consumer can't keep up with message throughput. Processing is too slow, lag grows.

**Solution**: Run multiple consumer instances in the same consumer group. Kafka distributes partitions across them — each partition is owned by one consumer, enabling parallel processing.

**When to USE**:
- Consumer lag is growing
- Processing time per message is high (DB writes, external calls)
- You need horizontal scalability

**When NOT to USE**:
- Messages within a key must be processed in strict order (one consumer per key)
- Shared state between consumers causes race conditions

**Complexity**: Low (Kafka handles it)

**Trade-offs**:
| Pros | Cons |
|------|------|
| Linear scale-out | Partition count limits max parallelism |
| No code change needed (Kafka handles distribution) | Order only guaranteed within a partition |
| Fault tolerant (rebalance on failure) | Idempotency required (rebalance = redelivery) |

**Decision Rule**:
- Lag growing and CPU/IO bound? → Add consumer instances
- Need order across all messages? → Single consumer (accept the bottleneck)
- Need order per entity (e.g., per OrderId)? → Partition by key, multiple consumers safe

---

## 11. Eager Graph Loading

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

Combined with Batch Query (Pattern #1) for reward items and Coordinator-Level Resolution (Pattern #12) for reference lookups.

---

## 12. Coordinator-Level Resolution

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

## 13. Bulk Load Then Map

**Problem**: A method loops over N records, calling the DB once per record — the **outer loop** is the bottleneck, not the queries inside each iteration. Each iteration may load a full entity graph with its own network round-trip, making latency scale as O(N).

**This is distinct from Pattern #1 (Batch Query)**: Pattern #1 batches a single supporting lookup inside a loop. Pattern #13 eliminates the outer loop itself — the entire entity graph for all N records is loaded in one query, then all mapping is done in memory.

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

**Failed approach (do not repeat)**: Replacing `Entry().Load()` inside each iteration with an expanded Include chain + `AsSplitQuery()` inside the loop produces **zero improvement** — AsSplitQuery generates the same number of queries as the lazy loads it replaces, 1:1. The outer loop must be eliminated, not optimized per-iteration. See incident-log.md Phase 3 attempt 1 notes.

---

## 14. Token Bucket Rate Limiting

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

## 15. Consistent Hashing Ring

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

## 16. Fanout on Write (Push)

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
- Celebrity users (> 1M followers)? → Fanout on Read (#17)
- Mixed platform? → Hybrid Fanout (#18)

---

## 17. Fanout on Read (Pull)

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

## 18. Hybrid Fanout

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

## 19. Event Sourcing

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

## 20. Scatter-Gather

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

## 21. Write-Ahead Log (WAL)

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
- Event log that doubles as WAL? → Event Sourcing (#19) subsumes WAL
- Kafka segment files? → Kafka uses WAL internally (you don't implement it)

---

## 22. Geohash Bucketing

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

## 23. Snowflake ID Generation

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

---

## 24. Hosted Payment Page

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

---

## 25. DLQ with Reconciliation

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
- After DLQ message fixed → replay with same consumer group (idempotency key prevents double-processing)