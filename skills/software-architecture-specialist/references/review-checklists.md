# 🔎 Code Review Checklists

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
🔎 Mode: Code Review
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
  Fix: Add idempotency key check before processing (see decision-rules.md)

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
  Fix: Accept Idempotency-Key header, check before processing (see decision-rules.md)

WARN — No timeout on downstream calls (DB, HTTP, Kafka)
  Pattern: HttpClient call or DB query with no explicit timeout configured
  Risk: Slow dependency hangs the request thread indefinitely
  Fix: Set explicit timeouts — 5s internal, 15s external (see decision-rules.md)

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
  Fix: Stream the file — read and process in chunks (see decision-rules.md: chunk size rules)

BLOCK — No transaction boundary on batch insert
  Pattern: inserting records one by one with no wrapping transaction
  Risk: Partial insert if process crashes midway — inconsistent staging data
  Fix: Wrap batch in a transaction, commit per chunk, mark processed rows

BLOCK — Writing directly to main DB without staging
  Pattern: FTP/external data written directly to production tables
  Risk: Dirty data, duplicates, or malformed records corrupt production
  Fix: Always write to staging first, validate, then apply (see patterns.md: Staging → Validate → Apply)

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