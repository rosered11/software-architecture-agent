# 🔍 Code Review Checklists

> Read this file automatically whenever Code Review mode is triggered —
> i.e. when the user pastes code and asks for a review, says "review this",
> "is this good?", "what's wrong with this?", or shares a PR/method for feedback.
>
> Run ALL checklists that match the code's technology. Do not skip items.
> Report every finding — do not silently pass items that are ambiguous.

---

## How to Run a Review

1. **Identify technologies** present in the pasted code (EF Core, Kafka, Go, PostgreSQL, API endpoint, ETL)
2. **Run every matching checklist** — code often spans multiple (e.g. EF Core + API endpoint)
3. **Output findings** grouped by severity, then a summary score
4. **For every BLOCK or WARN**: show the exact line/pattern, explain the risk, provide the fix

### Output Format

```
🔍 Mode: Code Review
Technologies detected: [list]
Checklists run: [list]

--- FINDINGS ---

🚨 BLOCK  — [Finding title]
   Line/pattern: [exact code]
   Risk: [what goes wrong and when]
   Fix: [concrete corrected code]

⚠️  WARN   — [Finding title]
   Line/pattern: [exact code]
   Risk: [what could go wrong]
   Fix / Consider: [recommendation]

💡 SUGGEST — [Finding title]
   Line/pattern: [exact code]
   Why: [architectural improvement]
   Option: [how to do it better]

--- SUMMARY ---
Score:   [PASS / PASS WITH WARNINGS / BLOCK]
Blocks:  [count]
Warns:   [count]
Suggests:[count]

Architectural lesson: [1 sentence — what pattern or rule this review reinforces]
KOS action: [Should a new Incident / Knowledge / Pattern / Tech Asset be created? Which one?]
```

---

## Severity Definitions

| Severity | Meaning | Merge decision |
|----------|---------|----------------|
| 🚨 BLOCK | Will cause a production incident at scale | Do not merge |
| ⚠️ WARN | May cause a problem under load or edge case | Merge only with explicit acknowledgment |
| 💡 SUGGEST | Architectural improvement worth doing | Merge OK, create a follow-up task |

---

## Checklist: EF Core / .NET Data Access

Run when: code uses `_context`, `DbSet`, `Include()`, `.Load()`, LINQ queries, or Entity Framework.

```
BLOCK — DB call inside a loop
  Pattern: foreach/for loop containing _context.*, .Load(), .FirstOrDefault(), .Where()
  Risk: N+1 queries — latency = O(n) × DB roundtrip. Invisible at 5 rows, incident at 500.
  Fix: Collect IDs → batch WHERE id IN (...) → Dictionary<id,entity> lookup

BLOCK — .Entry().Reference().Load() or .Entry().Collection().Load() inside a loop
  Pattern: _context.Entry(x).Reference(p => p.Y).Load() inside foreach
  Risk: Each call = 1 DB roundtrip. EF Core does NOT batch these automatically.
  Fix: Replace with batch query + dictionary (see Tech Asset: Batch IN query snippet)

BLOCK — Any() followed by FirstOrDefault() on the same table
  Pattern: if (_context.X.Where(w => ...).Any()) { return _context.X.Where(w => ...).FirstOrDefault(); }
  Risk: Two queries where one is enough. Doubles DB load on every call.
  Fix: Remove the Any() check — FirstOrDefault() returns null if not found.

BLOCK — Missing AsNoTracking() on read-only queries
  Pattern: GET endpoint or read-only method using _context without .AsNoTracking()
  Risk: EF change tracker allocates memory and CPU for every tracked entity.
       Unnecessary on reads — adds overhead with zero benefit.
  Fix: Add .AsNoTracking() to all GET queries.

WARN — Include() with 2+ collections without AsSplitQuery()
  Pattern: .Include(x => x.CollectionA).Include(x => x.CollectionB) without .AsSplitQuery()
  Risk: Cartesian explosion — result rows = CollectionA.Count × CollectionB.Count
  Fix: Add .AsSplitQuery() when including 2 or more collection navigations.

WARN — Loading full entity when only a few fields are needed
  Pattern: returning or mapping full entity model when only 2–3 fields are used
  Risk: Over-fetching — unnecessary columns transferred and tracked
  Fix: Add .Select(x => new Dto { ... }) projection

WARN — Missing null check after FirstOrDefault()
  Pattern: var x = _context.X.FirstOrDefault(); x.Property (no null check)
  Risk: NullReferenceException in production when record doesn't exist
  Fix: Check for null before accessing properties, or use null-conditional operator

SUGGEST — Synchronous DB calls in async context
  Pattern: .FirstOrDefault() or .ToList() instead of .FirstOrDefaultAsync() / .ToListAsync()
  Why: Blocks the thread pool under concurrent load
  Option: Use async variants consistently throughout the call chain

BLOCK — Same reference resolver called 2+ times for same ID in one request
  Pattern: Multiple sibling methods each calling IsExistOrderReference() or similar lookup
    for the same SourceOrderId within one parent method
  Risk: Each call fires 2-3 queries independently — pure redundancy that compounds under concurrency.
  Fix: Resolve once at the coordinator (parent method), pass resolved ID to sub-calls.
  See: kos-patterns.md #12 Coordinator-Level Resolution
  Real example (target.cs:55-57): GetOrderHeader, GetOrderMessagePayments, GetOrderPromotion
    each call IsExistOrderReference independently = 6-9 redundant queries per request.

SUGGEST — Magic string comparisons on OrderId / SubOrderId
  Pattern: .Where(w => w.SourceOrderId.Equals(OrderId)) (case-sensitive string compare)
  Why: Locale and case sensitivity bugs — OrdinalIgnoreCase is safer
  Option: Use StringComparison.OrdinalIgnoreCase or normalise IDs at entry point
```

---

## Checklist: Kafka Consumer / Go Message Handler

Run when: code processes Kafka messages, uses consumer groups, or handles events.

```
BLOCK — Missing error handling on message processing
  Pattern: consumer loop with no try/catch or recover() around the handler
  Risk: One bad message panics/crashes the entire consumer — partition stalls
  Fix: Wrap handler in recover() (Go) or try/catch (.NET) — route failures to DLQ

BLOCK — No retry limit — infinite retry on error
  Pattern: for { if err != nil { continue } } with no max attempt counter
  Risk: Poison pill message loops forever, blocks partition processing
  Fix: Add attempt counter, exponential backoff, DLQ after maxRetries

BLOCK — Non-idempotent handler with no deduplication
  Pattern: handler that inserts/creates without checking for existing record
  Risk: At-least-once delivery = duplicates. Double inserts, double charges, double events.
  Fix: Add idempotency key check before processing (see kos-decisions.md)

WARN — No DLQ routing for permanent errors
  Pattern: all errors retried the same way regardless of error type
  Risk: Business rule violations or bad schema messages retry forever, wasting resources
  Fix: Classify errors — transient → retry, permanent → DLQ immediately

WARN — Committing offset before processing completes
  Pattern: consumer.CommitOffset() called before the DB write or downstream call succeeds
  Risk: Message marked as processed but handling failed — silent data loss
  Fix: Commit offset only after successful processing

WARN — Shared mutable state across goroutines / concurrent handlers
  Pattern: writing to a shared map, slice, or counter from multiple goroutines without sync
  Risk: Race condition — data corruption or panic under concurrent load
  Fix: Use sync.Mutex, sync.Map, or channel-based communication

SUGGEST — No structured logging with message metadata
  Pattern: log.Println("error") with no message ID, topic, partition, offset
  Why: Impossible to trace a specific message failure in production
  Option: Always log topic, partition, offset, and key alongside the error

SUGGEST — Consumer group ID hardcoded
  Pattern: consumer group ID as a string literal in code
  Why: Makes it impossible to run multiple environments without code change
  Option: Move to config / environment variable
```

---

## Checklist: Go Service / Background Worker

Run when: code is written in Go — services, workers, goroutines, channels.

```
BLOCK — Goroutine leak — goroutine started with no cancellation path
  Pattern: go func() { for { ... } }() with no ctx.Done() or stop channel
  Risk: Goroutine runs forever, leaks memory, accumulates over restarts
  Fix: Pass context.Context, select on ctx.Done() for clean shutdown

BLOCK — Unhandled goroutine panic
  Pattern: go func() { ... }() with no recover()
  Risk: Panic in goroutine crashes the entire process
  Fix: Add defer recover() inside every goroutine that runs untrusted logic

BLOCK — Closing a channel that may already be closed
  Pattern: close(ch) without ensuring only one sender closes
  Risk: Panic: close of closed channel
  Fix: Use sync.Once or producer-owns-close pattern

WARN — Channel send/receive with no timeout or context
  Pattern: ch <- value or <-ch with no select + ctx.Done() + timeout
  Risk: Blocks forever if the other side is slow or stuck
  Fix: Use select with ctx.Done() and a timeout case

WARN — Large struct copied by value in hot path
  Pattern: func process(data LargeStruct) instead of func process(data *LargeStruct)
  Risk: Unnecessary memory allocation and copy on every call
  Fix: Pass pointer for structs > ~64 bytes in hot paths

SUGGEST — No graceful shutdown handler
  Pattern: main() with no os.Signal listener for SIGTERM / SIGINT
  Why: Container orchestration (Kubernetes) sends SIGTERM before killing — ignoring it
       causes in-flight work to be lost
  Option: Listen for SIGTERM, stop accepting new work, drain in-flight, then exit
```

---

## Checklist: PostgreSQL / SQL Queries

Run when: code contains raw SQL, query builders, or schema definitions.

```
BLOCK — Query with no WHERE clause on a large table
  Pattern: SELECT * FROM large_table or DELETE FROM table with no WHERE
  Risk: Full table scan — locks table, kills DB performance, may delete everything
  Fix: Always scope queries — add WHERE, LIMIT, or explicit intent comment

BLOCK — N+1 queries in raw SQL loop
  Pattern: for each ID: execute SELECT WHERE id = $1
  Risk: Same as EF Core N+1 — O(n) roundtrips
  Fix: SELECT WHERE id = ANY($1::int[]) with array of IDs

WARN — Missing index on foreign key or frequent filter column
  Pattern: WHERE column = $1 on a column with no index in schema
  Risk: Sequential scan on every query — latency grows with table size
  Fix: Add index — CREATE INDEX CONCURRENTLY for production tables

WARN — SELECT * in production query
  Pattern: SELECT * FROM table
  Risk: Over-fetching, breaks if schema changes, prevents index-only scans
  Fix: Always name the columns you need

WARN — String concatenation in SQL (SQL injection risk)
  Pattern: "SELECT ... WHERE id = " + userId
  Risk: SQL injection vulnerability
  Fix: Always use parameterised queries / prepared statements

SUGGEST — No LIMIT on potentially unbounded result set
  Pattern: SELECT ... FROM table WHERE condition (no LIMIT)
  Why: If condition matches 100k rows, you load 100k rows into memory
  Option: Add LIMIT with pagination, or assert max expected rows in comment
```

---

## Checklist: API Endpoint / HTTP Handler

Run when: code defines an HTTP route, controller action, or API handler.

```
BLOCK — Sensitive data returned in error response
  Pattern: return StatusCode(500, ex.Message) or returning stack trace to client
  Risk: Exposes internal implementation, file paths, connection strings to caller
  Fix: Log full error internally, return generic error message to client

BLOCK — No input validation before processing
  Pattern: directly using request body fields without null/format/range checks
  Risk: NullReferenceException, format exceptions, business rule violations in production
  Fix: Validate at entry point — fail fast with 400 before touching business logic

WARN — Missing idempotency key on mutating POST endpoint
  Pattern: POST endpoint that creates/charges with no idempotency key mechanism
  Risk: Retry from client = duplicate record / double charge
  Fix: Accept Idempotency-Key header, check before processing (see kos-decisions.md)

WARN — No timeout on downstream calls (DB, HTTP, Kafka)
  Pattern: HttpClient call or DB query with no explicit timeout configured
  Risk: Slow dependency hangs the request thread indefinitely
  Fix: Set explicit timeouts — 5s internal, 15s external (see kos-decisions.md)

WARN — Returning 200 with null body instead of 404
  Pattern: return Ok(null) or return Ok(new { data = null }) when resource not found
  Risk: Caller can't distinguish "found but empty" from "doesn't exist"
  Fix: return NotFound() with a clear message

SUGGEST — No request/trace ID in logs
  Pattern: logger.LogError(ex.Message) with no correlation ID
  Why: Impossible to trace a specific request failure across services in production
  Option: Log HttpContext.TraceIdentifier or a custom X-Request-ID header value

SUGGEST — Synchronous controller action in .NET
  Pattern: public IActionResult Get() instead of public async Task<IActionResult> GetAsync()
  Why: Blocks thread pool thread for the duration of the request
  Option: Use async/await throughout the call chain
```

---

## Checklist: ETL / Data Pipeline / FTP Ingestion

Run when: code processes files, batch imports, staging tables, or sync jobs.

```
BLOCK — Processing entire file in memory
  Pattern: File.ReadAllBytes() or reading full FTP file into a List<> before processing
  Risk: Files > 100MB cause OOM exception or memory pressure on the service
  Fix: Stream the file — read and process in chunks (see kos-decisions.md: chunk size rules)

BLOCK — No transaction boundary on batch insert
  Pattern: inserting records one by one with no wrapping transaction
  Risk: Partial insert if process crashes midway — inconsistent staging data
  Fix: Wrap batch in a transaction, commit per chunk, mark processed rows

BLOCK — Writing directly to main DB without staging
  Pattern: FTP/external data written directly to production tables
  Risk: Dirty data, duplicates, or malformed records corrupt production
  Fix: Always write to staging first, validate, then apply (see kos-patterns.md: Staging → Validate → Apply)

WARN — No idempotency on file reprocessing
  Pattern: re-running the sync job on the same file produces duplicate records
  Risk: FTP retries or re-runs cause double inventory, double orders
  Fix: Track processed file names/checksums, skip already-processed files

WARN — Swallowing validation errors silently
  Pattern: catch (Exception) { continue; } with no logging of failed rows
  Risk: Silent data loss — bad rows dropped without audit trail
  Fix: Log every rejected row with reason, expose a validation failure count metric

SUGGEST — No progress metric for long-running sync
  Pattern: batch job with no logging or metrics until it completes
  Why: Impossible to know if job is stuck or just slow in production
  Option: Emit Prometheus counter per N rows processed, log progress every 1000 rows
```

---

## Checklist: Distributed / High-Concurrency API

Run when: code handles high concurrent load, uses connection pools, manages distributed state, or involves cache/rate limiting.

```
BLOCK — Synchronous DB calls in high-concurrency endpoint
  Pattern: .FirstOrDefault(), .ToList() without async variants in a concurrent API endpoint
  Risk: Each request blocks a thread pool thread for the full DB wait duration.
        Under 100 concurrent × 1.5s hold = 150s of blocked threads → thread starvation.
  Fix: Use async/await + async DB methods (.FirstOrDefaultAsync(), .ToListAsync())
       Requires IDbContextFactory for parallel independent queries (DbContext is not thread-safe)
  Formula: concurrent_requests × hold_time_seconds < pool_size
           If result > 80% of pool → reduce queries or go async

BLOCK — No rate limiting on expensive endpoint
  Pattern: Endpoint hitting DB or external API with no rate limit per client
  Risk: One client can exhaust the connection pool for all other clients (thundering herd)
  Fix: Add Token Bucket per user/resource using Redis (kos-patterns.md #14)
       Return HTTP 429 with Retry-After header on rejection

BLOCK — Shared DbContext across concurrent operations
  Pattern: Single _context instance shared between Task.Run() calls or parallel threads
  Risk: EF Core DbContext is NOT thread-safe — race conditions, data corruption, exceptions
  Fix: Inject IDbContextFactory<T>, create a new context per task:
       await using var ctx = _contextFactory.CreateDbContext();

WARN — No Redis cache on read-heavy endpoint
  Pattern: Frequently-called GET endpoint with no caching, reads same data repeatedly
  Risk: DB connection pool exhausted under sustained concurrent load
  Check: Same data read > 10× per minute with low change frequency?
  Fix: Add Redis cache-aside pattern with TTL:
       30s for order status, 5min for user profile, 1hr for reference data
       Add event-driven invalidation via Kafka for accuracy

WARN — Connection pool ceiling not validated
  Pattern: No proof that concurrent_requests × queries × hold_time fits within pool_size
  Risk: Works fine at 10 concurrent, silently fails at 100 concurrent
  Check: concurrent × query_count × avg_query_ms / 1000 < pool_size (default 100)
  Fix: Reduce query count (batch), reduce hold time (async), or increase pool size

SUGGEST — Independent DB calls made sequentially
  Pattern: Three unrelated DB calls executed one after another in the same request
  Why: Serial: A + B + C = 300ms; Parallel via Task.WhenAll: max(A,B,C) = 100ms
  Option: Task.WhenAll() with IDbContextFactory for independent DB calls per task
```

---

## Checklist: Async .NET / EF Core Async

Run when: code uses `async`/`await`, `Task`, `Task.Run`, `Task.WhenAll`, or async EF Core methods.

```
BLOCK — .Result or .Wait() on async method in ASP.NET context
  Pattern: someAsyncMethod().Result or someAsyncMethod().Wait()
  Risk: Deadlock — ASP.NET sync context blocks waiting for a thread that's waiting
        for the sync context. Manifests as request hang, never completes.
  Fix: Await all the way up the call chain. Never mix sync blocking with async code.

BLOCK — Single DbContext shared across parallel Task.Run() / Task.WhenAll() calls
  Pattern: Task.Run(() => _context.Orders...) alongside Task.Run(() => _context.Payments...)
           using the same injected _context instance
  Risk: EF Core DbContext is NOT thread-safe — concurrent access causes exceptions,
        data corruption, or silent query interleaving.
  Fix: Inject IDbContextFactory<T>, create one DbContext per task:
       await using var ctx = _contextFactory.CreateDbContext();

BLOCK — async void method outside of UI event handler
  Pattern: public async void ProcessOrder() { ... }
  Risk: Exceptions are unobservable — crash the process silently.
        Callers cannot await it — fire-and-forget with no error propagation.
  Fix: Use async Task for all async methods. async void only for UI/event handlers.

WARN — Missing CancellationToken propagation
  Pattern: public async Task<T> GetData() with no CancellationToken parameter
  Risk: Client disconnect or request timeout does not cancel the in-flight DB query.
        Wastes DB connections and compute on abandoned requests under load.
  Fix: Accept CancellationToken, pass to all async calls:
       .FirstOrDefaultAsync(cancellationToken), HttpClient.GetAsync(url, token)

WARN — IDbContextFactory not used for parallel EF Core queries
  Pattern: Task.WhenAll with EF Core queries but no IDbContextFactory
  Risk: DbContext is not thread-safe — will throw InvalidOperationException or corrupt data.
  Fix: Register in DI: builder.Services.AddDbContextFactory<MyDbContext>(options => ...);
       Per-task usage: await using var ctx = _factory.CreateDbContext();

WARN — Missing ConfigureAwait(false) in library/service code
  Pattern: await someTask; (no ConfigureAwait) inside a library or service layer
  Risk: In ASP.NET Framework, captures the sync context unnecessarily — can cause deadlock
        when combined with .Result or .Wait() anywhere in the call chain.
  Fix: Add .ConfigureAwait(false) on all awaits in service/library code.
       (ASP.NET Core has no sync context — harmless but still good practice)

SUGGEST — Async method missing Async suffix
  Pattern: public async Task<T> GetData() instead of GetDataAsync()
  Why: .NET convention — async methods end in Async for discoverability and clarity.
  Option: Rename public methods to follow convention, especially on interfaces.

SUGGEST — Task.Run() wrapping non-CPU-bound sync code
  Pattern: await Task.Run(() => _context.Orders.ToList())
  Why: For I/O-bound work, Task.Run offloads to a thread pool thread but still blocks it.
       No throughput gain — use true async I/O methods instead.
  Option: Use .ToListAsync() directly. Reserve Task.Run for genuinely CPU-bound work only.
```

---

## Checklist: Payment / Financial System

Run when: code processes payments, transfers money, manages balances, or integrates with a PSP (Stripe, PayPal, Braintree).

```
BLOCK — Money stored as float
  Pattern: amount column as float or double type
  Risk: Floating point arithmetic errors — 0.1 + 0.2 ≠ 0.3 → balance drift over time
  Fix: Store as integer minor units (cents: 100 = $1.00) or DECIMAL(19,4) column

BLOCK — Missing idempotency key on payment endpoint
  Pattern: POST /payments with no idempotency_key check
  Risk: Client retry on timeout = double charge (at-least-once HTTP = two executions)
  Fix: Accept Idempotency-Key header, check existing result before processing,
       store result with key (TTL: 24–48 hours)

BLOCK — No double-entry ledger
  Pattern: Single mutable balance column, no append-only transaction log
  Risk: No audit trail, race conditions, no reconciliation capability
  Fix: Append debit + credit rows per transaction to ledger table
       Balance = SUM(ledger entries) — never from a mutable column alone

BLOCK — Raw card data handled by your service
  Pattern: Code receives, stores, or transmits credit card numbers or CVVs
  Risk: PCI-DSS Level 1 compliance required — major audit burden and breach liability
  Fix: Use PSP hosted payment page (kos-patterns.md #24) — card data never reaches your server

BLOCK — No reconciliation process
  Pattern: Financial system with no end-of-day comparison against PSP settlement files
  Risk: Silent balance discrepancies accumulate undetected for days/weeks
  Fix: Daily reconciliation job: internal ledger == PSP settlement; any mismatch → alert

WARN — Non-idempotent Kafka payment consumer
  Pattern: Payment consumer processes without checking for duplicate event_id
  Risk: Kafka at-least-once delivery = same payment event may arrive twice = double debit
  Fix: Deduplication table: check processed_event_ids before processing, insert after success

WARN — No compensation on partial payment failure
  Pattern: Multi-step payment with no rollback if a middle step fails
  Risk: Money reserved but not charged, or charged but order not fulfilled
  Fix: TC/C or Orchestration Saga — every step has a defined cancel/compensate operation

WARN — PSP HTTP call with no timeout or circuit breaker
  Pattern: Synchronous PSP call on the critical payment path with no timeout
  Risk: PSP slowdown hangs all payment requests → connection pool exhaustion
  Fix: Explicit timeout (15s for external PSP) + Circuit Breaker (kos-patterns.md #9)

SUGGEST — Financial state not event-sourced
  Pattern: Payment state stored only as current mutable status (PENDING → PAID → REFUNDED)
  Why: No audit trail, cannot answer "what happened at 14:32?", cannot replay on bug fix
  Option: Append payment events to immutable log (kos-patterns.md #19)
          PaymentInitiated → CardCharged → PaymentSettled → Refunded
```

## Checklist: Test Coverage (.NET / xUnit)

> Run when reviewing test files OR when generating new tests. Goal: every branch observable,
> no false-green from InMemory quirks, test isolation guaranteed.

```
─── BLOCK ──────────────────────────────────────────────────────────────────────────────

BLOCK — No test for the exception/catch path
  Pattern: Only happy-path tests; catch block (ResultInt = -10) never exercised
  Risk: Silent failures in production — error path untested, may swallow wrong exceptions
  Fix: Add test with missing seed data or injected throw; assert ResultInt == -10 and
       ReturnMessage is non-empty

BLOCK — Shared DbContext across parallel tasks in tests
  Pattern: Single OrderContext instance passed to multiple concurrent Task.WhenAll arms
  Risk: EF Core DbContext is NOT thread-safe — "A second operation was started on this
        context" exception in CI but not locally (timing-dependent)
  Fix: Use TestDbContextFactory (TA17); each task arm gets its own CreateDbContext() instance

─── WARN ───────────────────────────────────────────────────────────────────────────────

WARN — Same InMemory database name reused across test instances
  Pattern: .UseInMemoryDatabase("TestDb") hard-coded string shared across all tests
  Risk: Test A seeds data → Test B reads stale data from previous test → false-green or
        false-red depending on execution order
  Fix: .UseInMemoryDatabase(Guid.NewGuid().ToString()) — unique name per test class instance

WARN — AsSplitQuery() used in production method but InMemory provider selected in tests
  Pattern: Method under test calls a repository with AsSplitQuery(); test uses InMemory
  Risk: InMemory may silently ignore AsSplitQuery() (EF Core 6+) or throw
        InvalidOperationException (older versions) — test result unreliable
  Fix: Switch to SQLite InMemory (.UseSqlite("Filename=:memory:") + EnsureCreated()) when
       AsSplitQuery() or EF.CompileQuery is present in the call path

WARN — Only one branch of "All" vs specific SubOrderId tested
  Pattern: Tests cover SourceSubOrderId = "SUB-001" but not "All" (or vice versa)
  Risk: Entire batch-load code path (GetSubOrderMessageFromBatchAsync) never exercised
  Fix: Add dedicated test for SourceSubOrderId = "All" with multiple sub-orders seeded;
       verify Items count equals sum across sub-orders

WARN — Navigation properties not seeded; test passes because null check missing in prod
  Pattern: Test seeds Order but not Customer nav property; assertion passes by luck
  Risk: In production, orderHeader.Customer is loaded via Include() — if null-check is
        missing, NRE on first customer order → untested code path
  Fix: Always seed navigation properties (Customer, Addresses, Items) that are accessed
       in the method under test; assert their mapped fields explicitly

─── SUGGEST ────────────────────────────────────────────────────────────────────────────

SUGGEST — Use Record.ExceptionAsync for no-throw assertions
  Pattern: try/catch in test to verify exception is swallowed
  Why: Record.ExceptionAsync is idiomatic xUnit and produces clearer failure messages
  Option: var ex = await Record.ExceptionAsync(() => sut.Method(...)); Assert.Null(ex);

SUGGEST — Use Guid.NewGuid().ToString() for DB isolation per test
  Pattern: Hard-coded string DB name
  Why: Prevents flaky tests when xUnit runs test methods in parallel
  Option: Move DbContextOptions creation into constructor with Guid.NewGuid()

SUGGEST — Separate seed helpers from test methods
  Pattern: Inline _context.Order.Add(...) + SaveChanges() repeated in every [Fact]
  Why: DRY — seed changes break N tests instead of one helper; readability suffers
  Option: Private SeedOrder(...) / SeedSubOrder(...) helpers with default parameters;
          see TA18 skeleton for reference pattern

SUGGEST — Add deadlock-guard test for Task.WhenAll paths
  Pattern: Async methods with Task.WhenAll have no timeout test
  Why: Deadlocks manifest only under load; a simple CancellationTokenSource(10s) guard
       catches them in CI before they reach production
  Option: Task.WhenAny(workTask, Task.Delay(Timeout.Infinite, cts.Token));
          Assert.Same(workTask, completed)

SUGGEST — Inline repositories (new Repo()) are a testability smell — log it
  Pattern: new OrderRepository(_context) inside method → cannot mock
  Why: Forces integration test over unit test; every test needs DB setup
  Option: Extract IOrderRepository / ISubOrderRepository interfaces; inject via constructor
          — flag as SUGGEST in code review, link to future refactor task
```

> Cross-reference: TA17 (TestDbContextFactory), TA18 (xUnit skeleton), test-generation.md §3–§4