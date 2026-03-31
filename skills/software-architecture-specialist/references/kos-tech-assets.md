# KOS — Tech Assets

> Cross-linked per the Incident → Knowledge → Pattern → Decision → Reuse loop.

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

### TA12: Dead Tuple Health Monitor Query (PostgreSQL)

```
Name:             Dead Tuple Health Monitor
Type:             Code Snippet
Language:         SQL / PostgreSQL
Usage:            Run on a schedule (daily or weekly) or after any heavy write/delete operation.
                  Alert when dead_ratio > 5% on tables with > 100K rows.
                  Add to pg_cron, Grafana alert, or external cron scheduler.

SELECT
  schemaname,
  relname AS table_name,
  n_live_tup AS live_rows,
  n_dead_tup AS dead_rows,
  ROUND(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100, 2) AS dead_ratio_pct,
  last_vacuum,
  last_autovacuum,
  last_analyze,
  n_mod_since_analyze
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
   OR (n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0)) > 0.05
ORDER BY n_dead_tup DESC;

Related Knowledge:  → K26: PostgreSQL MVCC and Dead Tuples
Related Pattern:    → P21: Per-Table Storage Hygiene
```

---

### TA13: Per-Table Autovacuum Configuration (PostgreSQL)

```
Name:             Per-Table Autovacuum Scale Factor Override
Type:             Config Snippet
Language:         SQL / PostgreSQL
Usage:            Apply to any table > 500K rows with default autovacuum settings.
                  Run once — persists in pg_class until explicitly changed.
                  Scale by table size: 0.005 for > 5M rows, 0.01 for > 500K, 0.05 for > 100K.

-- For large tables (> 500K rows): trigger vacuum at ~1% dead rows
ALTER TABLE stockadjustments SET (
  autovacuum_vacuum_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 1000,
  autovacuum_analyze_scale_factor = 0.005,
  autovacuum_analyze_threshold = 500
);

-- For very large tables (> 5M rows)
ALTER TABLE <your_large_table> SET (
  autovacuum_vacuum_scale_factor = 0.005,
  autovacuum_vacuum_threshold = 1000
);

-- Verify the setting was applied
SELECT relname, reloptions
FROM pg_class
WHERE relname = 'stockadjustments';

Related Knowledge:  → K27: Autovacuum Scale Factor Trap for Large Tables
Related Pattern:    → P21: Per-Table Storage Hygiene
```

---

### TA14: REINDEX CONCURRENTLY Script (PostgreSQL)

```
Name:             REINDEX CONCURRENTLY — Non-Blocking Index Rebuild
Type:             Code Snippet
Language:         SQL / PostgreSQL
Usage:            Run after detecting index bloat > 30% (reusable / total pages).
                  Run one index at a time. Monitor via pg_stat_progress_create_index.
                  Does not lock the table — safe for production.
                  Requires PostgreSQL 12+.

-- Run each one at a time (not all in parallel)
REINDEX INDEX CONCURRENTLY stockadjustments_pkey;
REINDEX INDEX CONCURRENTLY stockadjustments_adjusted_at_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_sync_stock_seq_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_adjustment_type_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_product_id_idx;
REINDEX INDEX CONCURRENTLY stockadjustments_stock_id_idx;

-- Monitor progress (run in a separate session)
SELECT phase, blocks_done, blocks_total,
       ROUND(blocks_done::numeric / NULLIF(blocks_total, 0) * 100, 1) AS pct_complete
FROM pg_stat_progress_create_index
WHERE relid = 'stockadjustments'::regclass;

-- Verify sizes after (before: ~1.7 GB, after: 251 MB measured)
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE relname = 'stockadjustments'
ORDER BY pg_relation_size(indexrelid) DESC;

Related Knowledge:  → K26: PostgreSQL MVCC and Dead Tuples
Related Pattern:    → P21: Per-Table Storage Hygiene
Related Decision:   → D12: REINDEX CONCURRENTLY vs VACUUM FULL
```

---

### TA15: EF.CompileQuery Static Field Template

```
Name:             EF.CompileQuery Static Field Template
Type:             Code Snippet
Language:         C#
Stack:            .NET / EF Core 7.0+ (AsSplitQuery requires 7.0+)
Description:      Static compiled query template for hot-path EF Core queries with
                  Include chains. Eliminates DynamicMethod/DynamicILGenerator accumulation
                  in the EF CompiledQueryCache. Replace YourDbContext and entity/field names.
// Snippet:
// Step 1: Add static field at class level (compiled once on first call)
// Replace: YourDbContext, YourEntity, YourFilterField
private static readonly Func<YourDbContext, string[], string[], IEnumerable<YourEntity>>
    _bulkQuery = EF.CompileQuery(
        (YourDbContext ctx, string[] ids1, string[] ids2) =>
            ctx.YourEntities
               .AsNoTracking()
               .Include(e => e.NavigationA)
               .Include(e => e.NavigationB).ThenInclude(b => b.ChildC)
               // ... add all Include paths ...
               .AsSplitQuery()
               .Where(e => ids1.Contains(e.Field1) && ids2.Contains(e.Field2)));

// Step 2: Replace the inline query in the method body
var results = _bulkQuery(
    _context,
    listOfIds1.ToArray(),
    listOfIds2.ToArray()
).ToList();

// For async path: use EF.CompileAsyncQuery → returns IAsyncEnumerable<T>
private static readonly Func<YourDbContext, string[], string[], IAsyncEnumerable<YourEntity>>
    _bulkQueryAsync = EF.CompileAsyncQuery(
        (YourDbContext ctx, string[] ids1, string[] ids2) =>
            ctx.YourEntities.AsNoTracking()
               .Include(e => e.NavigationA)
               .AsSplitQuery()
               .Where(e => ids1.Contains(e.Field1)));

// Usage:
var results = new List<YourEntity>();
await foreach (var item in _bulkQueryAsync(_context, ids1.ToArray(), ids2.ToArray()))
    results.Add(item);

// Verify impact: dotnet-dump analyze <file.dmp>
// dumpheap -stat | grep DynamicMethod
// Expected: count drops to service-wide unique footprint (stable ceiling)
Related Knowledge:  → K28: EF Core Compiled Query Cache and DynamicMethod Accumulation
Related Pattern:    → P22: EF Compiled Query Cache Management
Related Decision:   → D13: Apply EF.CompileQuery to GetSubOrderMessage Bulk Query
```

---

### TA16: dotnet-dump Heap Analysis Workflow

```
Name:             dotnet-dump Heap Analysis Workflow
Type:             Runbook / Command Reference
Language:         bash / dotnet CLI
Stack:            .NET (any version)
Description:      Step-by-step commands to take a memory dump, run dumpheap -stat,
                  export to file, and interpret results. Covers both .dmp (full dump)
                  and .gcdump (GC-only) paths.
// Snippet:
# ── Capture dump ──────────────────────────────────────────────────────────────

# Option A: dotnet-dump (full memory dump — includes all heap detail)
dotnet tool install -g dotnet-dump
dotnet-dump collect -p <PID> -o ./Order.API-$(date +%s).dmp

# Option B: dotnet-gcdump (GC-only — lighter, heapstat only)
dotnet tool install -g dotnet-gcdump
dotnet-gcdump collect -p <PID> -o ./heap.gcdump
dotnet-gcdump report heap.gcdump --report-type HeapStat   # only valid report type

# ── Analyze .dmp file ─────────────────────────────────────────────────────────

# Interactive REPL
dotnet-dump analyze ./Order.API.dmp

# Inside REPL — key commands:
dumpheap -stat                          # all types sorted by total size (largest at bottom)
dumpheap -type DynamicMethod            # list all DynamicMethod instances with addresses
dumpheap -type SubOrderMessageViewModel # list domain entity instances
gcroot <address>                        # who is keeping object at <address> alive
exit

# ── Export heapstat to file (non-interactive) ─────────────────────────────────
# Windows:
echo dumpheap -stat | dotnet-dump analyze ./Order.API.dmp > heapstat.txt 2>&1

# ── Interpret output ──────────────────────────────────────────────────────────
# Read bottom-up (largest total size at bottom of file)
# Red flags: DynamicMethod > 2000, Free > 50% of heap, EF entity type > 1000 objects
# Healthy: DynamicMethod < 500, Free < 30%, domain objects proportional to active requests

# ── Compare two dumps (leak detection) ───────────────────────────────────────
# Dump 1: baseline (steady state)
# Dump 2: 10 min later at same load
# Compare DynamicMethod count:
#   delta ≈ 0   → stable ceiling (fix confirmed)
#   delta grows → unbounded growth → apply EF.CompileQuery
Related Knowledge:  → K29: .NET Heap Dump Analysis — Reading dumpheap -stat
                    → K28: EF Core Compiled Query Cache and DynamicMethod Accumulation
Related Pattern:    → P22: EF Compiled Query Cache Management
Related Decision:   → D13: Apply EF.CompileQuery to GetSubOrderMessage Bulk Query
```

---

