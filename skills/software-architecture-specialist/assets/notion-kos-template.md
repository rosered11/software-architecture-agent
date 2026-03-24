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
```