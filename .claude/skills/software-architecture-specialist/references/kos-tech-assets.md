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
Related Incidents:  → I1: GetSubOrder API Latency Spike
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
Related Incidents:  → I1: GetSubOrder API Latency Spike
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
Related Incidents:  → I1: GetSubOrder API Latency Spike
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
Related Incidents:  → I1: GetSubOrder API Latency Spike
```

---

### TA11: GetSubOrderAsync Coordinator + Map Functions (.NET / EF Core)

```
Name:             GetSubOrderAsync Coordinator + Map Functions
Type:             Code Snippet
Language:         C#
Usage:            Full async coordinator with parallel DB calls and pure in-memory map functions.
                  Core output of the GetSubOrder Phase 1–4 refactor (incident2.cs).

// Snippet:
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
Related Incidents:  → I1: GetSubOrder API Latency Spike
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

-- Snippet:
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
Related Incidents:  → I2: PostgreSQL Dead Tuple Bloat — stockadjustments
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

-- Snippet:
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
Related Incidents:  → I2: PostgreSQL Dead Tuple Bloat — stockadjustments
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

-- Snippet:
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
Related Incidents:  → I2: PostgreSQL Dead Tuple Bloat — stockadjustments
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
Related Incidents:  → I1: GetSubOrder API Latency Spike
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
Related Incidents:  → I1: GetSubOrder API Latency Spike
```

---

### TA17: TestDbContextFactory — IDbContextFactory\<T\> for xUnit

```
Name:             TestDbContextFactory — IDbContextFactory<T> for xUnit
Type:             Code Snippet
Language:         C#
Usage:            Use when the SUT accepts IDbContextFactory<OrderContext> and creates parallel
                  DbContext instances via CreateDbContext(). Each call returns a new context
                  over the same InMemory database — mirrors production lifetime without SQL Server.
                  Pair with UseInMemoryDatabase(Guid.NewGuid().ToString()) for test isolation.

Prerequisites:    Microsoft.EntityFrameworkCore.InMemory
                  Microsoft.EntityFrameworkCore (IDbContextFactory<T>)

// Snippet:
internal sealed class TestDbContextFactory : IDbContextFactory<OrderContext>
{
    private readonly DbContextOptions<OrderContext> _options;

    public TestDbContextFactory(DbContextOptions<OrderContext> options)
        => _options = options;

    public OrderContext CreateDbContext() => new OrderContext(_options);
}

// Setup in test constructor:
var dbOptions = new DbContextOptionsBuilder<OrderContext>()
    .UseInMemoryDatabase(Guid.NewGuid().ToString())   // unique per test class
    .Options;
var context = new OrderContext(dbOptions);
var factory = new TestDbContextFactory(dbOptions);
var sut     = new MyService(logger, context, factory);

// Why Guid per test: prevents state bleed when xUnit runs tests in parallel.
// All CreateDbContext() calls share the same named store — correct for testing
// Task.WhenAll patterns that open multiple contexts to the same logical DB.

Related Pattern:    → P16: Async Parallel DB Coordinator
Related Knowledge:  → K28: EF Core Compiled Query Cache and DynamicMethod Accumulation
Related Tech Asset: → TA18: xUnit Integration Test Skeleton — EF Core Service
```

---

### TA18: xUnit Integration Test Skeleton — EF Core Service with IDbContextFactory

```
Name:             xUnit Integration Test Skeleton — EF Core Service with IDbContextFactory
Type:             Pattern Implementation
Language:         C#
Usage:            Skeleton for testing any service that:
                    (a) nests repositories with `new Repo(_context)` (not injectable), AND
                    (b) uses IDbContextFactory<T> for parallel Task.WhenAll paths.
                  Fill in: [ServiceClass], namespace, model names, seed data, branch assertions.

NuGet packages:
  xunit
  xunit.runner.visualstudio
  Microsoft.NET.Test.Sdk
  Microsoft.EntityFrameworkCore.InMemory
  Moq

// Snippet:
public class MyMethodTests : IDisposable
{
    private const string OrderId    = "ORD-TEST-001";
    private const string SubOrderId = "SUB-TEST-001";

    private readonly DbContextOptions<OrderContext> _dbOptions;
    private readonly OrderContext                   _context;
    private readonly TestDbContextFactory           _factory;
    private readonly Mock<ILogger>                  _loggerMock;
    private readonly [ServiceClass]                 _sut;   // TODO: replace [ServiceClass]

    public MyMethodTests()
    {
        _dbOptions  = new DbContextOptionsBuilder<OrderContext>()
                          .UseInMemoryDatabase(Guid.NewGuid().ToString())
                          .Options;
        _context    = new OrderContext(_dbOptions);
        _factory    = new TestDbContextFactory(_dbOptions);
        _loggerMock = new Mock<ILogger>();
        _sut        = new [ServiceClass](_loggerMock.Object, _context, _factory);
    }

    public void Dispose() => _context.Dispose();

    // ── happy path ─────────────────────────────────────────────────────────────
    [Fact]
    public async Task MyMethod_ValidInput_ReturnsResultIntOne()
    {
        SeedOrder(OrderId);
        SeedSubOrder(OrderId, SubOrderId);
        var (result, _) = await _sut.MyMethod(OrderId, SubOrderId);
        Assert.Equal(1, result.ResultInt);
    }

    // ── exception path ─────────────────────────────────────────────────────────
    [Fact]
    public async Task MyMethod_MissingSubOrder_ReturnsResultIntNegativeTen()
    {
        SeedOrder(OrderId);
        // No SubOrder seeded intentionally
        var (result, _) = await _sut.MyMethod(OrderId, "NONEXISTENT");
        Assert.Equal(-10, result.ResultInt);
    }

    // ── no exception propagated ────────────────────────────────────────────────
    [Fact]
    public async Task MyMethod_EmptyDatabase_DoesNotThrow()
    {
        var ex = await Record.ExceptionAsync(() => _sut.MyMethod("GHOST", "GHOST"));
        Assert.Null(ex);
    }

    // ── deadlock guard ─────────────────────────────────────────────────────────
    [Fact]
    public async Task MyMethod_ParallelTasks_CompleteWithinTimeout()
    {
        SeedOrder(OrderId);
        SeedSubOrder(OrderId, SubOrderId);
        using var cts  = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var work       = _sut.MyMethod(OrderId, SubOrderId);
        var completed  = await Task.WhenAny(work, Task.Delay(Timeout.Infinite, cts.Token));
        Assert.Same(work, completed);
    }

    // ── seed helpers ───────────────────────────────────────────────────────────
    private void SeedOrder(string sourceOrderId, int id = 1, string orderNumber = "ON-001")
    {
        _context.Order.Add(new OrderModel          // TODO: verify model name
        {
            Id = id, SourceOrderId = sourceOrderId,
            IsActive = true, OrderNumber = orderNumber,
            Customer = new List<OrderCustomerModel>()  // TODO: verify nav model name
        });
        _context.SaveChanges();
    }

    private void SeedSubOrder(string sourceOrderId, string sourceSubOrderId, int itemCount = 1)
    {
        _context.SubOrder.Add(new SubOrderModel    // TODO: verify model name
        {
            SourceOrderId = sourceOrderId, SourceSubOrderid = sourceSubOrderId,
            IsActive = true,
            Addresses = new List<SubOrderAddressModel>(),  // TODO: verify
            Items     = Enumerable.Range(0, itemCount)
                            .Select(i => new SubOrderItemModel { SkuCode = $"SKU-{i}" })
                            .ToList()
        });
        _context.SaveChanges();
    }
}

// Note: If AsSplitQuery() throws with InMemory, switch to:
//   .UseSqlite("Filename=:memory:") + context.Database.EnsureCreated()

Related Pattern:    → P16: Async Parallel DB Coordinator
Related Tech Asset: → TA17: TestDbContextFactory — IDbContextFactory<T> for xUnit
Related Checklist:  → review-checklists.md: Checklist: Test Coverage (.NET / xUnit)
```

---

### TA19: C# EF Core Per-Batch Commit Template with Polly Timeout Policy

```
Name:             C# EF Core Per-Batch Commit Template with Polly Timeout Policy
Type:             Code Snippet
Language:         C#
Stack:            .NET 8, EF Core 8, Pomelo.EntityFrameworkCore.MySql, Polly v7+
Usage:            Drop-in replacement for ProcessSyncLoopAsync() that wraps a while(true) batch
                  loop with per-batch TX. Read batch BEFORE opening TX to minimize hold to
                  write-only duration (~200ms). Fill in GetProductStaging() / SyncProductMasterAsync()
                  with your types. CommandTimeout(120) on DbContext registration as a safety net.
Related Knowledge:  → K30
Related Pattern:    → P24, P25
Related Decisions:  → D16, D17
Related Incidents:  → I3, I4, I5, I6
Related Tech Assets:→ TA20 (observability instrumentation)

// Snippet:
long lastProcessedId = startingId;
int round = 1;

while (true)
{
    cancellationToken.ThrowIfCancellationRequested();

    // Read BEFORE TX — holds connection only for writes (~200ms vs full batch)
    var batch = await GetProductStaging(lastProcessedId, cancellationToken);
    if (batch.Count == 0) break;

    await batchPolicy.ExecuteAsync(async ct =>
    {
        await using var tx = await context.Database.BeginTransactionAsync(ct);
        try
        {
            await SyncProductMasterAsync(batch, activityTracking, ct);
            await tx.CommitAsync(ct);
            lastProcessedId = batch.Last().Id;
            logger.LogInformation("[{Sync}] Batch {Round}: {Count} records", SyncName, round, batch.Count);
            round++;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "[{Sync}] Batch {Round} FAILED", SyncName, round);
            try { await tx.RollbackAsync(ct); } catch { /* dead connection — swallow */ }
            throw;
        }
    }, cancellationToken);

    await stagingContext.SaveChangesAsync(cancellationToken);
}
```

#### Per-Batch Commit Loop

```csharp
protected override async Task<long> ProcessSyncLoopAsync(
    long startingId,
    Dictionary<string, ProductMasterActivity> productMasterActivityTracking,
    CancellationToken cancellationToken)
{
    var hasData = await CheckPendingAsync(startingId, cancellationToken);
    if (!hasData)
    {
        logger.LogWarning(Shared.LoggingHelper.MESSAGE_WITOUT_DATA_SYNC, SyncName, businessUnit);
        return startingId;
    }

    // Polly: retry transient DB errors per batch (exponential backoff: 2s, 4s, 8s)
    var retryPolicy = Policy
        .Handle<MySqlException>(ex => IsTransient(ex))
        .Or<TimeoutRejectedException>()
        .WaitAndRetryAsync(
            retryCount: 3,
            sleepDurationProvider: attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt)),
            onRetry: (ex, delay, attempt, _) =>
                logger.LogWarning(ex, "Batch {Round} retry {Attempt} after {Delay}s",
                    round, attempt, delay.TotalSeconds));

    // Polly: hard timeout per batch (60s ceiling)
    var timeoutPolicy = Policy.TimeoutAsync(60, TimeoutStrategy.Optimistic);
    var batchPolicy = Policy.WrapAsync(retryPolicy, timeoutPolicy);

    long lastProcessedId = startingId;
    int round = 1;

    while (true)
    {
        cancellationToken.ThrowIfCancellationRequested();

        // Read batch BEFORE opening TX — minimizes TX hold to write-only duration (~200ms)
        var productStagings = await GetProductStaging(lastProcessedId, cancellationToken);
        if (productStagings.Count == 0)
        {
            logger.LogInformation(LoggingHelper.MESSAGE_TRACKING_END_BATCH, SyncName);
            break;
        }

        await batchPolicy.ExecuteAsync(async ct =>
        {
            // Per-batch TX: hold time ≈ insert duration only (~200ms for 10K rows)
            await using var tx = await context.Database.BeginTransactionAsync(ct);
            try
            {
                await SyncProductMasterAsync(
                    productStagings, productMasterActivityTracking, ct);
                await tx.CommitAsync(ct);

                // Advance cursor AFTER commit — safe: if commit fails, cursor stays back
                lastProcessedId = productStagings.Last().Id;
                logger.LogInformation(
                    LoggingHelper.MESSAGE_TRACKING_PER_BATCH,
                    SyncName, round, productStagings.Count, lastProcessedId);
                round++;
            }
            catch (Exception ex)
            {
                logger.LogError(ex, Shared.LoggingHelper.MESSAGE_ROLLBACK, SyncName, businessUnit);
                try { await tx.RollbackAsync(ct); }
                catch (Exception rbEx)
                {
                    // Dead connection — rollback will also fail. Log and swallow.
                    logger.LogError(rbEx, "Rollback failed for batch {Round}", round);
                }
                throw; // rethrow for Polly retry
            }
        }, cancellationToken);

        // Persist staging state per-batch, after production commit
        await stagingContext.SaveChangesAsync(cancellationToken);
    }

    return lastProcessedId;
}

/// <summary>Transient MySQL error codes safe to retry.</summary>
private static bool IsTransient(MySqlException ex) => ex.Number is
    1205 or  // ER_LOCK_WAIT_TIMEOUT
    1213 or  // ER_LOCK_DEADLOCK
    2006 or  // CR_SERVER_GONE_ERROR
    2013;    // CR_SERVER_LOST
```

#### DbContext Registration — add CommandTimeout

```csharp
// Program.cs / DI setup
services.AddDbContext<DbSpcProductContext>(options =>
    options.UseMySql(
        connectionString,
        ServerVersion.AutoDetect(connectionString),
        o => o.CommandTimeout(120)));   // 2-min per-statement ceiling
```

#### Airflow DAG Fix — airflow.py

```python
from datetime import timedelta

# Inside run_dotnet_exe():
try:
    exit_code = result.wait(timeout=7200)   # 2h hard ceiling
except subprocess.TimeoutExpired:
    result.kill()
    raise Exception(".NET job exceeded maximum allowed runtime of 2 hours")

# In PythonOperator:
retries=2,
retry_delay=timedelta(minutes=5),
execution_timeout=timedelta(hours=3),
```

---

### TA20: ETL Batch Resource Tracking — Prometheus + Stopwatch + GC (.NET)

```
Name:             ETL Batch Resource Tracking — Prometheus + Stopwatch + GC
Type:             Code Snippet
Language:         C#
Stack:            .NET 8, Prometheus-net, EF Core 8
Usage:            Drop-in instrumentation for any ETL batch loop with DB writes. Tracks
                  TX hold time (Histogram), records (Counter), round (Gauge), GC alloc (Summary)
                  + structured log per batch. Always call ChangeTracker.Clear() + tracking
                  dict.Clear() after commit — prevents linear heap growth across batches.
                  Copy static field declarations (see below) + per-batch block into sync class.
Related Knowledge:  → K31, K32
Related Pattern:    → P25
Related Decisions:  → D17
Related Incidents:  → I3, I4, I5

// Snippet:
// ── Per-batch instrumentation block (inside while loop, after ReadBatch) ──
long gcBefore = GC.GetTotalAllocatedBytes(precise: false);
var batchSw   = Stopwatch.StartNew();
var readSw    = Stopwatch.StartNew();
var batch     = await GetProductStaging(lastId, cancellationToken);
readSw.Stop();
StagingReadDuration.WithLabels(labels).Observe(readSw.Elapsed.TotalSeconds);

if (batch.Count == 0) break;

await using var tx = await context.Database.BeginTransactionAsync(cancellationToken);
try
{
    await SyncProductMasterAsync(batch, activityTracking, cancellationToken);
    await tx.CommitAsync(cancellationToken);
    batchSw.Stop();

    BatchDuration.WithLabels(labels).Observe(batchSw.Elapsed.TotalSeconds);
    RecordsProcessed.WithLabels(labels).Inc(batch.Count);
    CurrentBatchRound.WithLabels(labels).Set(round);
    BatchMemoryAlloc.WithLabels(labels).Observe(GC.GetTotalAllocatedBytes(precise: false) - gcBefore);

    // Prevent linear heap growth — detach committed entities + clear tracking dict
    context.ChangeTracker.Clear();
    activityTracking.Clear();

    logger.LogInformation(
        "[{SyncName}] Batch {Round}: {Count} records, TX {TxMs}ms, read {ReadMs}ms",
        SyncName, round, batch.Count, batchSw.ElapsedMilliseconds, readSw.ElapsedMilliseconds);
    round++;
}
catch (Exception ex)
{
    batchSw.Stop();
    logger.LogError(ex, "[{SyncName}] Batch {Round} FAILED after {TxMs}ms", SyncName, round, batchSw.ElapsedMilliseconds);
    try { await tx.RollbackAsync(cancellationToken); } catch { }
    throw;
}
```

#### Static Prometheus Field Declarations

```csharp
// Add to sync class — static fields, one per metric
private static readonly Histogram BatchDuration = Metrics
    .CreateHistogram("etl_sync_batch_duration_seconds",
        "Per-batch TX hold time (staging read excluded)",
        new HistogramConfiguration
        {
            Buckets = Histogram.ExponentialBuckets(0.1, 2, 10), // 0.1s → 51.2s
            LabelNames = new[] { "sync_name", "business_unit" }
        });

private static readonly Counter RecordsProcessed = Metrics
    .CreateCounter("etl_sync_records_processed_total",
        "Cumulative records committed",
        new CounterConfiguration { LabelNames = new[] { "sync_name", "business_unit" } });

private static readonly Gauge CurrentBatchRound = Metrics
    .CreateGauge("etl_sync_current_batch_round",
        "Current batch round number (resets per job run)",
        new GaugeConfiguration { LabelNames = new[] { "sync_name", "business_unit" } });

private static readonly Histogram StagingReadDuration = Metrics
    .CreateHistogram("etl_sync_staging_read_seconds",
        "Per-batch staging read duration",
        new HistogramConfiguration
        {
            Buckets = Histogram.ExponentialBuckets(0.05, 2, 8), // 50ms → 6.4s
            LabelNames = new[] { "sync_name", "business_unit" }
        });

private static readonly Summary BatchMemoryAlloc = Metrics
    .CreateSummary("etl_sync_batch_alloc_bytes",
        "GC allocation per batch",
        new SummaryConfiguration { LabelNames = new[] { "sync_name", "business_unit" } });
```

#### Per-Batch Instrumentation Block (inside while loop)

```csharp
var labels = new[] { SyncName, businessUnit.ToString() };

// ── Track staging read ──
var readSw = Stopwatch.StartNew();
var productStagings = await GetProductStaging(lastIdFromStaging, cancellationToken);
readSw.Stop();
StagingReadDuration.WithLabels(labels).Observe(readSw.Elapsed.TotalSeconds);

if (productStagings.Count == 0) break;

// ── Track per-batch TX hold + memory ──
long gcBefore = GC.GetTotalAllocatedBytes(precise: false);
var batchSw = Stopwatch.StartNew();

await using var tx = await context.Database.BeginTransactionAsync(cancellationToken);
try
{
    await SyncProductMasterAsync(productStagings, productMasterActivityTracking, cancellationToken);
    await tx.CommitAsync(cancellationToken);

    batchSw.Stop();
    long gcAfter = GC.GetTotalAllocatedBytes(precise: false);

    // ── Record metrics ──
    BatchDuration.WithLabels(labels).Observe(batchSw.Elapsed.TotalSeconds);
    RecordsProcessed.WithLabels(labels).Inc(productStagings.Count);
    CurrentBatchRound.WithLabels(labels).Set(round);
    BatchMemoryAlloc.WithLabels(labels).Observe(gcAfter - gcBefore);

    logger.LogInformation(
        "[{SyncName}] Batch {Round}: {Count} records, TX hold {TxHoldMs}ms, "
        + "staging read {ReadMs}ms, alloc {AllocMB:F1}MB, total {Total}, elapsed {JobSec:F0}s",
        SyncName, round, productStagings.Count,
        batchSw.ElapsedMilliseconds, readSw.ElapsedMilliseconds,
        (gcAfter - gcBefore) / 1_048_576.0,
        totalRecordsProcessed, jobStopwatch.Elapsed.TotalSeconds);
    round++;
}
catch (Exception ex)
{
    batchSw.Stop();
    logger.LogError(ex,
        "[{SyncName}] Batch {Round} FAILED after {TxHoldMs}ms — total committed: {Total}",
        SyncName, round, batchSw.ElapsedMilliseconds, totalRecordsProcessed);
    try { await tx.RollbackAsync(cancellationToken); }
    catch (Exception rbEx)
    {
        logger.LogError(rbEx, "Rollback failed for batch {Round}", round);
    }
    throw;
}
```

#### Job Summary Log (after while loop)

```csharp
jobStopwatch.Stop();
logger.LogInformation(
    "[{SyncName}] Job complete: {Total} records in {Rounds} batches, "
    + "{JobSec:F1}s total, avg {AvgMs:F0}ms/batch",
    SyncName, totalRecordsProcessed, round - 1,
    jobStopwatch.Elapsed.TotalSeconds,
    round > 1 ? jobStopwatch.Elapsed.TotalMilliseconds / (round - 1) : 0);
```

---


### TA21: Airflow PythonOperator — Subprocess Kill on Task Termination

```
Name:             Airflow PythonOperator Subprocess Kill Pattern
Type:             Code Snippet
Language:         Python
Stack:            Apache Airflow 2.x, subprocess.Popen
Usage:            Guarantees the child .NET process (or any subprocess) is killed when Airflow
                  terminates the Python callable via execution_timeout, worker shutdown, or
                  task cancellation. Without this, the subprocess runs as an orphan indefinitely.
                  Wrap the Popen streaming loop in try/finally — the finally block always runs.
Related Knowledge:  → K30
Related Incidents:  → I3, I4, I5

# Snippet:
def run_dotnet_exe():
    proc = subprocess.Popen([...], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        for line in proc.stdout:
            print(line, end="")
        exit_code = proc.wait()
        if exit_code != 0:
            raise Exception(f".NET job failed with exit code {exit_code}")
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        if proc.poll() is None:   # safety net — always kills on any exit
            proc.kill()
            proc.wait()
```

#### Pattern

```python
def run_dotnet_exe():
    proc = subprocess.Popen(
        ["dotnet", f"{app_path}/ETLCronjob.dll", "--process-type=" + process_type],
        cwd=app_path, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    try:
        print("=== .Net Logging Start ===")
        for line in proc.stdout:
            print(line, end="")           # streams live to Airflow task logs
        print("=== .Net Logging End ===")

        exit_code = proc.wait()
        if exit_code != 0:
            raise Exception(f".NET job failed with exit code {exit_code}")
    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()                   # reap zombie to free PID
        raise
    finally:
        if proc.poll() is None:           # safety net
            proc.kill()
            proc.wait()
```

#### Why `result.wait(timeout=7200)` after the streaming loop is dead code

```
for line in result.stdout:   ← blocks until stdout exhausted (process already exited)
    print(line)
result.wait(timeout=7200)    ← process is dead, timeout never fires
```

Real timeout guard = `execution_timeout=timedelta(hours=3)` on PythonOperator.
try/finally ensures subprocess is killed when that timeout fires.

---

### TA22: ETL Clone Verification Diff — SyncProduct*Jda Touch Points

```
Name:             ETL Clone Verification Diff — SyncProduct*Jda Touch Points
Type:             Code Review Checklist / Copy-Paste Safety
Language:         C# / .NET
Related Incidents:   → I6
Related Knowledge:   → K33
Related Patterns:    → P26
Related Decisions:   → D18
Date:             2026-04-08

// Snippet:
// TOUCH POINT 1 — Class name
// public sealed class SyncProductBarcodeJda(...)  ← update class name

// TOUCH POINT 2 — Staging DbSet in GetProductStaging()
// stagingContext.SpcJdaBarcodeStaging  ← MUST update

// TOUCH POINT 3 — Staging DbSet in CheckPendingAsync()  ← MOST COMMONLY MISSED
// stagingContext.SpcJdaBarcodeStaging.AnyAsync(x => x.Id > lastId, ...)

// TOUCH POINT 4 — serviceType property
// protected override string serviceType => "JdaProductBarcode";

// TOUCH POINT 5 — SyncName / tracker key
// SyncName = "SyncProductBarcodeJda"

// TOUCH POINT 6 — BatchSize config value (re-run BotE if write volume differs)
// tx_hold = (batch_size/10K) x 14s < 25s
```

Use this as a PR diff checklist when creating a new SyncProduct*Jda service by cloning
an existing one. All 6 touch points must be updated independently.

```csharp
// ── CLONE VERIFICATION: 6 touch points, verify each independently ──────────────────

// TOUCH POINT 1 — Class name (constructor)
// Source:  public sealed class SyncProductMasterJda(...)
// Clone:   public sealed class SyncProductBarcodeJda(...)  ← update class name

// TOUCH POINT 2 — Staging DbSet in GetProductStaging()
// Source:  stagingContext.SpcJdaProductStaging
// Clone:   stagingContext.SpcJdaBarcodeStaging  ← MUST update — independent from TP3!

// TOUCH POINT 3 — Staging DbSet in CheckPendingAsync()
// Source:  stagingContext.SpcJdaProductStaging.AnyAsync(x => x.Id > lastId, ...)
// Clone:   stagingContext.SpcJdaBarcodeStaging.AnyAsync(x => x.Id > lastId, ...)
//          ↑ MOST COMMONLY MISSED — compiler does NOT catch wrong table reference

// TOUCH POINT 4 — serviceType property
// Source:  protected override string serviceType => "JdaProductMaster";
// Clone:   protected override string serviceType => "JdaProductBarcode";

// TOUCH POINT 5 — SyncName / tracker key (used in DB and logs)
// Source:  SyncName = "SyncProductMasterJda"  (defined in abstract base)
// Clone:   SyncName = "SyncProductBarcodeJda"  ← check base class or override

// TOUCH POINT 6 — BatchSize config value
// Source:  BatchSize = 10000  (appsettings.json)
// Clone:   verify same 10K ceiling applies for new workload
//          if write volume differs, re-run BotE: tx_hold = (batch_size/10K) x 14s < 25s
```

#### Post-Clone Grep Verification (run before merging)

```bash
# Replace SyncProductBarcodeJda with your new file name
CLONE_FILE="SyncProductBarcodeJda.cs"
SOURCE_DBSET="SpcJdaProductStaging"

echo "=== Checking for unreplaced copy-paste DbSet references ==="
grep -n "$SOURCE_DBSET" "$CLONE_FILE" && echo "BUG: wrong DbSet reference found!" || echo "PASS"

SOURCE_SYNCNAME="SyncProductMasterJda"
echo "=== Checking for unreplaced SyncName ==="
grep -n "$SOURCE_SYNCNAME" "$CLONE_FILE" && echo "BUG: old SyncName found!" || echo "PASS"
```

Expected output: both checks return `PASS`. Any `BUG:` line = fix before merge.



---

### TA23: Airflow DAG Local Debug Runner Template

```
Name:       Airflow DAG Local Debug Runner Template
Type:       Python template
Language:   Python
Stack:      Airflow, pymysql, SQLAlchemy, pandas
Tags:       airflow, debug, local, stub, mysql, xcom, dag_run
Related:    I7, K34, P27, D19
```

Reusable template for running Airflow DAG tasks locally in VS Code debugpy without an Airflow installation.
Covers two variants: **parent DAG** (XCom via MockTaskInstance) and **child DAG** (dag_run.conf via MockDagRun).

#### Variant A — Parent DAG debug runner

```python
# Snippet: ds_outbound_order/debug_runner.py
from __future__ import annotations
import os, sys, types

# 1. Stub all airflow.* modules before importing the DAG
_AIRFLOW_MODS = [
    "airflow", "airflow.models", "airflow.models.dag", "airflow.models.variable",
    "airflow.operators", "airflow.operators.python", "airflow.operators.trigger_dagrun",
    "airflow.hooks", "airflow.hooks.base",
    "airflow.providers", "airflow.providers.mysql", "airflow.providers.mysql.hooks",
    "airflow.providers.mysql.hooks.mysql",
    "pendulum",
]
for mod in _AIRFLOW_MODS:
    sys.modules[mod] = types.ModuleType(mod)

import pymysql
import pandas as pd
from sqlalchemy import create_engine

# 2. Connection registry (mirrors Airflow connection store)
CONNECTIONS = {
    'spc_mysql_ds': {
        'host': os.environ.get('SPC_DS_HOST', 'localhost'),
        'port': int(os.environ.get('SPC_DS_PORT', 3306)),
        'user': os.environ.get('SPC_DS_USER', 'root'),
        'password': os.environ.get('SPC_DS_PASSWORD', ''),
        'database': os.environ.get('SPC_DS_DB', 'spc_ds'),
    },
}

# 3. MySqlHook replacement
class _RealMySqlHook:
    def __init__(self, mysql_conn_id='default'):
        self._cfg = CONNECTIONS[mysql_conn_id]

    def _connect(self):
        return pymysql.connect(**self._cfg, charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)

    def get_first(self, sql, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
                row = cur.fetchone()
                return tuple(row.values()) if row else None

    def get_pandas_df(self, sql, parameters=None):
        with self._connect() as conn:
            return pd.read_sql(sql, conn, params=parameters)

    def run(self, sql, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
            conn.commit()

    def get_sqlalchemy_engine(self):
        cfg = self._cfg
        url = (f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
               f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4")
        return create_engine(url, future=True)  # future=True -> SQLAlchemy 2.x API on 1.4.x

# 4. Patch stubs
sys.modules['airflow.providers.mysql.hooks.mysql'].MySqlHook = _RealMySqlHook

class _MockVariable:
    @staticmethod
    def get(key, default_var=None): return default_var
sys.modules['airflow.models.variable'].Variable = _MockVariable

class _MockTaskInstance:
    def xcom_push(self, key, value): print(f"  XCOM PUSH  {key} = {value!r}")
    def xcom_pull(self, task_ids=None, key=None): return None

# 5. Import and run the task function
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_outbound_order import ds_inc_outbound_order_etl_data

ds_inc_outbound_order_etl_data(ti=_MockTaskInstance())
```

#### Variant B — Child DAG debug runner (dag_run.conf)

```python
# Snippet: ds_outbound_order/net/debug_runner.py
from __future__ import annotations
import os, sys, types

_AIRFLOW_MODS = [
    "airflow", "airflow.models", "airflow.models.dag", "airflow.models.variable",
    "airflow.operators", "airflow.operators.python", "airflow.operators.trigger_dagrun",
    "airflow.hooks", "airflow.hooks.base",
    "airflow.providers", "airflow.providers.mysql", "airflow.providers.mysql.hooks",
    "airflow.providers.mysql.hooks.mysql",
]
for mod in _AIRFLOW_MODS:
    sys.modules[mod] = types.ModuleType(mod)

import pymysql
import subprocess

# Simulate TriggerDagRunOperator-resolved conf.
# In production, XCom is resolved before child DAG receives conf.
MOCK_CONF = {
    'parent_dag_id':                'ds_inc_outbound_order',
    'parent_run_id':                'manual__2026-04-21T00:00:00',
    'dih_batch_id':                 '12345',
    'total_outbound_order_success': '10',
    'owner_id':                     'CDS-CDS',
}

SKIP_DOTNET = True   # set False to actually run the .NET app

DB_CONNECTIONS = {
    'spc_order_mysql': {'host': os.environ.get('SPC_ORDER_HOST', 'localhost'),
                        'schema': os.environ.get('SPC_ORDER_DB', 'spc_order'),
                        'login': os.environ.get('SPC_ORDER_USER', 'root'),
                        'password': os.environ.get('SPC_ORDER_PASSWORD', '')},
    'spc_mysql_ds':    {'host': os.environ.get('SPC_DS_HOST', 'localhost'),
                        'schema': os.environ.get('SPC_DS_DB', 'spc_ds'),
                        'login': os.environ.get('SPC_DS_USER', 'root'),
                        'password': os.environ.get('SPC_DS_PASSWORD', '')},
}
MYSQL_CONNECTIONS = {
    'spc_mysql_ds': {'host': os.environ.get('SPC_DS_HOST', 'localhost'),
                     'port': int(os.environ.get('SPC_DS_PORT', 3306)),
                     'user': os.environ.get('SPC_DS_USER', 'root'),
                     'password': os.environ.get('SPC_DS_PASSWORD', ''),
                     'database': os.environ.get('SPC_DS_DB', 'spc_ds')},
}

class _FakeConn:
    def __init__(self, cfg):
        self.host = cfg['host']; self.schema = cfg['schema']
        self.login = cfg['login']; self.password = cfg['password']

class _MockBaseHook:
    @staticmethod
    def get_connection(conn_id): return _FakeConn(DB_CONNECTIONS[conn_id])
sys.modules['airflow.hooks.base'].BaseHook = _MockBaseHook

class _RealMySqlHook:
    def __init__(self, mysql_conn_id='default'):
        self._cfg = MYSQL_CONNECTIONS[mysql_conn_id]
    def _connect(self):
        return pymysql.connect(**self._cfg, charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)
    def get_first(self, sql, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
                row = cur.fetchone()
                return tuple(row.values()) if row else None
    def run(self, sql, parameters=None):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parameters)
            conn.commit()
sys.modules['airflow.providers.mysql.hooks.mysql'].MySqlHook = _RealMySqlHook

if SKIP_DOTNET:
    def _stub_popen(cmd, **kwargs):
        print(f"[STUB] subprocess.Popen skipped: {cmd}")
        class _FakeProc:
            stdout = iter(["[STUB] dotnet output\n"])
            def wait(self): return 0
            def poll(self): return 0
            def kill(self): pass
        return _FakeProc()
    subprocess.Popen = _stub_popen

class _MockVariable:
    @staticmethod
    def get(key, default_var=None): return default_var
sys.modules['airflow.models.variable'].Variable = _MockVariable

class _MockDagRun:
    def __init__(self, conf): self.conf = conf; self.dag_id = 'debug'; self.run_id = 'debug_run'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_spc_order_outbound_jda_staging_to_spc import run_dotnet_exe

run_dotnet_exe(dag_run=_MockDagRun(MOCK_CONF))
```

#### launch.json entries

```json
// Snippet: .vscode/launch.json — PYTHONIOENCODING=utf-8 fixes Windows Thai locale (cp874) in debugpy
{
    "name": "Debug ds_outbound_order DAG",
    "type": "debugpy", "request": "launch",
    "program": "${workspaceFolder}/ds_outbound_order/debug_runner.py",
    "console": "integratedTerminal", "stopOnEntry": false, "justMyCode": false,
    "env": {
        "PYTHONIOENCODING": "utf-8",
        "SPC_DS_HOST": "localhost", "SPC_DS_PORT": "3306",
        "SPC_DS_USER": "root", "SPC_DS_PASSWORD": "", "SPC_DS_DB": "spc_ds"
    }
}
```

**When to reuse:** Any Airflow DAG that needs local F5 debugging. Adapt `CONNECTIONS`/`MOCK_CONF` per DAG. Set `SKIP_DOTNET=True` to stub out external process calls during development.

---

### TA24: OrderJda Two-Pass Per-Batch Commit Template (.NET EF Core)

```
Name:        OrderJda Two-Pass Per-Batch Commit Template
Type:        Code Snippet
Language:    C#
Stack:       .NET 8, EF Core 8, PostgreSQL
Usage:       Two-pass per-batch commit for EF Core ETL where child entities FK on a DB-generated
             parent ID (IDENTITY/SEQUENCE). Pass 1: save headers → EF populates headerActivity.Id.
             Pass 2: batch all item activities using now-real parent IDs → one save.
             Total: 2 SaveChangesAsync per batch regardless of batch_size.
             Copy into SyncXxx concrete class. Replace OrderOutbound* types with your entities.
Related Knowledge:   → K35: Two-Pass EF Core Batch Pattern for FK-Dependent Inserts
Related Pattern:     → P28: Two-Pass Batch Commit
Related Decision:    → D20: ETL Transaction Scope — Per-Batch vs Single TX for PostgreSQL
Related Incident:    → I8: OrderJda ETL — N+1 SELECT + SaveChanges-in-Loop

// Snippet:
// Pass 1: collect all headers, save once → DB generates headerActivity.Id
var headerState = new Dictionary<string, (OrderOutboundActivityTb Activity, OrderOutboundTb Order)>();
foreach (var header in orderHeaders)
{
    context.OrderOutboundActivityTb.Add(headerActivity);
    context.OrderOutboundTb.Add(order);
    headerState[header.OrderNo] = (headerActivity, order);
}
await context.SaveChangesAsync(ct);  // ← headerActivity.Id now a real DB value

// Pass 2: collect all children using populated parent IDs, save once
var activityTracking = new Dictionary<string, OrderOutboundItemActivityTb>();
foreach (var header in orderHeaders)
{
    if (!headerState.TryGetValue(header.OrderNo, out var state)) continue;
    CollectOrderActivities(stagings, header, activityTracking, state.Order, orderItems, state.Activity);
}
context.OrderOutboundItemActivityTb.AddRange(activityTracking.Values);
ApplyItemMasterChanges(context, headerState, itemMasterDict);
await context.SaveChangesAsync(ct);  // ← all items + master changes in one save

await tx.CommitAsync(ct);
await orderSyncTrackerService.CheckpointAsync(tracker, lastProcessedId, ct);
activityTracking.Clear();
```

**Full template** (outer loop + metrics + TX) — see below.

```csharp
// ─── Outer loop setup ──────────────────────────────────────────────────────
var batchId = Environment.GetEnvironmentVariable("ETLNETJOB_DIH_BATCH_ID");
int round = 1;
var syncTag = new KeyValuePair<string, object?>("sync_name", SyncName);

while (true)
{
    cancellationToken.ThrowIfCancellationRequested();

    var orderHeaders = await GetOrderHeaderAsync(lastProcessedId, batchId, cancellationToken);
    if (orderHeaders.Count == 0) { logger.LogInformation("...end batch"); break; }

    var batchSw = Stopwatch.StartNew();

    // ── Pre-materialize master lookups (2 queries, no N+1) ──────────────────
    HashSet<string> orderNos = new(orderHeaders.Select(x => x.OrderNo));
    var headerMasterDict = await context.OrderOutboundTb
        .Where(x => orderNos.Contains(x.OrderNo))
        .ToDictionaryAsync(x => x.OrderNo, cancellationToken);
    var itemMasterDict = await context.OrderOutboundItemTb
        .Where(x => orderNos.Contains(x.OrderNo))
        .GroupBy(x => x.OrderNo)
        .ToDictionaryAsync(x => x.Key, x => x.ToList(), cancellationToken);

    var stagingAllOrders = await GetDataStaging(orderHeaders, cancellationToken);
    var stagingByKey = stagingAllOrders
        .GroupBy(x => (x.OrderNo, x.JdaBatchId, x.DihBatchId))
        .ToDictionary(x => x.Key, x => x.OrderBy(y => y.Id).ToList());

    await using var tx = await context.Database.BeginTransactionAsync(cancellationToken);
    try
    {
        // ── Pass 1: parents → save once to get DB-generated IDs ─────────────
        var headerState = new Dictionary<string, (OrderOutboundActivityTb Activity, OrderOutboundTb Order)>();
        foreach (var header in orderHeaders)
        {
            var stagings = stagingByKey.TryGetValue((header.OrderNo, header.JdaBatchId, header.DihBatchId), out var s) ? s : [];
            // ... determine action, create activity + order master ...
            context.OrderOutboundActivityTb.Add(headerActivity);
            headerState[header.OrderNo] = (headerActivity, order);
        }
        var dbSw = Stopwatch.StartNew();
        await context.SaveChangesAsync(cancellationToken);  // ← Pass 1: headerActivity.Id populated
        metrics.DbWriteDurationMs.Record(dbSw.Elapsed.TotalMilliseconds, syncTag, new("pass", 1));

        // ── Pass 2: children (uses headerActivity.Id from Pass 1) ───────────
        var activityTracking = new Dictionary<string, OrderOutboundItemActivityTb>();
        foreach (var header in orderHeaders)
        {
            if (!headerState.TryGetValue(header.OrderNo, out var state)) continue;
            var stagings = stagingByKey.TryGetValue((header.OrderNo, header.JdaBatchId, header.DihBatchId), out var s) ? s : [];
            var orderItems = itemMasterDict.TryGetValue(header.OrderNo, out var items) ? items : [];
            CollectOrderActivities(stagings, header, activityTracking, state.Order, orderItems, state.Activity);
        }
        if (activityTracking.Count > 0)
        {
            StageItemInserts(activityTracking.Values.ToList());
            var activitiesByOrderNo = activityTracking.Values.GroupBy(x => x.OrderNo)
                .ToDictionary(x => x.Key, x => x.ToList());
            foreach (var (orderNo, acts) in activitiesByOrderNo)
            {
                if (!headerState.TryGetValue(orderNo, out var state)) continue;
                var orderItems = itemMasterDict.TryGetValue(orderNo, out var items) ? items : [];
                var (ins, upd, del) = orderBulkService.ApplyActivities(acts, orderItems, state.Order);
                totalInsert += ins; totalUpdate += upd; totalDelete += del;
            }
            activityTracking.Clear();
        }
        dbSw = Stopwatch.StartNew();
        await context.SaveChangesAsync(cancellationToken);  // ← Pass 2: all items in one save
        metrics.DbWriteDurationMs.Record(dbSw.Elapsed.TotalMilliseconds, syncTag, new("pass", 2));

        lastProcessedId = orderHeaders.Last().Id;
        await tx.CommitAsync(cancellationToken);

        // ── Checkpoint after commit (Airflow restart safety) ────────────────
        await orderSyncTrackerService.CheckpointAsync(tracker, lastProcessedId, cancellationToken);

        batchSw.Stop();
        metrics.BatchDurationMs.Record(batchSw.Elapsed.TotalMilliseconds, syncTag, new("round", round));
        metrics.RecordsProcessed.Add(orderHeaders.Count, syncTag);
        metrics.Inserts.Add(totalInsert, syncTag);
        metrics.Updates.Add(totalUpdate, syncTag);
        metrics.Deletes.Add(totalDelete, syncTag);
        round++;
    }
    catch (Exception ex)
    {
        logger.LogError(ex, "...", SyncName);
        await tx.RollbackAsync(cancellationToken);
        metrics.Errors.Add(1, syncTag);
        throw;
    }
}

---

### TA25: Airflow PythonOperator — Thread-Based Subprocess with Hard Timeout

```
Name:             Airflow PythonOperator — Thread-Based Subprocess with Hard Timeout
Type:             Code Snippet
Language:         Python
Stack:            Apache Airflow 2.x, subprocess.Popen, threading
Usage:            Use when PythonOperator calls a long-running subprocess (dotnet, java, binary),
                  live stdout streaming to Airflow logs is required, AND a hard wall-clock kill
                  is needed before Airflow's execution_timeout fires.
                  Set TIMEOUT_SUBPROCESS = execution_timeout_seconds - 120 (2-min buffer).
                  daemon=True on the stream thread means no cleanup needed when main thread exits.
                  proc.wait(timeout=N) in a nested try catches subprocess.TimeoutExpired before
                  the outer except Exception swallows it.
Related Knowledge:   → K36: Python sys.path — Nested Package Resolution
Related Incident:    → I9: Airflow DAG — Dead subprocess.TimeoutExpired Branch
Related Pattern:     → P29: Subprocess Timeout via Daemon Thread + proc.wait
Related Decision:    → D21: Airflow Subprocess Hard Kill — Thread Model vs communicate

# Snippet:
TIMEOUT_EXTRACT    = timedelta(minutes=30)
TIMEOUT_SUBPROCESS = int(TIMEOUT_EXTRACT.total_seconds()) - 120  # 28-min hard kill; 2-min buffer

def run_subprocess_with_timeout(cmd, cwd, env):
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    def _stream_output():
        for line in proc.stdout:
            print(line, end="")

    stream_thread = threading.Thread(target=_stream_output, daemon=True)

    try:
        print("=== Subprocess Logging Start ===")
        stream_thread.start()

        try:
            proc.wait(timeout=TIMEOUT_SUBPROCESS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise Exception(
                f"Subprocess exceeded {TIMEOUT_SUBPROCESS // 60}-minute hard limit and was killed"
            )

        stream_thread.join(timeout=5)
        print("=== Subprocess Logging End ===")

        exit_code = proc.returncode
        print("Exit code:", exit_code)
        if exit_code != 0:
            raise Exception(f"Subprocess failed with exit code {exit_code}")

    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
```

