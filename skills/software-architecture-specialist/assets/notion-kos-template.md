# 🗂️ Notion KOS Template (v2.0)

> Read this file when the user wants to capture a new record into their Notion workspace,
> asks "how do I fill in the KOS?", or when Knowledge Structuring mode is triggered.
> Use the filled examples to understand the expected depth for each field.
> Always output the complete record — never partial fills.

---

## Core Loop Reminder

```
Incident → Knowledge → Pattern → Decision → Reuse
```

Every record you create should link backward and forward in this chain.

---

## Index

| Database | Represents | When to Create |
|----------|-----------|----------------|
| [1. Incident](#1-incident) | WHAT happened | Any production problem, bug, or performance issue |
| [2. Knowledge](#2-knowledge) | WHY (theory) | Any concept learned from an incident or study |
| [3. Pattern](#3-pattern) | HOW to solve | Any reusable solution worth naming |
| [4. Decision Log](#4-decision-log) | WHY a decision was made | Any non-trivial architectural choice |
| [5. Tech Assets](#5-tech-assets) | Implementation | Any reusable code snippet or config |

---

## 1. Incident

**Represents**: WHAT happened in production.
**Create when**: A bug, slowness, outage, or data issue occurs.

### Template

```
Title:              [Short descriptive name — system + symptom]
Severity:           Low | Medium | High | Critical
System:             [System name from Systems DB]
Problem:            [Observable symptom — what the user/monitor saw]
Root Cause:         [The real technical reason — not the symptom]
Fix:                [What was done to resolve]
Lesson Learned:     [What to never repeat — architectural rule extracted]
Related Knowledge:  [→ Knowledge records that explain WHY this happened]
Applied Pattern:    [→ Pattern used to fix]
Related Decisions:  [→ Decision Log entries made during/after incident]
Related Tech Assets:[→ Code snippets used in the fix]
```

### Filled Example — GetSubOrder Latency Spike

```
Title:              GetSubOrder API Latency Spike
Severity:           High
System:             SubOrder Processing
Problem:            API response ~900ms, ~289 DB queries per single request
Root Cause:         N+1 query pattern — .Entry().Reference().Load() and
                    .Entry().Collection().Load() called inside foreach loops.
                    Each item triggered 1+ DB roundtrips. 50 items × 7 relations = 350 queries.
                    Also: redundant Any() + FirstOrDefault() on same table = 2 queries where 1 needed.
Fix:                Replaced loop-based lazy loads with batch WHERE id IN (...) queries.
                    Built Dictionary<id, entity> for O(1) in-memory lookup.
                    Added AsNoTracking() on all read-only queries.
                    Collapsed Any() + FirstOrDefault() pattern to single query.
Lesson Learned:     Never call DB inside a loop. EF Core does not batch .Load() automatically.
                    Latency ≈ #queries × DB roundtrip. Profile query count before deploying.
Related Knowledge:  → N+1 Query Problem
                    → Batch Query Pattern
                    → EF Core Best Practices
Applied Pattern:    → Avoid N+1 Query
Related Decisions:  → Use Batch IN Query instead of Eager Load in GetSubOrder
Related Tech Assets:→ Batch IN query snippet
                    → Dictionary O(1) lookup snippet
                    → AsNoTracking config snippet
```

---

## 2. Knowledge

**Represents**: WHY — theory, concepts, and understanding behind incidents and patterns.
**Create when**: You learn something that explains a problem or justifies a solution.

### Template

```
Title:            [Concept name — clear and searchable]
Type:             Concept | Technique | Framework Knowledge | Principle
Domain:           DB Performance | ORM | Distributed Systems | Event-Driven |
                  Resilience | Data | API Design | Auth | Observability
Difficulty:       Beginner | Intermediate | Advanced
Summary:          [1–2 sentences — what it is and why it matters]
Deep Dive:        [Full technical explanation — how it works, when it activates, what it costs]
Example:          [Concrete code or system example from your stack]
Trade-offs:       Pros: [list]
                  Cons: [list]
Decision Rule:    [If X → do Y. Concrete thresholds where possible]
Related Concepts: [→ Other Knowledge records — linked mental models]
Related Patterns: [→ Patterns derived from this knowledge]
Related Incidents:[→ Real incidents that exposed this knowledge]
Related Decisions:[→ Decisions that used this knowledge]
Related Tech Assets: [→ Code that implements this knowledge]
Source:           [Book / article / incident / own experience]
```

### Filled Example — N+1 Query Problem

```
Title:            N+1 Query Problem
Type:             Concept
Domain:           DB Performance
Difficulty:       Intermediate
Summary:          Making a DB call inside a loop causes total queries = N+1,
                  scaling linearly with data size. Silent at low volumes, catastrophic at scale.
Deep Dive:        Each .Entry(x).Reference(p).Load() inside a foreach is a separate DB roundtrip.
                  EF Core does not batch these automatically — each call goes to the DB individually.
                  With 50 items and 7 relations each, that is 350 separate queries from the loop alone.
                  The "+1" refers to the initial query to load the parent entity.
                  Pattern is invisible in development (5 items = 5 queries = fast)
                  and detonates in production (500 items = 500 queries = timeout).
Example:          // Each iteration = 1 DB call
                  for (int i = 0; i < datalist.Length; i++) {
                      _context.Entry(datalist[i]).Reference(x => x.Amount).Load();
                  }
Trade-offs:       Pros: Easy to write, readable, works correctly at small scale
                  Cons: O(n) DB calls, latency scales with data, invisible in tests
Decision Rule:    N < 50   → N+1 acceptable, no action
                  N > 100  → must batch
                  N > 1000 → batch + chunk (500 per query)
Related Concepts: → Lazy Loading
                  → ORM Overhead
                  → Change Tracking
Related Patterns: → Avoid N+1 Query
Related Incidents:→ GetSubOrder API Latency Spike
Related Decisions:→ Use Batch IN Query instead of Eager Load in GetSubOrder
Related Tech Assets: → Batch IN query snippet
Source:           GetSubOrder production incident, 2024
```

### Filled Example — Batch Query Pattern

```
Title:            Batch Query with IN Clause
Type:             Technique
Domain:           DB Performance
Difficulty:       Intermediate
Summary:          Load all needed records in one query using WHERE id IN (...),
                  then map results with an in-memory dictionary for O(1) lookup per item.
Deep Dive:        Collect all IDs needed from the current dataset.
                  Issue a single SELECT WHERE id IN (...) query.
                  Build a Dictionary<id, entity> from the result.
                  Replace per-item DB calls with dict.TryGetValue() — zero DB calls in loop.
                  Reduces N queries to 1 query + O(n) CPU for dictionary build.
                  Memory cost: all related entities loaded into RAM simultaneously.
Example:          var ids = items.Select(x => x.Id).ToList();
                  var map = _context.Amount
                      .AsNoTracking()
                      .Where(x => ids.Contains(x.RefId))
                      .ToDictionary(x => x.RefId);
                  foreach (var item in items) {
                      if (map.TryGetValue(item.Id, out var amount))
                          item.Amount = amount;
                  }
Trade-offs:       Pros: Dramatically fewer DB calls, predictable latency, easy to implement
                  Cons: Higher RAM usage, IN clause can be slow if N > 1000 (chunk then)
Decision Rule:    N > 100  → use batch IN query
                  N > 1000 → batch + chunk (500 per query)
Related Concepts: → N+1 Query Problem
                  → Dictionary Lookup
                  → Memory vs Latency Trade-off
Related Patterns: → Avoid N+1 Query
                  → Batch + Chunk Pattern
Related Incidents:→ GetSubOrder API Latency Spike
Related Decisions:→ Use Batch IN Query instead of Eager Load in GetSubOrder
Related Tech Assets: → Batch IN query snippet
                     → Dictionary O(1) lookup snippet
Source:           GetSubOrder production incident, 2024
```

---

## 3. Pattern

**Represents**: HOW to solve a class of problems — a reusable, named solution.
**Create when**: You apply a solution that could be reused in future systems.

### Template

```
Name:             [Pattern name — use established names where they exist]
Category:         DB Performance | Scalability | Event-Driven | Resilience |
                  Data Pipeline | API Design | Architecture
Problem:          [What class of problem this solves — 1–2 sentences]
Solution:         [How to apply the pattern — step by step]
When to Use:      [Concrete triggering conditions]
When NOT to Use:  [Anti-conditions — when this pattern causes more harm than good]
Complexity:       Low | Medium | High
Based on Knowledge: [→ Theory this pattern is grounded in]
Used in Incidents:  [→ Real incidents where this was applied]
Used in Decisions:  [→ Decision Log entries that chose this pattern]
Related Tech Assets:[→ Code snippets that implement this pattern]
```

### Filled Example — Avoid N+1 Query

```
Name:             Avoid N+1 Query
Category:         DB Performance
Problem:          A DB call inside a loop causes query count = O(n),
                  degrading API latency linearly with record count.
Solution:         1. Collect all IDs from the current working set
                  2. Single batch query using WHERE id IN (ids)
                  3. Build Dictionary<id, entity> from results
                  4. Replace per-item DB call with O(1) dict lookup
When to Use:      Any loop that accesses DB per iteration.
                  Any EF Core .Entry().Load() inside a foreach.
                  Any FirstOrDefault() called repeatedly with different IDs.
When NOT to Use:  N is provably < 50 and will never grow (adds complexity for no gain).
                  Conditions are too complex per-item to express as a single IN query.
Complexity:       Low–Medium
Based on Knowledge: → N+1 Query Problem
                    → Batch Query Pattern
Used in Incidents:  → GetSubOrder API Latency Spike
Used in Decisions:  → Use Batch IN Query instead of Eager Load in GetSubOrder
Related Tech Assets:→ Batch IN query snippet
                    → Dictionary O(1) lookup snippet
```

---

## 4. Decision Log

**Represents**: WHY a non-trivial architectural decision was made.
**Create when**: You choose between meaningful alternatives with trade-offs.
**Rule**: If you can explain the decision in one sentence with no trade-offs, it doesn't need a log entry. If you had to think about it, log it.

### Template

```
Title:            [Decision summary — verb + what was decided]
Context:          [Situation that triggered the decision — system state, constraints]
Problem:          [What needed to be decided and why it mattered]
Options Considered:
  A. [Option name]
     Pros: [list]
     Cons: [list]
  B. [Option name]
     Pros: [list]
     Cons: [list]
  C. [Option name — optional]
     Pros: [list]
     Cons: [list]
Decision:         [Which option was chosen and the single most important reason]
Trade-offs:       [What was sacrificed by choosing this option]
Expected Outcome: [What success looks like — measurable where possible]
Actual Outcome:   [Fill after deploy — what actually happened]
Related Knowledge:[→ Theory supporting the decision]
Related Patterns: [→ Patterns involved]
Related Incidents:[→ Incidents that drove this decision]
Date:             [YYYY-MM-DD]
```

### Filled Example — GetSubOrder Batch Query Decision

```
Title:            Use Batch IN Query instead of Eager Load in GetSubOrder
Context:          GetSubOrder had ~900ms latency in production due to 289 DB queries
                  triggered by EF Core lazy loads inside foreach loops.
                  System serves order fulfillment — latency directly impacts picker UX.
Problem:          Need to reduce DB roundtrips without adding infrastructure complexity
                  or changing the external API contract.
Options Considered:
  A. Include() Eager Load
     Pros: Simple, built into EF Core, less code
     Cons: Risk of cartesian explosion with multiple collections,
           no fine-grained control over what is loaded
  B. Batch IN Query + Dictionary (chosen)
     Pros: Precise control, no cartesian risk, no new infra,
           O(1) lookup replaces O(n) queries
     Cons: More code, manual mapping required
  C. Redis cache layer
     Pros: Very fast reads, reduces DB load system-wide
     Cons: Adds infra dependency, cache invalidation complexity,
           operational cost, over-engineering for this problem
Decision:         Option B — Batch IN Query with in-memory Dictionary mapping.
                  Root cause was unnecessary DB calls, not a caching problem.
                  Solve at the source before adding infrastructure.
Trade-offs:       Slightly more verbose mapping code.
                  Small memory increase (all related entities in RAM simultaneously).
                  No new infrastructure introduced.
Expected Outcome: Latency < 100ms. Queries < 20 per request.
Actual Outcome:   Latency ~40ms. Queries ~10 per request. 22× improvement.
Related Knowledge:→ N+1 Query Problem
                  → Batch Query Pattern
                  → EF Core Best Practices
Related Patterns: → Avoid N+1 Query
Related Incidents:→ GetSubOrder API Latency Spike
Date:             2024-XX-XX
```

---

## 5. Tech Assets

**Represents**: Reusable implementation — code snippets, configs, templates.
**Create when**: You write something you will want to find and reuse later.

### Template

```
Name:             [Descriptive asset name — what it does, not what it is]
Type:             Code Snippet | Pattern Implementation | Config | Template
Language:         C# | Go | SQL | YAML | JSON | Bash
Usage:            [When and how to use — copy-paste guidance]
Snippet:          [The actual code]
Related Knowledge:[→ Theory behind this code]
Related Pattern:  [→ Which pattern this implements]
```

### Filled Example — Batch IN Query Snippet

```
Name:             Batch load related entities with IN clause
Type:             Code Snippet
Language:         C# / EF Core
Usage:            Replace any .Entry(x).Reference().Load() or .Entry(x).Collection().Load()
                  inside a foreach loop. Collect IDs first, batch query, then map.

// Snippet:
var ids = datalist.Select(x => x.RefId).Distinct().ToList();

var amounts = await _context.Amount
    .AsNoTracking()
    .Where(x => ids.Contains(x.RefId))
    .ToListAsync();

var amountMap = amounts.ToDictionary(x => x.RefId);

foreach (var item in datalist)
{
    if (amountMap.TryGetValue(item.RefId, out var amount))
    {
        item.Amount = amount;
    }
}

Related Knowledge:→ Batch Query Pattern
Related Pattern:  → Avoid N+1 Query
```

### Filled Example — Dictionary O(1) Lookup

```
Name:             In-memory Dictionary mapping for O(1) lookup
Type:             Pattern Implementation
Language:         C#
Usage:            After any batch load, replace .FirstOrDefault() in a loop
                  with dictionary lookup. Build once, use many times.

// Snippet:
var map = entities.ToDictionary(x => x.Id);

var results = ids
    .Select(id => map.TryGetValue(id, out var entity) ? entity : null)
    .Where(x => x != null)
    .ToList();

Related Knowledge:→ Batch Query Pattern
Related Pattern:  → Avoid N+1 Query
```

### Filled Example — AsNoTracking Config

```
Name:             AsNoTracking configuration for read-only EF Core queries
Type:             Config Snippet
Language:         C# / EF Core
Usage:            All GET endpoints and read-only operations.
                  Reduces EF change tracker overhead — always apply on read paths.

// Snippet:
var subOrder = await _context.SubOrder
    .AsNoTracking()
    .AsSplitQuery()
    .Include(x => x.Items)
        .ThenInclude(i => i.Amount)
    .Where(w => w.IsActive && w.SourceOrderId == orderId)
    .Select(x => new SubOrderDto
    {
        Id = x.Id,
        Status = x.Status,
        Items = x.Items.Select(i => new ItemDto
        {
            Amount = i.Amount.NetAmount
        }).ToList()
    })
    .FirstOrDefaultAsync();

Related Knowledge:→ EF Core Best Practices
Related Pattern:  → Avoid N+1 Query
```

---

## Relation Wiring Cheatsheet

When filling any record, always check these relation chains:

```
New Incident created?
  → Link to Knowledge (what explains it)
  → Link to Pattern (what fixed it)
  → Link to Decision Log (what was decided during it)
  → Link to Tech Assets (what code was written for it)

New Knowledge created?
  → Link to Incidents that exposed it
  → Link to Patterns derived from it
  → Link to Related Concepts (self-relation)
  → Link to Tech Assets that implement it

New Pattern created?
  → Link to Knowledge it's based on
  → Link to Incidents where it was applied
  → Link to Tech Assets that implement it

New Decision Log created?
  → Link to Knowledge that supported it
  → Link to Patterns it used
  → Link to Incidents that drove it

New Tech Asset created?
  → Link to Knowledge behind the code
  → Link to Pattern it implements
```

---

## Output Format for Claude

When generating a KOS record, always output the **full block** using the template above.
Never output partial records. Never skip fields — use `[none yet]` if empty.
Always suggest relation links even if the user hasn't mentioned them.
After outputting the record, add:

```
📎 Suggested relations to create in Notion:
- [Database] → [Record title]
- [Database] → [Record title]

---

## Filled Records — GetSubOrder Phase 4 (incident2.cs, 2026-03-27)

### Incident Record

```
Title:              GetSubOrder Timeout Under High Concurrent Load (incident2.cs)
Severity:           High
System:             SubOrder Processing
Problem:            API times out under concurrent request bursts. Latency scaled with concurrency, not data size.
                    Baseline: P50=5,048ms, P99=8,283ms at 30 sequential calls.
Root Cause:         Connection pool exhaustion from query count multiplication.
                    Per-request query count ~33 (5 suborders, 3 promotions):
                    - IsExistOrderReference called 3× for same SourceOrderId = 6 redundant queries (BUG-3)
                    - GetRewardItem called per subOrderId in a loop = N queries (BUG-2)
                    - Entry().Reference(Amount).Load() per promotion row = M queries (BUG-6)
                    - Any()+FirstOrDefault() double-query on GetOrderHeader + IsExistOrderReference (BUG-4, BUG-5)
                    - Missing AsNoTracking() on all read queries (BUG-7)
                    Formula: 100 concurrent × 33 queries × 10ms = 33 connections held → pool (100) exhausted
Fix:                Phase 1-3 (synchronous refactor, incident2.cs):
                      BUG-3: Resolve IsExistOrderReference once in GetSubOrder coordinator, pass resolvedId to private internal methods
                      BUG-2: GetRewardItemsBatched() — single WHERE SourceSubOrderId IN (...) query
                      BUG-6: GetOrderPromotionInternal() — .Include(op => op.Amount).AsNoTracking()
                      BUG-4: IsExistOrderReference collapsed from 3 queries to 2
                      BUG-5: GetOrderHeader collapsed from 2 queries to 1
                      BUG-7: AsNoTracking() added to all read paths
                    Phase 4 (async parallel, incident2.cs):
                      GetSubOrderAsync() — fires GetOrderHeader, GetOrderMessagePayments,
                      GetOrderPromotion, GetRewardItemsBatched in parallel via Task.WhenAll.
                      Each task gets its own DbContext from IDbContextFactory.
                      Map functions (MapPayments, MapPromotions, MapRewardItems) shared by sync + async.
Result:             Queries: ~33 → ~7 per request (-79%)
                    P50 latency: 5,048ms → est. ~400ms (-92%) after Phase 4
                    Concurrency ceiling: ~20 req → ~400+ req
Lesson Learned:     Timeout under concurrency = query COUNT problem, not slow query problem.
                    Formula: concurrent_requests × queries_per_request × hold_time_ms must be < pool_size × 1000.
                    EF Core DbContext is not thread-safe — parallel tasks require IDbContextFactory.
                    Resolve shared context (IsExistOrderReference) once at coordinator, never inside sub-calls.
Related Knowledge:  → N+1 Query Problem
                    → EF Core DbContext Thread Safety + IDbContextFactory
                    → Connection Pool Math
                    → Async Parallel DB Coordinator
Applied Pattern:    → Batch Query (#1)
                    → Eager Graph Loading (#11)
                    → Coordinator-Level Resolution (#12)
                    → Bulk Load Then Map (#13)
                    → Async Parallel DB Coordinator (#26)
Related Decisions:  → Resolve IsExistOrderReference once at coordinator
                    → Use IDbContextFactory for parallel GetSubOrderAsync
Related Tech Assets:→ GetSubOrderAsync snippet
                    → MapPayments / MapPromotions / MapRewardItems helpers
                    → GetRewardItemsBatched snippet
                    → EF LogTo query counter
```

---

### Knowledge Record — EF Core DbContext Thread Safety

```
Title:            EF Core DbContext is Not Thread-Safe — IDbContextFactory Required
Type:             Framework Knowledge
Domain:           DB Performance / ORM
Difficulty:       Intermediate
Summary:          A single EF Core DbContext instance cannot be used concurrently from multiple threads.
                  Parallel DB tasks require separate DbContext instances, obtained from IDbContextFactory.
Deep Dive:        EF Core DbContext maintains internal state (change tracker, query cache, connection).
                  Concurrent access from multiple threads causes race conditions, corrupted state, or exceptions.
                  The solution: IDbContextFactory<TContext> creates a fresh DbContext per request/task.
                  In ASP.NET Core, scoped DbContext (default) is safe for sequential use in one request.
                  For parallel Task.WhenAll, each task must call _contextFactory.CreateDbContext()
                  and dispose it after use (await using).
                  Registration: services.AddDbContextFactory<AppDbContext>(options => ...);
                  The factory is registered as Singleton — safe to inject and use from any lifetime.
Example:          await using var ctx1 = _contextFactory.CreateDbContext();
                  await using var ctx2 = _contextFactory.CreateDbContext();
                  await Task.WhenAll(
                      GetOrderHeaderAsync(ctx1, orderId),
                      GetOrderPaymentsAsync(ctx2, orderId)
                  );
Trade-offs:       Pros: Enables true parallel DB queries in same request
                  Pros: Each context has isolated change tracker — no contamination
                  Cons: More connections opened per request (N parallel tasks = N connections)
                  Cons: Requires factory registration — extra DI setup
Decision Rule:    Single sequential method → use injected _context (scoped)
                  Parallel Task.WhenAll → use IDbContextFactory, 1 context per task
                  Shared _context across Task.WhenAll → BLOCK, race condition guaranteed
Related Concepts: → EF Core Change Tracking
                  → Async Parallel DB Coordinator
                  → Connection Pool Math
Related Patterns: → Async Parallel DB Coordinator (#26)
Related Incidents:→ GetSubOrder Timeout Under High Concurrent Load (incident2.cs)
Related Decisions:→ Use IDbContextFactory for parallel GetSubOrderAsync
Source:           incident2.cs Phase 4, 2026-03-27; EF Core Microsoft docs
```

---

### Pattern Record — Async Parallel DB Coordinator

```
Name:             Async Parallel DB Coordinator
Category:         Performance
Problem:          A coordinator method calls 2+ independent DB operations sequentially —
                  total latency = sum of all call times. Under load, threads block on I/O
                  and the connection pool exhausts.
Solution:         1. Complete any serial prerequisites (shared context resolution, initial query)
                  2. Identify all independent DB calls (no data dependency between them)
                  3. Create one DbContext per parallel task from IDbContextFactory
                  4. Fire all tasks simultaneously via Task.WhenAll
                  5. Await results and assemble in memory (zero DB calls in assembly step)
                  6. Expose sync wrapper (existing callers unaffected); migrate callers incrementally
When to Use:      - Coordinator calls 2+ independent DB operations sequentially
                  - I/O wait % > 80% on hot path
                  - Sequential latency > 300ms
                  - EF Core + .NET stack with IDbContextFactory available
When NOT to Use:  - Calls have data dependencies (sequential await instead)
                  - Only 1 DB call (parallelism overhead not worth it)
                  - Very low concurrency (< 10 req/s) — sequential async sufficient
Complexity:       Medium
Based on Knowledge: → EF Core DbContext Thread Safety + IDbContextFactory
                    → Connection Pool Math
Used in Incidents:  → GetSubOrder Timeout Under High Concurrent Load (incident2.cs)
Used in Decisions:  → Use IDbContextFactory for parallel GetSubOrderAsync
Related Tech Assets:→ GetSubOrderAsync snippet
```

---

### Decision Log Record

```
Title:            Use IDbContextFactory for Parallel GetSubOrderAsync
Context:          GetSubOrder Phase 4 — async parallelization of 3 independent DB calls.
                  Three options for enabling parallel DB access in EF Core.
Problem:          EF Core DbContext is not thread-safe. Task.WhenAll requires concurrent DB access.
                  How to enable parallel queries without race conditions?
Scale (BotE):     Sequential: 400+300+250+200 = 1,150ms per request
                  Parallel ceiling: max(400,300,250,200) = 400ms (-65%)
                  Connection cost: 4 parallel tasks × 1 connection each = 4 connections per request
Options:
  A. IDbContextFactory          Each task creates its own DbContext.
                                Safe, explicit, EF Core recommended pattern.
                                BotE: 400ms latency, 4 connections per request.
  B. IServiceScopeFactory       Create a new DI scope per task, resolve DbContext from scope.
                                More boilerplate, same safety guarantee as A.
                                Useful when more than just DbContext is needed per scope.
  C. Shared _context            Use existing scoped DbContext across tasks.
                                BLOCKED — DbContext is not thread-safe. Race condition guaranteed.
Decision:         Option A — IDbContextFactory
                  Cleanest API for this use case. No extra DI scope needed. await using disposes cleanly.
                  Factory registered as Singleton; DbContext instances scoped per task.
Expected Outcome: P50 latency: ~1,500ms → ~400ms (-73%)
                  Concurrency ceiling: ~140 req → ~400+ req
                  Thread safety: guaranteed — no shared state across parallel tasks
Watch out for:    Connection pool growth — 4 parallel tasks = 4 connections per request.
                  Under very high concurrency: 400 req × 4 connections = 1,600 connections.
                  Ensure pool size ≥ expected_concurrent_requests × parallel_tasks.
                  Monitor: pg_stat_activity (PostgreSQL) or sys.dm_exec_requests (SQL Server).
Related Knowledge:→ EF Core DbContext Thread Safety + IDbContextFactory
Related Patterns: → Async Parallel DB Coordinator (#26)
Related Incidents:→ GetSubOrder Timeout Under High Concurrent Load (incident2.cs)
```

---

### Tech Asset Records

```
Name:             GetSubOrderAsync — Async Parallel Coordinator
Type:             Code Snippet
Language:         C# / EF Core
Purpose:          Async version of GetSubOrder that fires 4 independent DB calls in parallel
Pattern:          Async Parallel DB Coordinator (#26)
Key Lines:
  await using var ctx1 = _contextFactory.CreateDbContext();
  await using var ctx2 = _contextFactory.CreateDbContext();
  await using var ctx3 = _contextFactory.CreateDbContext();
  await using var ctx4 = _contextFactory.CreateDbContext();
  await Task.WhenAll(
      GetOrderHeaderAsync(ctx1, resolvedOrderId),
      GetOrderMessagePaymentsInternalAsync(ctx2, resolvedOrderId),
      GetOrderPromotionInternalAsync(ctx3, resolvedOrderId),
      GetRewardItemsBatchedAsync(ctx4, resolvedOrderId, subOrderIds)
  );
Source:           incident2.cs, GetSubOrderAsync(), 2026-03-27
Related Pattern:  → Async Parallel DB Coordinator (#26)
Related Incident: → GetSubOrder Timeout Under High Concurrent Load
```

```
Name:             MapPayments / MapPromotions / MapRewardItems — In-Memory Mappers
Type:             Code Snippet
Language:         C# / EF Core
Purpose:          Pure in-memory mapping functions with no DbContext dependency.
                  Shared by both sync and async paths — zero duplication.
Pattern:          Map Function Extraction (decision-rules.md)
Key Rule:         Extract mapping to a private method when both sync and async versions
                  need the same in-memory transformation. No DbContext in the mapper.
Source:           incident2.cs, MapPayments/MapPromotions/MapRewardItems, 2026-03-27
Related Pattern:  → Async Parallel DB Coordinator (#26)
Related Incident: → GetSubOrder Timeout Under High Concurrent Load
```

---

### KOS Relation Wiring

```
📎 Relations to create in Notion for this session:

Incidents:
- GetSubOrder Timeout (incident2.cs) → Knowledge: EF Core DbContext Thread Safety
- GetSubOrder Timeout (incident2.cs) → Pattern: Async Parallel DB Coordinator (#26)
- GetSubOrder Timeout (incident2.cs) → Decision: Use IDbContextFactory for parallel GetSubOrderAsync
- GetSubOrder Timeout (incident2.cs) → Tech Asset: GetSubOrderAsync snippet
- GetSubOrder Timeout (incident2.cs) → Tech Asset: MapPayments/MapPromotions/MapRewardItems

Knowledge:
- EF Core DbContext Thread Safety → Pattern: Async Parallel DB Coordinator (#26)
- EF Core DbContext Thread Safety → Incident: GetSubOrder Timeout (incident2.cs)

Patterns:
- Async Parallel DB Coordinator (#26) → Knowledge: EF Core DbContext Thread Safety
- Async Parallel DB Coordinator (#26) → Knowledge: Connection Pool Math
- Async Parallel DB Coordinator (#26) → Incident: GetSubOrder Timeout (incident2.cs)

Decision:
- Use IDbContextFactory → Knowledge: EF Core DbContext Thread Safety
- Use IDbContextFactory → Pattern: Async Parallel DB Coordinator (#26)
- Use IDbContextFactory → Incident: GetSubOrder Timeout (incident2.cs)
```
```