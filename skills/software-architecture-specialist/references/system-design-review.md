# 🏗️ System Design Review

> Read this file when the user asks to "review this system", "audit my design",
> "is this architecture solid?", "what could go wrong with X?", or when Design Review
> mode is triggered with a system description, diagram, or flow.
>
> The goal is to find structural weaknesses BEFORE they become incidents.
> Think of this as a pre-mortem: assume the system will fail — find where first.
>
> Always run ALL applicable sections. Score each one.
> Output risks ranked by likelihood × impact, not by section order.

---

## How to Run a System Design Review

1. **Identify system type** from the description — pick all that apply:
   - Data Sync / ETL / FTP Pipeline
   - Event-Driven / Kafka-based
   - API / Service Layer
   - Background Worker / Batch Job
   - Distributed Transaction / Multi-service Flow
   - Real-time / Stateful Connection System (WebSocket, live location, chat)
   - Financial / Payment System (payments, ledger, wallets, reconciliation)

2. **Run every applicable review section** for the system type(s) — including system-type-specific sections at the bottom

3. **Score each dimension** 1–5:
   - 5 = Strong, no concerns
   - 3 = Acceptable, known gaps
   - 1 = Critical gap, likely to cause an incident

4. **Output format**: risks ranked by severity, then a scorecard, then a prioritised action list

---

## Output Format

```
🏗️ Mode: System Design Review
System: [name]
Type: [Data Sync / Event-Driven / API / Worker / Distributed]

--- RISKS (ranked by severity) ---

🔴 CRITICAL — [Risk title]
   Where: [Component or flow step]
   What could go wrong: [Specific failure scenario]
   Likelihood: High / Medium / Low
   Impact: [Data loss / Outage / Corruption / Latency / Silent failure]
   Fix: [Concrete architectural change]

🟡 MEDIUM — [Risk title]
   Where: [Component]
   What could go wrong: [Scenario]
   Fix: [Recommendation]

🟢 LOW — [Risk title]
   Where: [Component]
   What could go wrong: [Scenario]
   Fix: [Consider for future]

--- SCORECARD ---

| Dimension           | Score (1–5) | Notes |
|---------------------|-------------|-------|
| Flow Completeness   | X/5 | |
| Failure Handling    | X/5 | |
| Data Consistency    | X/5 | |
| Retry & Idempotency | X/5 | |
| Observability       | X/5 | |
| Scalability         | X/5 | |
| Security Boundary   | X/5 | |
Overall: X/35

--- ACTION PLAN (prioritised) ---

Priority 1 — [Action]: [1 sentence what to do]
Priority 2 — [Action]: [1 sentence what to do]
Priority 3 — [Action]: [1 sentence what to do]

ADR needed? [Yes/No — which decision needs to be documented]
KOS action: [Which Knowledge / Pattern records to create from this review]
```

---

## Review Section 1: Flow Completeness

**Run for**: every system type.

Every system must define three things before it is considered designed — not just coded:

```
[ ] HAPPY PATH defined
    Is the full end-to-end flow documented?
    Can you trace a single record from entry to final state?
    Questions to ask:
    - What triggers the flow?
    - What is the terminal success state?
    - Who/what consumes the output?

[ ] EDGE CASES defined
    What are the known non-standard inputs or states?
    Questions to ask:
    - What happens with empty input / zero records?
    - What happens with duplicate records?
    - What happens if a downstream dependency returns unexpected data?
    - What are the boundary conditions on IDs, timestamps, amounts?

[ ] FAILURE MODES defined
    What happens when each component fails?
    Questions to ask:
    - What if the DB is down during processing?
    - What if the message queue is unavailable?
    - What if a partial write completes before a crash?
    - What is the recovery path for each failure?
```

**Score 5** — all three defined and documented
**Score 3** — happy path documented, edge cases partially known
**Score 1** — only happy path exists, no failure modes defined

---

## Review Section 2: Failure Handling & Resilience

**Run for**: every system type.

```
[ ] Every external call has a timeout configured
    Risk if missing: Threads held indefinitely, cascading slowdown
    Check: DB queries, HTTP calls, Kafka produce/consume, file reads

[ ] Every external call has a retry strategy
    Risk if missing: Transient failures cause permanent data loss
    Check: Is backoff applied? Is max retry count set? Is DLQ configured?

[ ] Partial failure is handled
    Risk if missing: Half-processed records leave system in inconsistent state
    Check: What happens if the process crashes after step 2 of a 5-step flow?
    Good: Transaction boundary wraps the unit of work
    Bad: Each step commits independently with no compensating logic

[ ] Poison pill protection exists
    Risk if missing: One bad message/record blocks all processing forever
    Check: After N failures, does the record/message route to DLQ or dead store?

[ ] Circuit breaker or fallback exists for critical dependencies
    Risk if missing: Downstream outage cascades into this system
    Check: If [dependency] goes down, what does this system do?
```

---

## Review Section 3: Data Consistency

**Run for**: systems that write to DB, sync data, or process events.

```
[ ] Write operations are atomic
    Risk if missing: Partial writes cause corrupt or inconsistent state
    Check: Is there a transaction boundary around the logical unit of work?
    Watch for: Multiple _context.SaveChangesAsync() calls in one flow without rollback

[ ] Idempotency is guaranteed on retryable operations
    Risk if missing: Retries cause duplicate records, double charges, double events
    Check: Can this operation be called twice with the same input safely?
    Signals: Is there a unique constraint? An idempotency key check? A dedup step?

[ ] Event publish and DB write are atomic (if events are published)
    Risk if missing: DB written but event not published (or vice versa) = silent inconsistency
    Check: Is Outbox pattern used? Or is there a risk of partial success?

[ ] Change detection is reliable (for sync systems)
    Risk if missing: Missed updates or phantom changes cause stale data
    Check: Is detection based on timestamps (unreliable if source doesn't update them),
           hash comparison (reliable but expensive), or change feed (reliable if available)?

[ ] Schema changes in source are handled
    Risk if missing: Silent data loss when source adds/removes fields
    Check: Is source schema validated on ingestion? What happens on unexpected fields?
```

---

## Review Section 4: Retry Strategy & Idempotency

**Run for**: Kafka consumers, background workers, ETL jobs, API handlers.

```
[ ] Retry policy defined per error type
    Transient (timeout, lock, network) → retry with backoff
    Permanent (bad data, business rule) → DLQ immediately, no retry
    Unknown → retry N times, then DLQ
    Risk if missing: Either data loss (no retry) or infinite loops (always retry)

[ ] Retry is safe (idempotent)
    Risk if missing: Retrying a non-idempotent operation causes side effects
    Check: INSERT → needs unique constraint or existence check
           External API call → needs idempotency key
           Event publish → needs dedup on consumer side

[ ] DLQ is monitored and actionable
    Risk if missing: Silent data loss — messages pile up with no alert
    Check: Is there an alert on DLQ depth > 0?
           Is there a runbook for DLQ replay?
           Are DLQ messages inspectable (not just a byte blob)?

[ ] Backoff strategy is defined
    Risk if missing: Retry storms overwhelm recovering dependency
    Check: Is exponential backoff applied?
           Is there jitter to prevent thundering herd?
```

---

## Review Section 5: Observability

**Run for**: every system type.

```
[ ] Request/operation tracing exists
    Risk if missing: Cannot trace a specific record through the system in production
    Check: Is a trace ID / correlation ID propagated across all components?
           Is it present on every log line?

[ ] Key business metrics are emitted
    Risk if missing: Cannot tell if the system is working correctly, only if it's running
    Check for each system type:
    - Data Sync: records_processed_total, records_failed_total, sync_duration_seconds
    - Kafka Consumer: consumer_lag, messages_processed_total, processing_duration_seconds
    - API: request_duration_seconds (histogram), error_rate, request_count
    - ETL: rows_staged, rows_validated, rows_applied, rows_rejected

[ ] Alerts are defined for meaningful failure conditions
    Risk if missing: Failures are discovered by users, not by monitoring
    Check: Is there an alert for error rate > threshold?
           Is there an alert for consumer lag growing?
           Is there an alert for sync job not completing in expected window?

[ ] Logs include enough context to diagnose without code access
    Risk if missing: Debugging requires reproducing the problem, not reading logs
    Check: Do error logs include the record ID, operation, system state, and error detail?
           Are there no "something went wrong" messages without context?

[ ] Health check endpoint exists (for services)
    Risk if missing: Load balancer routes traffic to broken instances
    Check: Does /health return meaningful status (not just 200 OK always)?
```

---

## Review Section 6: Scalability

**Run for**: systems with variable load or data volume growth.

```
[ ] No O(n) DB operations in hot paths
    Risk if missing: Latency degrades linearly as data grows
    Check: Are there any queries without WHERE clauses?
           Any loops that query the DB per iteration?
           Any SELECT * on large tables?

[ ] Batch size is bounded
    Risk if missing: Large batches cause memory spikes or lock contention
    Check: Is there a maximum batch size defined?
           Is it configurable without code change?

[ ] State does not accumulate in memory unboundedly
    Risk if missing: Service crashes under load from OOM
    Check: Are there any List<T> or Dictionary that grow without a cap?
           Are streaming patterns used for large file/data processing?

[ ] Horizontal scaling is possible
    Risk if missing: Single instance becomes a bottleneck
    Check: Is shared mutable state avoided?
           Can two instances run simultaneously without conflict?
           Is Kafka partition key designed for parallel consumption?

[ ] Database indexes exist for all frequent query patterns
    Risk if missing: Full table scans degrade at scale
    Check: Every WHERE clause column — is it indexed?
           Every foreign key — is it indexed?
           Every ORDER BY column in paginated queries?
```

---

## Review Section 7: Security Boundary

**Run for**: systems that handle external data, user input, or cross-service calls.

```
[ ] Input validation at system entry point
    Risk if missing: Bad data propagates into DB, events, and downstream systems
    Check: Is source data validated before staging?
           Are field types, lengths, and formats checked?
           Are required fields enforced?

[ ] Sensitive data is not logged
    Risk if missing: PII leaks into log aggregation systems
    Check: Are customer names, emails, phone numbers, payment data excluded from logs?
           Are there log filtering rules for sensitive fields?

[ ] Service-to-service auth is enforced
    Risk if missing: Any internal service can call any other
    Check: Are internal API calls authenticated (service account, token, mTLS)?

[ ] Secrets are not hardcoded
    Risk if missing: Credentials in source code = credential leak
    Check: Connection strings, API keys, tokens — are they in config/env vars, not code?
```

---

## System-Type Specific Reviews

### Data Sync / ETL / FTP Pipeline

Additional checks beyond the core sections:

```
[ ] Staging table is used before main DB write
    Risk: Dirty external data corrupts production
    Check: FTP/external → staging → validate → apply (never direct to main)

[ ] File processing is streamed, not loaded entirely into memory
    Risk: Large files (>100MB) cause OOM
    Check: Is file read with a streaming reader or chunked processor?

[ ] Processed files are tracked to prevent reprocessing
    Risk: Rerunning the job processes the same file twice
    Check: Is file name/hash/timestamp recorded after successful processing?

[ ] Sync window and frequency are defined
    Risk: Unknown sync lag causes stale data without alerting
    Check: Is there an expected completion time? An alert if job doesn't finish by then?

[ ] Record-level vs full-snapshot strategy is explicit
    Risk: Full snapshot on large datasets is wasteful; record-level needs reliable change detection
    Check: Which strategy is used? Is it appropriate for data volume and source reliability?
```

### Event-Driven / Kafka-based System

Additional checks:

```
[ ] Partition key is chosen deliberately
    Risk: Wrong key causes ordering violations or hot partitions
    Check: Is the key chosen to guarantee order per entity (e.g. OrderId)?
           Is cardinality high enough to distribute load across partitions?

[ ] Consumer is designed for at-least-once delivery
    Risk: Assuming exactly-once causes duplicate processing bugs
    Check: Is consumer handler idempotent?
           Is offset committed only after successful processing?

[ ] Topic retention policy is defined
    Risk: Messages expire before consumers process them after an outage
    Check: Is retention long enough to cover expected consumer downtime?

[ ] Schema evolution strategy exists
    Risk: Producer adds a field → consumer crashes on deserialization
    Check: Is schema registry used? Are consumers forward-compatible?
           Is there a versioning strategy for event schemas?
```

### Background Worker / Batch Job

Additional checks:

```
[ ] Job has a defined SLA window
    Risk: Job runs indefinitely with no alerting
    Check: Is there a maximum expected duration? An alert if exceeded?

[ ] Job is safe to run concurrently (or is explicitly locked)
    Risk: Two instances running simultaneously cause duplicate processing
    Check: Is there a distributed lock? Or is the job designed to be idempotent under concurrency?

[ ] Job progress is checkpointed
    Risk: Long job crashes at 95% complete and must restart from 0%
    Check: Is progress recorded? Can the job resume from last checkpoint?

[ ] Job failure leaves system in a recoverable state
    Risk: Half-run job leaves data in an intermediate state with no recovery path
    Check: Is there a rollback or cleanup procedure for failed runs?
```

---

### Real-Time / Stateful Connection System

Additional checks for systems using WebSocket, SSE, long polling, or persistent connections:

```
[ ] Connection protocol is appropriate for the use case
    Risk: Using polling when WebSocket is needed = high latency or wasted requests
    Check (patterns.md #16–18 / K14):
      Bidirectional, low latency (chat, location)?  → WebSocket
      One-way push, infrequent (notifications)?     → Long Polling or SSE
      Periodic pull, > 5s interval?                 → Short Polling

[ ] Connection memory budget is calculated
    Risk: 1M connections × 10KB/connection = 10GB RAM — server OOM
    Check: connections_per_server × 10KB < available_RAM - headroom
    Plan: 100K–1M connections per WebSocket server instance

[ ] WebSocket server scaling strategy is defined
    Risk: Sticky sessions or a pub/sub router is needed — standard load balancer doesn't route by connection
    Check: Are sessions sticky? OR is Redis Pub/Sub used to route messages between servers?

[ ] Heartbeat / presence mechanism is defined
    Risk: Silently disconnected clients appear online — stale presence data
    Check: Is there a heartbeat (every 5–30s)? TTL-based presence in Redis?

[ ] Message delivery guarantee is defined
    Risk: WebSocket is NOT at-least-once — messages can be lost on disconnect
    Check: Is there an offline message queue for disconnected users?
           Are messages persisted before delivery attempt (not just sent to socket)?

[ ] Service discovery routes users to correct server
    Risk: Message for user on server A arrives at server B — not delivered
    Check: Is there a user-to-server mapping? (ZooKeeper, etcd, Redis hash)
           Is consistent hashing used to route users to the same server?

[ ] Reconnection and message replay is handled
    Risk: Client disconnects for 30s, misses messages — no catch-up mechanism
    Check: Can client request messages since last_message_id on reconnect?
```

---

### Financial / Payment System

Additional checks for payment processing, wallets, ledgers, and settlement:

```
[ ] Double-entry ledger is used
    Risk: Mutable balance only = no audit trail, race conditions, no reconciliation
    Check: Is there an append-only ledger table?
           Does every transaction create two rows (debit + credit)?
           Does sum(debit) + sum(credit) = 0 for every transaction_id?

[ ] Money is stored as integer minor units (never float)
    Risk: Float arithmetic drift causes balance errors at scale
    Check: Is amount column BIGINT (cents) or DECIMAL(19,4)? Never FLOAT or DOUBLE.

[ ] Idempotency key is required for every payment
    Risk: Retry on timeout = double charge
    Check: Is Idempotency-Key header required? Checked before processing?
           Is the result stored with the key (TTL: 24-48 hours)?

[ ] PCI scope is minimised or eliminated
    Risk: Handling raw card data requires PCI-DSS Level 1 audit
    Check: Is PSP hosted page used (Pattern #24)? Does your server ever touch card numbers?

[ ] TC/C or Saga pattern used for multi-step payments
    Risk: Partial failure leaves money reserved without charge, or charged without fulfillment
    Check: Does every step have a defined compensate/cancel operation?
           Is compensation triggered automatically on failure?

[ ] End-of-day reconciliation exists
    Risk: Silent balance discrepancies accumulate undetected
    Check: Is there a daily reconciliation job?
           Does it compare internal ledger against PSP settlement files?
           Is there an alert if discrepancy > 0?

[ ] PSP external calls have timeout + Circuit Breaker
    Risk: PSP slowdown cascades into your payment service
    Check: Is there an explicit timeout (15s)? A Circuit Breaker (Pattern #9)?
           Is there an async fallback (queue the payment, retry via Kafka)?

[ ] Kafka payment consumer is idempotent
    Risk: At-least-once delivery = same payment event processed twice = double debit
    Check: Is there a processed_event_ids deduplication table?
           Is ON CONFLICT DO NOTHING on the ledger insert?
```

---

## Worked Example — SubOrder Processing Review (from target.cs)

**System**: SubOrder Processing — `GetSubOrder()` method
**Type**: API / Service Layer
**Source**: `target.cs` (lines 1-125 coordinator, lines 126-600+ supporting methods)
**Date**: 2026-03-25

### Key findings

```
🔴 CRITICAL — N+1 query pattern: GetSubOrderMessage loop (target.cs:518-540)
   Where: GetSubOrderMessage() foreach — 1 DB query per sub-order
   What could go wrong: 10 sub-orders = 10 sequential queries. Under 100 concurrent
     requests = 1,000 DB calls competing for pool → timeout cascade.
   Likelihood: High (already occurred under production concurrency)
   Impact: API timeout, connection pool exhaustion, cascading failure
   Fix: Batch load all sub-orders in one query with Contains()

🔴 CRITICAL — N+1 query pattern: GetRewardItem loop (target.cs:69-77)
   Where: GetRewardItem() for loop — 1 DB query per SourceSubOrderId
   What could go wrong: Same as above — O(n) queries for n sub-orders
   Likelihood: High (triggered when SourceSubOrderId == "All")
   Impact: Compounds with GetSubOrderMessage N+1 — doubles the query count
   Fix: Single batch query with Contains() on SourceSubOrderIdList

🔴 CRITICAL — Lazy load inside loop: GetOrderPromotion (target.cs:209)
   Where: Entry(datalist[i]).Reference(x => x.Amount).Load() per promotion
   What could go wrong: 1 extra DB query per promotion row
   Likelihood: High
   Impact: Adds P queries (P = promotion count) on top of existing N+1
   Fix: Add .Include(op => op.Amount) to initial query

🔴 CRITICAL — Duplicate reference resolution 3× per request (target.cs:55-57)
   Where: GetOrderHeader, GetOrderMessagePayments, GetOrderPromotion each call
     IsExistOrderReference independently for the same SourceOrderId
   What could go wrong: 6-9 redundant queries per request — pure waste
   Likelihood: Certain (fires on every request)
   Impact: Connection pool pressure under concurrency
   Fix: Resolve once at coordinator (GetSubOrder), pass resolved ID down
   See: Pattern #12 Coordinator-Level Resolution

🔴 CRITICAL — Any() + FirstOrDefault() double queries (target.cs:483-494, 497-510)
   Where: GetOrderHeader, IsExistOrderReference (both overloads)
   What could go wrong: 2 queries where 1 is enough — on every call
   Likelihood: Certain
   Impact: Doubles query count for these lookups
   Fix: Collapse to single FirstOrDefault() — null check replaces Any()

🔴 CRITICAL — No query count observability
   Where: All methods in target.cs — no EF logging, no query counter
   What could go wrong: N+1 is undetectable until latency spikes in production
   Likelihood: High
   Impact: Silent degradation, discovered by users not monitoring
   Fix: Add EF Core query count metric per request to Prometheus

🟡 MEDIUM — Missing AsNoTracking() on all read queries
   Where: Every _context query in target.cs (lines 136, 194, 366, 488, 518)
   What could go wrong: EF change tracker overhead: memory + CPU waste on pure reads
   Fix: Add AsNoTracking() to all read-only queries

🟡 MEDIUM — Weak error logging (target.cs:44-48, 116-122)
   Where: catch blocks use LogInformation instead of LogError, no stack trace,
     no SourceOrderId/SubOrderId context
   What could go wrong: Production errors invisible or untraceable
   Fix: LogError with structured parameters + stack trace

🟡 MEDIUM — No request/trace ID in any log line
   Where: All _logger calls throughout target.cs
   What could go wrong: Under concurrency, logs interleave — can't trace one request
   Fix: Add correlation ID via middleware or structured logging scope

🟢 LOW — Synchronous DB calls (entire file)
   Where: All queries use .FirstOrDefault(), .ToList() — no async variants
   What could go wrong: Thread pool thread blocked during each DB round-trip
   Fix: Convert to async/await (Phase 4 follow-up)
```

### Query Count Analysis (target.cs, N=10 sub-orders, P=3 promotions)

| Source | Location | Queries |
|--------|----------|---------|
| IsExistOrderReference × 3 callers | lines 55-57 → 497-510 | 6-9 |
| GetOrderHeader (Any + FirstOrDefault) | lines 483-494 | 2 |
| GetOrderMessagePayments | lines 136-139 | 1 |
| GetSubOrderMessage loop | lines 518-540 | 10 |
| GetOrderPromotion + Amount lazy loads | lines 194, 209 | 1 + 3 |
| GetRewardItem loop | lines 69-77 → 366-369 | 10 |
| **Total** | | **~33** |
| **After all fixes (target)** | | **~7** |

### Scorecard (pre-fix, based on target.cs review)

| Dimension           | Score | Notes |
|---------------------|-------|-------|
| Flow Completeness   | 4/5 | Happy path well-defined, edge cases mostly covered |
| Failure Handling    | 2/5 | Errors swallowed with LogInformation, no circuit breaker, no timeout on DB |
| Data Consistency    | 4/5 | No concurrent write risk on this read path |
| Retry & Idempotency | 3/5 | Read-only method — no retry needed, but no timeout protection |
| Observability       | 1/5 | No query count metrics, no trace ID, errors logged at wrong level |
| Scalability         | 1/5 | N+1 × 3 loops, duplicate queries, no AsNoTracking — connection pool bomb |
| Security Boundary   | 4/5 | No sensitive data in logs (but no structured logging either) |
**Overall: 19/35**

### Action Plan

1. **Immediate (Phase 1)**: Collapse Any()+FirstOrDefault(), add AsNoTracking(), eager-load Amount — reduces ~33 to ~15 queries
2. **Day 2 (Phase 2)**: Hoist IsExistOrderReference to coordinator — reduces ~15 to ~10 queries
3. **Day 3 (Phase 3)**: Batch GetRewardItem and GetSubOrderMessage with Contains() — reduces ~10 to ~7 queries
4. **Follow-up (Phase 4)**: Async migration with IDbContextFactory + Task.WhenAll for parallel independent calls
5. **Monitoring**: Add EF Core query count metric + Stopwatch baseline before any code changes
6. **ADR created**: `architecture-decision.md` — Option A (Batch Refactor) now, Option B (Async) follow-up, Option C (CQRS) deferred