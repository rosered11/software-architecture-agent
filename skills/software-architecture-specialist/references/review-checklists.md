# Code Review Checklists

> Auto-loaded when: user pastes code for review, "review this", "is this good?", "what's wrong with this?", PR/method shared for feedback.
> Run ALL matching checklists. Report every finding — don't silently pass ambiguous items.

## How to Run

1. Identify technologies in the code (EF Core, Kafka, Go, PostgreSQL, API, ETL, Async .NET, Payment, Tests)
2. Run every matching checklist
3. For every BLOCK/WARN: show exact line/pattern + risk + fix

## Output Format

```
🔍 Mode: Code Review
Technologies: [list] | Checklists: [list]

--- FINDINGS ---
🚨 BLOCK — [title]
   Pattern: [exact code] | Risk: [what fails and when] | Fix: [corrected code]

⚠️ WARN — [title]
   Pattern: [exact code] | Risk: [what could go wrong] | Fix: [recommendation]

💡 SUGGEST — [title]
   Pattern: [exact code] | Why: [improvement] | Option: [how]

--- SUMMARY ---
Score: PASS / PASS WITH WARNINGS / BLOCK
Blocks: N | Warns: N | Suggests: N
Lesson: [1 sentence — pattern this review reinforces]
KOS action: [Incident / Knowledge / Pattern / Tech Asset to create?]
```

| Severity | Meaning | Merge |
|----------|---------|-------|
| 🚨 BLOCK | Will cause production incident at scale | Do not merge |
| ⚠️ WARN | May cause problem under load or edge case | Acknowledge before merging |
| 💡 SUGGEST | Architectural improvement | Merge OK, create follow-up |

---

## EF Core / .NET Data Access
*Run when: `_context`, `DbSet`, `Include()`, `.Load()`, LINQ queries*

```
BLOCK — DB call inside loop (N+1)
  Pattern: foreach/for containing _context.*, .Load(), FirstOrDefault(), Where()
  Risk: O(n) DB roundtrips — invisible at 5 rows, incident at 500
  Fix: Collect IDs → batch WHERE IN → Dictionary<id,entity> lookup

BLOCK — .Entry().Reference/Collection().Load() inside loop
  Pattern: _context.Entry(x).Reference(p => p.Y).Load() in foreach
  Risk: 1 DB roundtrip per iteration; EF Core does NOT batch these
  Fix: Replace with batch query + Dictionary

BLOCK — Any() + FirstOrDefault() on same table
  Pattern: if (_context.X.Where(...).Any()) { return _context.X.Where(...).FirstOrDefault(); }
  Risk: 2 queries where 1 is enough — doubles DB load on every call
  Fix: Remove Any() — FirstOrDefault() returns null if not found

BLOCK — Missing AsNoTracking() on read-only queries
  Pattern: GET endpoint / read-only method without .AsNoTracking()
  Risk: EF change tracker overhead — memory + CPU waste on pure reads
  Fix: Add .AsNoTracking() to all read-only queries

BLOCK — Same reference resolver called 2+ times for same ID in one request
  Pattern: Multiple sibling methods each calling IsExistOrderReference() independently for the same ID
  Risk: Each call = 2–3 independent queries — pure redundancy, compounds under concurrency
  Fix: Resolve once at coordinator; pass resolved ID to sub-calls
  See: kos-patterns.md #12 (Coordinator-Level Resolution)

WARN — Include() 2+ collections without AsSplitQuery()
  Pattern: .Include(x => x.A).Include(x => x.B) without .AsSplitQuery()
  Risk: Cartesian explosion — result rows = A.Count × B.Count
  Fix: Add .AsSplitQuery()

WARN — Full entity loaded when only 2–3 fields needed
  Pattern: Returning/mapping full entity when few fields are used
  Risk: Over-fetching — unnecessary columns transferred and tracked
  Fix: Add .Select(x => new Dto { ... }) projection

WARN — Missing null check after FirstOrDefault()
  Pattern: var x = _context.X.FirstOrDefault(); x.Property (no null check)
  Risk: NullReferenceException in production when record doesn't exist
  Fix: Null check before use, or null-conditional operator

SUGGEST — Synchronous DB calls
  Pattern: .FirstOrDefault() / .ToList() instead of async variants
  Why: Blocks thread pool under concurrent load
  Option: .FirstOrDefaultAsync() / .ToListAsync() throughout

SUGGEST — Magic string comparisons on IDs
  Pattern: .Where(w => w.SourceOrderId.Equals(id)) (case-sensitive string compare)
  Why: Locale/case sensitivity bugs
  Option: StringComparison.OrdinalIgnoreCase or normalise IDs at entry point
```

---

## Kafka Consumer / Go Message Handler
*Run when: Kafka consumers, consumer groups, event handlers*

```
BLOCK — Missing error handling on message processing
  Pattern: Consumer loop with no try/catch or recover() around handler
  Risk: One bad message crashes the consumer — partition stalls
  Fix: Wrap handler in recover() (Go) / try/catch (.NET); route failures to DLQ

BLOCK — No retry limit — infinite retry on error
  Pattern: for { if err != nil { continue } } with no attempt counter
  Risk: Poison pill loops forever, blocks partition processing
  Fix: Attempt counter + exponential backoff + DLQ after maxRetries

BLOCK — Non-idempotent handler, no deduplication
  Pattern: Handler inserts/creates without checking for existing record
  Risk: At-least-once delivery = duplicates → double inserts, double charges
  Fix: Idempotency key check before processing

WARN — No DLQ routing for permanent errors
  Pattern: All errors retried the same way regardless of type
  Risk: Bad schema / business rule violations retry forever
  Fix: Classify — transient → retry with backoff; permanent → DLQ immediately

WARN — Offset committed before processing completes
  Pattern: CommitOffset() before DB write or downstream call succeeds
  Risk: Message marked processed but handling failed — silent data loss
  Fix: Commit offset only after successful processing

WARN — Shared mutable state across goroutines
  Pattern: Writing to shared map/slice/counter from multiple goroutines without sync
  Risk: Race condition — data corruption or panic under concurrent load
  Fix: sync.Mutex, sync.Map, or channel-based communication

SUGGEST — No structured logging with message metadata
  Pattern: log.Println("error") with no topic/partition/offset/key
  Option: Always log topic, partition, offset, key alongside the error

SUGGEST — Consumer group ID hardcoded
  Pattern: Group ID as string literal in code
  Option: Move to config / environment variable
```

---

## Go Service / Background Worker
*Run when: Go code — services, workers, goroutines, channels*

```
BLOCK — Goroutine leak (no cancellation path)
  Pattern: go func() { for { ... } }() with no ctx.Done() or stop channel
  Risk: Goroutine runs forever, leaks memory, accumulates over restarts
  Fix: Pass context.Context; select on ctx.Done() for clean shutdown

BLOCK — Unhandled goroutine panic
  Pattern: go func() { ... }() with no recover()
  Risk: Panic in goroutine crashes the entire process
  Fix: defer recover() inside every goroutine running untrusted logic

BLOCK — Closing a channel that may already be closed
  Pattern: close(ch) without ensuring single sender closes
  Risk: panic: close of closed channel
  Fix: sync.Once or producer-owns-close pattern

WARN — Channel send/receive with no timeout
  Pattern: ch <- value or <-ch without select + ctx.Done() + timeout
  Risk: Blocks forever if other side is slow or stuck
  Fix: select with ctx.Done() and a timeout case

WARN — Large struct copied by value in hot path
  Pattern: func process(data LargeStruct) for structs > ~64 bytes
  Risk: Unnecessary memory allocation and copy on every call
  Fix: Pass pointer

SUGGEST — No graceful shutdown handler
  Pattern: main() with no os.Signal listener for SIGTERM/SIGINT
  Why: Kubernetes sends SIGTERM before kill — ignoring it loses in-flight work
  Option: Listen for SIGTERM, drain in-flight, then exit
```

---

## PostgreSQL / SQL Queries
*Run when: raw SQL, query builders, schema definitions*

```
BLOCK — Query with no WHERE on large table
  Pattern: SELECT * FROM large_table or DELETE FROM table (no WHERE)
  Risk: Full table scan — locks table, may delete everything
  Fix: Always scope with WHERE, LIMIT, or explicit intent comment

BLOCK — N+1 in raw SQL loop
  Pattern: for each ID: SELECT WHERE id = $1
  Risk: O(n) DB roundtrips
  Fix: SELECT WHERE id = ANY($1::int[]) with array of IDs

WARN — Missing index on FK or frequent filter column
  Pattern: WHERE column = $1 on unindexed column
  Risk: Sequential scan — latency grows linearly with table size
  Fix: CREATE INDEX CONCURRENTLY for production tables

WARN — SELECT * in production query
  Pattern: SELECT * FROM table
  Risk: Over-fetching; breaks on schema change; prevents index-only scans
  Fix: Name the columns you need

WARN — String concatenation in SQL
  Pattern: "SELECT ... WHERE id = " + userId
  Risk: SQL injection
  Fix: Parameterised queries / prepared statements always

SUGGEST — No LIMIT on unbounded result set
  Pattern: SELECT ... WHERE condition (no LIMIT)
  Option: Add LIMIT with pagination, or assert max rows in comment
```

---

## API Endpoint / HTTP Handler
*Run when: HTTP routes, controller actions, API handlers*

```
BLOCK — Sensitive data in error response
  Pattern: return StatusCode(500, ex.Message) or stack trace returned to client
  Risk: Exposes internals, file paths, connection strings to caller
  Fix: Log full error internally; return generic message to client

BLOCK — No input validation before processing
  Pattern: Request body fields used directly without null/format/range checks
  Risk: NullReferenceException, format exceptions, business rule violations in production
  Fix: Validate at entry point — 400 before touching business logic

WARN — Missing idempotency key on mutating POST
  Pattern: POST that creates/charges with no idempotency key mechanism
  Risk: Client retry = duplicate record / double charge
  Fix: Accept Idempotency-Key header; check before processing (see kos-decisions.md)

WARN — No timeout on downstream calls
  Pattern: HttpClient or DB query with no explicit timeout configured
  Risk: Slow dependency hangs the request thread indefinitely
  Fix: 5s internal, 15s external (see kos-decisions.md)

WARN — 200 with null body instead of 404
  Pattern: return Ok(null) when resource not found
  Risk: Caller can't distinguish "found but empty" from "doesn't exist"
  Fix: return NotFound() with clear message

SUGGEST — No trace ID in logs
  Pattern: LogError(ex.Message) with no correlation ID
  Option: Log HttpContext.TraceIdentifier or X-Request-ID header value

SUGGEST — Synchronous controller action
  Pattern: public IActionResult Get() (not async Task<IActionResult>)
  Option: async/await throughout the call chain
```

---

## ETL / Data Pipeline / FTP Ingestion
*Run when: file processing, batch imports, staging tables, sync jobs*

```
BLOCK — Processing entire file in memory
  Pattern: File.ReadAllBytes() or reading full file into List<> before processing
  Risk: OOM on files >100MB
  Fix: Stream — read and process in chunks

BLOCK — No transaction boundary on batch insert
  Pattern: Inserting records one-by-one with no wrapping transaction
  Risk: Partial insert on crash — inconsistent staging data
  Fix: Wrap batch in transaction; commit per chunk; mark processed rows

BLOCK — Writing directly to main DB without staging
  Pattern: FTP/external data written directly to production tables
  Risk: Dirty data, duplicates, or malformed records corrupt production
  Fix: external → staging → validate → apply

WARN — No idempotency on file reprocessing
  Pattern: Re-running sync job on same file produces duplicate records
  Risk: FTP retries / re-runs cause double inventory, double orders
  Fix: Track file name/checksum; skip already-processed files

WARN — Swallowing validation errors silently
  Pattern: catch (Exception) { continue; } with no logging of failed rows
  Risk: Silent data loss — bad rows dropped with no audit trail
  Fix: Log every rejected row with reason; expose validation failure count metric

SUGGEST — No progress metric for long-running sync
  Pattern: Batch job with no logging/metrics until completion
  Option: Prometheus counter per N rows; log progress every 1000 rows
```

---

## Distributed / High-Concurrency API
*Run when: high concurrent load, connection pools, distributed state, cache/rate limiting*

```
BLOCK — Synchronous DB calls in high-concurrency endpoint
  Pattern: FirstOrDefault() / ToList() (no async) in concurrent API handler
  Risk: Each request blocks a thread pool thread for full DB wait duration
        Formula: concurrent × hold_ms / 1000 > pool_size → thread starvation
  Fix: async/await + async EF methods; IDbContextFactory for parallel queries

BLOCK — No rate limiting on expensive endpoint
  Pattern: Endpoint hitting DB/external API with no per-client rate limit
  Risk: One client exhausts connection pool for all others (thundering herd)
  Fix: Token Bucket per user/resource via Redis (kos-patterns.md #14); return 429 + Retry-After

BLOCK — Shared DbContext across concurrent operations
  Pattern: Single _context instance in Task.Run() or parallel threads
  Risk: DbContext is NOT thread-safe — race conditions, data corruption, exceptions
  Fix: IDbContextFactory<T>; one context per task via CreateDbContext()

WARN — No Redis cache on read-heavy endpoint
  Pattern: Frequently-called GET with no caching on low-change data
  Risk: DB pool exhausted under sustained concurrent load
  Fix: Cache-aside + TTL: 30s order status · 5min user profile · 1hr reference data
       Invalidate via Kafka events for accuracy

WARN — Connection pool ceiling not validated
  Pattern: No proof that concurrent × queries × hold_time fits within pool_size
  Check: concurrent × query_count × avg_query_ms / 1000 < pool_size (default 100)
  Fix: Reduce query count (batch), reduce hold time (async), or increase pool size

SUGGEST — Independent DB calls made sequentially
  Pattern: Three unrelated DB calls executed serially in one request
  Why: Serial A+B+C = 300ms; Task.WhenAll = max(A,B,C) = 100ms
  Option: Task.WhenAll() + IDbContextFactory
```

---

## Async .NET / EF Core Async
*Run when: `async`/`await`, `Task`, `Task.Run`, `Task.WhenAll`, async EF Core methods*

```
BLOCK — .Result or .Wait() on async method
  Pattern: someAsync().Result or someAsync().Wait() in ASP.NET context
  Risk: Deadlock — sync context blocks waiting for thread waiting for sync context → request hangs
  Fix: Await all the way up; never block on async code

BLOCK — Shared DbContext across parallel tasks
  Pattern: Task.Run(() => _context.Orders...) + Task.Run(() => _context.Payments...) — same instance
  Risk: DbContext NOT thread-safe — InvalidOperationException, data corruption, query interleaving
  Fix: IDbContextFactory<T>; CreateDbContext() per task

BLOCK — async void method
  Pattern: public async void ProcessOrder() { ... }
  Risk: Exceptions are unobservable — process crash; callers can't await — fire-and-forget with no error propagation
  Fix: async Task for all async methods; async void only for UI event handlers

WARN — Missing CancellationToken propagation
  Pattern: async Task<T> Get() with no CancellationToken parameter
  Risk: Client disconnect doesn't cancel in-flight DB query — wastes connections on abandoned requests
  Fix: Accept CancellationToken; pass to all async calls (FirstOrDefaultAsync, HttpClient, etc.)

WARN — IDbContextFactory not used for parallel EF Core queries
  Pattern: Task.WhenAll with EF Core queries but single injected _context
  Risk: DbContext not thread-safe — InvalidOperationException or silent data corruption
  Fix: Register AddDbContextFactory<T>(); CreateDbContext() per task arm

WARN — Missing ConfigureAwait(false) in library/service code
  Pattern: await someTask; (no ConfigureAwait) in service/library layer
  Risk: In ASP.NET Framework, captures sync context — deadlock if .Result/.Wait() anywhere in chain
  Fix: .ConfigureAwait(false) on all awaits in service/library code

SUGGEST — Async method missing Async suffix
  Pattern: public async Task<T> GetData() (not GetDataAsync())
  Option: Follow .NET convention — async methods end in Async, especially on interfaces

SUGGEST — Task.Run() wrapping non-CPU-bound sync code
  Pattern: await Task.Run(() => _context.Orders.ToList())
  Why: Offloads to thread pool but still blocks that thread — no throughput gain for I/O-bound work
  Option: .ToListAsync() directly; Task.Run only for genuinely CPU-bound work
```

---

## Payment / Financial System
*Run when: payments, transfers, balances, PSP integration*

```
BLOCK — Money stored as float
  Pattern: amount as float or double type
  Risk: Floating-point drift — 0.1+0.2 ≠ 0.3 → balance errors accumulate at scale
  Fix: BIGINT (cents) or DECIMAL(19,4); never FLOAT/DOUBLE

BLOCK — Missing idempotency key on payment endpoint
  Pattern: POST /payments with no idempotency_key check before processing
  Risk: Client retry on timeout = double charge
  Fix: Idempotency-Key header required; check before processing; store result 24–48h TTL

BLOCK — No double-entry ledger
  Pattern: Single mutable balance column; no append-only transaction log
  Risk: No audit trail, race conditions, no reconciliation capability
  Fix: Append debit + credit rows per transaction; balance = SUM(ledger entries)

BLOCK — Raw card data handled by your service
  Pattern: Code receives, stores, or transmits card numbers or CVVs
  Risk: PCI-DSS Level 1 audit required — major liability
  Fix: PSP hosted payment page (kos-patterns.md #24) — card data never reaches your server

BLOCK — No reconciliation process
  Pattern: Financial system with no end-of-day comparison against PSP settlement files
  Risk: Silent balance discrepancies accumulate undetected for days/weeks
  Fix: Daily job: internal ledger == PSP settlement; any discrepancy → immediate alert

WARN — Non-idempotent Kafka payment consumer
  Pattern: Consumer processes payment without checking duplicate event_id
  Risk: At-least-once delivery = same event twice = double debit
  Fix: processed_event_ids dedup table; check before processing; insert after success

WARN — No compensation on partial payment failure
  Pattern: Multi-step payment with no rollback if a middle step fails
  Risk: Money reserved but not charged, or charged but order not fulfilled
  Fix: TC/C or Orchestration Saga — every step has a defined cancel/compensate operation

WARN — PSP call with no timeout or circuit breaker
  Pattern: Synchronous PSP call on critical payment path with no timeout
  Risk: PSP slowdown cascades → connection pool exhaustion
  Fix: 15s explicit timeout + Circuit Breaker (kos-patterns.md #9); async fallback via Kafka

SUGGEST — Financial state not event-sourced
  Pattern: Payment state as mutable status only (PENDING → PAID → REFUNDED)
  Why: No audit trail; cannot answer "what happened at 14:32?"; cannot replay on bug fix
  Option: Append payment events to immutable log (kos-patterns.md #19)
```

---

## Test Coverage (.NET / xUnit)
*Run when: reviewing test files or generating new tests*

```
BLOCK — No test for exception/catch path
  Pattern: Only happy-path tests; catch block (e.g. ResultInt = -10) never exercised
  Risk: Error path untested — may swallow wrong exceptions silently in production
  Fix: Test with missing seed data or injected throw; assert error fields explicitly

BLOCK — Shared DbContext across parallel tasks in tests
  Pattern: Single context instance passed to multiple concurrent Task.WhenAll arms
  Risk: "A second operation was started on this context" — timing-dependent CI failures
  Fix: TestDbContextFactory (TA17); each task arm gets its own CreateDbContext()

WARN — Same InMemory DB name reused across test instances
  Pattern: .UseInMemoryDatabase("TestDb") hard-coded across all tests
  Risk: Test A seeds data → Test B reads stale data → false-green/false-red by execution order
  Fix: .UseInMemoryDatabase(Guid.NewGuid().ToString()) per test class instance

WARN — AsSplitQuery() used with InMemory provider
  Pattern: Method under test uses AsSplitQuery(); test uses InMemory provider
  Risk: InMemory ignores or throws on AsSplitQuery() — unreliable test results
  Fix: Switch to SQLite InMemory (.UseSqlite("Filename=:memory:") + EnsureCreated())

WARN — Only one branch of "All" vs specific SubOrderId tested
  Pattern: Tests cover one path but not the other (batch-load path never exercised)
  Risk: Entire code branch unexercised in CI
  Fix: Dedicated test for each branch; seed multiple sub-orders for "All" case

WARN — Navigation properties not seeded
  Pattern: Test seeds Order but not Customer nav property; assertion passes by luck
  Risk: NRE in production when Include() loads nav that tests assumed null-safe
  Fix: Seed all navigation properties accessed in method under test; assert mapped fields explicitly

SUGGEST — Use Record.ExceptionAsync for no-throw assertions
  Option: var ex = await Record.ExceptionAsync(() => sut.Method(...)); Assert.Null(ex);

SUGGEST — Unique DB name per test for isolation
  Option: Guid.NewGuid().ToString() in constructor — prevents flaky tests under xUnit parallelism

SUGGEST — Extract seed helpers from test methods
  Option: Private SeedOrder(...) / SeedSubOrder(...) helpers with defaults; see TA18 skeleton

SUGGEST — Add deadlock-guard test for Task.WhenAll paths
  Option: CancellationTokenSource(10s); Task.WhenAny(workTask, Task.Delay(∞, cts.Token)); Assert.Same(workTask, completed)

SUGGEST — Inline repositories are a testability smell
  Pattern: new OrderRepository(_context) inside method — cannot mock
  Option: Extract IOrderRepository interface; inject via constructor; flag as follow-up refactor
```

> Cross-reference: TA17 (TestDbContextFactory), TA18 (xUnit skeleton)
