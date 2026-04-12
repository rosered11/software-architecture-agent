# System Design Review

> Triggered by: "review this system", "audit my design", "is this architecture solid?", or when a system description/diagram is shared.
> Goal: pre-mortem — find structural weaknesses before they become incidents.
> Run ALL applicable sections. Score each. Output risks ranked by likelihood × impact.

## Process

1. **Identify system type** — pick all that apply:
   - Data Sync / ETL / FTP Pipeline
   - Event-Driven / Kafka-based
   - API / Service Layer
   - Background Worker / Batch Job
   - Distributed Transaction / Multi-service Flow
   - Real-time / Stateful Connection (WebSocket, live location, chat)
   - Financial / Payment System

2. Run every applicable section + system-type-specific sections below
3. Score each dimension 1–5: `5` = strong · `3` = acceptable gaps · `1` = critical gap
4. Output: risks ranked by severity → scorecard → prioritised action list

## Output Format

```
🏗️ Mode: System Design Review
System: [name] | Type: [types]

--- RISKS ---
🔴 CRITICAL — [title]
   Where: [component] | Likelihood: H/M/L | Impact: [data loss / outage / corruption / latency / silent]
   Failure: [specific scenario] | Fix: [architectural change]

🟡 MEDIUM — [title] | Where: [component]
   Failure: [scenario] | Fix: [recommendation]

🟢 LOW — [title] | Where: [component] | Fix: [future consideration]

--- SCORECARD ---
| Dimension           | Score | Notes |
|---------------------|-------|-------|
| Flow Completeness   |  /5   |       |
| Failure Handling    |  /5   |       |
| Data Consistency    |  /5   |       |
| Retry & Idempotency |  /5   |       |
| Observability       |  /5   |       |
| Scalability         |  /5   |       |
| Security Boundary   |  /5   |       |
Overall: /35

--- ACTION PLAN ---
Priority 1 — [action]: [one sentence]
Priority 2 — ...

ADR needed? [Yes/No] | KOS action: [records to create]
```

---

## Section 1: Flow Completeness
*Run for: all system types*

```
[ ] HAPPY PATH — end-to-end flow documented; trace a single record from entry to terminal state
[ ] EDGE CASES — empty input, duplicates, unexpected downstream data, boundary conditions on IDs/timestamps/amounts
[ ] FAILURE MODES — each component's failure and recovery path defined
```
**Score**: 5 = all three defined · 3 = happy path + partial edge cases · 1 = happy path only

---

## Section 2: Failure Handling & Resilience
*Run for: all system types*

```
[ ] Every external call has a timeout — DB, HTTP, Kafka, file reads
[ ] Every external call has a retry strategy — backoff, max count, DLQ configured
[ ] Partial failure handled — transaction boundary wraps the logical unit of work
    Good: single transaction per unit | Bad: each step commits independently with no compensation
[ ] Poison pill protection — after N failures, route to DLQ, not infinite loop
[ ] Circuit breaker / fallback for critical dependencies
```

---

## Section 3: Data Consistency
*Run for: systems that write to DB, sync data, or process events*

```
[ ] Writes are atomic — single transaction boundary per logical unit
    Watch: multiple SaveChangesAsync() in one flow without rollback
[ ] Retryable operations are idempotent — unique constraint, dedup key, or existence check
[ ] Event publish + DB write are atomic — Outbox pattern; or risk of silent split-brain
[ ] Change detection is reliable — timestamp (weak) / hash (strong) / change feed (strongest)
[ ] Source schema changes handled — validate on ingestion; unknown fields don't silently drop data
```

---

## Section 4: Retry Strategy & Idempotency
*Run for: Kafka consumers, workers, ETL jobs, API handlers*

```
[ ] Retry policy per error type:
    Transient (timeout, lock, network) → retry + backoff
    Permanent (bad data, business rule) → DLQ immediately, no retry
    Unknown → retry N times → DLQ
[ ] Retry is safe — INSERT has unique constraint; external API call has idempotency key
[ ] DLQ is monitored — alert on depth > 0; messages inspectable; replay runbook exists
[ ] Backoff is exponential with jitter — prevents thundering herd on recovery
```

---

## Section 5: Observability
*Run for: all system types*

```
[ ] Trace/correlation ID propagated and present on every log line
[ ] Business metrics emitted per system type:
    Data Sync: records_processed_total, records_failed_total, sync_duration_seconds
    Kafka:     consumer_lag, messages_processed_total, processing_duration_seconds
    API:       request_duration_seconds (histogram), error_rate, request_count
    ETL:       rows_staged, rows_validated, rows_applied, rows_rejected
[ ] Alerts on: error rate threshold, consumer lag growth, job not completing in expected window
[ ] Error logs include: record ID, operation, system state, error detail — no bare "something failed" messages
[ ] Health endpoint returns meaningful status (not just always-200)
```

---

## Section 6: Scalability
*Run for: systems with variable load or data volume growth*

```
[ ] No O(n) DB ops in hot paths — no unscoped queries, no loop-per-row
[ ] Batch size is bounded and configurable without code change
[ ] No unbounded in-memory accumulation — stream large files/data; cap collections
[ ] Horizontal scaling is safe — no shared mutable state; Kafka partition key distributes load
[ ] Indexes cover all WHERE, FK, and ORDER BY columns in frequent query patterns
```

---

## Section 7: Security Boundary
*Run for: systems handling external data, user input, or cross-service calls*

```
[ ] Input validated at entry — types, lengths, formats, required fields
[ ] Sensitive data excluded from logs — PII, payment data, emails, tokens
[ ] Service-to-service calls authenticated — service account, token, or mTLS
[ ] Secrets in config/env vars — never hardcoded in source
```

---

## System-Type Specific

### Data Sync / ETL / FTP Pipeline
```
[ ] Staging table used — external → staging → validate → apply (never write directly to main)
[ ] File read is streamed — not loaded entirely into memory (OOM risk on >100MB files)
[ ] Processed files tracked — name/hash/timestamp recorded after success; prevents reprocessing
[ ] Sync window/frequency defined — alert if job doesn't finish in expected window
[ ] Sync strategy explicit — full snapshot vs record-level; appropriate for volume and source reliability
```

### Event-Driven / Kafka-based
```
[ ] Partition key chosen deliberately — guarantees order per entity; cardinality distributes load
[ ] Consumer designed for at-least-once — handler is idempotent; offset committed after success only
[ ] Topic retention covers expected consumer downtime window
[ ] Schema evolution strategy — registry, forward-compatible consumers, event versioning
```

### Background Worker / Batch Job
```
[ ] SLA window defined — alert if max duration exceeded
[ ] Safe under concurrency — distributed lock OR idempotent under parallel runs
[ ] Progress checkpointed — job resumes from last checkpoint, not from 0% on crash
[ ] Failure leaves recoverable state — rollback or cleanup path exists for partial runs
```

### Real-Time / Stateful Connection (WebSocket)
```
[ ] Protocol appropriate:
    Bidirectional, low latency (chat, location) → WebSocket
    One-way push, infrequent (notifications)   → SSE or Long Polling
    Periodic pull, >5s interval                → Short Polling
[ ] Memory budget calculated — connections × 10KB < available_RAM; plan 100K–1M per instance
[ ] Scaling strategy — sticky sessions OR Redis Pub/Sub to route messages across servers
[ ] Heartbeat + TTL presence — detect silently disconnected clients (every 5–30s)
[ ] Message delivery guaranteed — offline queue; messages persisted before delivery attempt
[ ] User-to-server routing — Redis hash / etcd mapping or consistent hashing
[ ] Reconnect + replay — client requests messages since last_message_id on reconnect
```

### Financial / Payment System
```
[ ] Double-entry ledger — append-only; every transaction = debit + credit row; SUM = 0 per tx_id
[ ] Money as integer minor units — BIGINT (cents) or DECIMAL(19,4); never FLOAT/DOUBLE
[ ] Idempotency key required per payment — checked before processing; result stored 24–48h TTL
[ ] PCI scope minimised — PSP hosted page; card data never reaches your server
[ ] TC/C or Saga for multi-step payments — every step has a defined compensate/cancel operation
[ ] End-of-day reconciliation — internal ledger vs PSP settlement; alert on any discrepancy
[ ] PSP calls: explicit timeout (15s) + Circuit Breaker; async fallback via Kafka if needed
[ ] Kafka payment consumer idempotent — processed_event_ids dedup; ON CONFLICT DO NOTHING on ledger insert
```
