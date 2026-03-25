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