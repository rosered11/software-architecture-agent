# Career Roadmap — Software Engineer → Software Architect

> Triggered by: "how do I become an architect?", "what should I focus on?", "am I making progress?", Career Coaching mode.
> Goal: Software Architect in 2 years. Stack: .NET, Go, Kafka, PostgreSQL — microservices, data sync, event-driven.
> Every competency maps to real work — incidents, systems, decisions already in the KOS.

---

## Competency Map

### Domain 1: System Design

| Skill | What it means | Evidence | Gap |
|-------|--------------|----------|-----|
| Define flow + edge cases + failure modes | Every system has happy path, edge cases, and failure handling documented before coding | Stock Sync, SubOrder defined in Notion | FTP ETL failure modes incomplete |
| Choose the right architecture pattern | Select Outbox, CQRS, Saga based on concrete trade-offs, not familiarity | Outbox considered for Stock Sync | No CQRS decision documented |
| Design for scalability from the start | Identify O(n) risks and batch thresholds at design time, not after incident | GetSubOrder batch fix | No load estimation for FTP ETL |
| Make trade-offs explicit | Document what is sacrificed, not just what is chosen | GetSubOrder ADR: 3 options | Most decisions undocumented |

**Level → Target**: Intermediate (systems work, decisions implicit) → Senior (every non-trivial decision has an ADR; design review is a habit)

---

### Domain 2: Distributed Systems

| Skill | What it means | Evidence | Gap |
|-------|--------------|----------|-----|
| Event-driven design | Design Kafka flows with correct partition key, ordering guarantees, DLQ | Kafka in current systems | No partition key decisions documented |
| Data consistency across services | Know when to use Outbox, Saga, or direct calls | Outbox pattern known | No Saga designed yet |
| Failure isolation | One service failing must not cascade into others | — | Circuit breaker not implemented |
| Idempotency by default | All retryable operations safe to repeat without side effects | Awareness present | Not consistently applied |
| Observability across services | Trace ID propagation, cross-service correlation | Prometheus in use | No trace ID propagation confirmed |

**Level → Target**: Intermediate (work in distributed systems, don't design the contracts) → Senior (define event contracts, consistency boundaries, and failure isolation strategy)

---

### Domain 3: Performance & Optimization

| Skill | What it means | Evidence | Gap |
|-------|--------------|----------|-----|
| Diagnose N+1 and query patterns | Identify DB anti-patterns from code and metrics, not just production alerts | GetSubOrder — full root cause | |
| Batch and chunk large datasets | Know when and how to apply batch + chunk | GetSubOrder fix applied | FTP ETL chunking unconfirmed |
| Profile before optimizing | Measure query count and latency before writing any fix | EF Core logging used | No systematic profiling process |
| Write performance into design | Flag O(n) risks at design review, not post-incident | Review checklist available | Not yet consistent habit |

**Level → Target**: Intermediate-Advanced (can fix performance problems) → Senior (performance review is part of every PR and system design, not a post-incident activity)

---

### Domain 4: Decision Making & Architecture Documentation

| Skill | What it means | Evidence | Gap |
|-------|--------------|----------|-----|
| Write ADRs | Capture context, options, decision, trade-offs in structured form | GetSubOrder ADR | Only 1 ADR — most decisions undocumented |
| Evaluate options with trade-offs | Never choose without naming what you sacrifice | GetSubOrder: 3 options compared | Inconsistent on other decisions |
| Know when NOT to use a pattern | Anti-conditions matter as much as when to apply | Patterns include anti-conditions | Needs practice in real decisions |
| Build a decision audit trail | Past decisions are traceable and reviewable by anyone | Notion KOS Decision Log exists | Sparse — mostly empty |

**Level → Target**: Early (can write ADRs, rarely do) → Senior (every non-trivial choice has an ADR; decision trail is reviewable by anyone)

> **This is the highest-leverage gap.** Architects are judged on their decisions, not their code.

---

### Domain 5: Operational Maturity

| Skill | What it means | Evidence | Gap |
|-------|--------------|----------|-----|
| Root cause analysis | Find the real cause, not the symptom | GetSubOrder fully analysed | More incidents needed in KOS |
| Write and maintain runbooks | Operational playbooks that work at 2am without you | Template available | No runbooks written for live systems |
| Define and own SLAs | Know what "healthy" looks like and alert on deviation | Prometheus in use | No explicit SLA targets per system |
| Post-incident learning | Every incident generates Knowledge + Prevention record | KOS structure in place | Process not consistently followed |
| Proactive system review | Run pre-mortems before incidents happen | Design Review checklist available | Not yet applied to existing systems |

**Level → Target**: Reactive (handle incidents well, no proactive coverage) → Senior (every system has a runbook, SLA targets, and has been through a design review)

---

### Domain 6: Communication & Influence

| Skill | What it means | Evidence | Gap |
|-------|--------------|----------|-----|
| Explain trade-offs simply | Translate technical decisions into business impact | — | Not yet tracked |
| Lead a design review | Facilitate a structured review of another engineer's design | — | Not yet done |
| Write for future readers | ADRs, runbooks, system docs clear to someone new | Notion KOS structured | Content quality not evaluated |
| Influence without authority | Get buy-in for architectural changes without formal power | GetSubOrder fix adopted | More examples needed |

**Level → Target**: Not yet demonstrated → Senior (regularly lead design discussions; documentation referenced by others)

---

## 2-Year Roadmap

### Year 1 — Build the Foundation

**Q1 (Months 1–3): Establish the baseline**
```
[ ] Run System Design Review on all 3 existing systems (Stock Sync, SubOrder, FTP ETL)
    → Find gaps before they become incidents; generate ≥3 ADRs from findings
[ ] Write runbooks for all 3 systems (runbook-template.md; highest severity first)
[ ] Log every incident in KOS — no exceptions (Title, Root Cause, Fix, Lesson, Pattern)
[ ] Run review-checklists.md on every PR touched; flag ≥1 architectural issue per sprint
```

**Q2 (Months 4–6): Deepen distributed systems**
```
[ ] Design + implement Outbox pattern for ≥1 system; document as ADR with trade-offs
[ ] Define partition key strategy for all owned Kafka topics; add to kos-decisions.md
[ ] Add trace ID propagation to ≥1 service; verify on every log line; document as Tech Asset
[ ] Define SLA targets per system (P99 latency, error rate, consumer lag); add alerts
```

**Q3 (Months 7–9): Own architectural decisions**
```
[ ] Write ADR for every non-trivial decision going forward (target: 10+ ADRs by end Q3)
[ ] Lead ≥1 design review for another engineer using system-design-review.md
[ ] Apply batch + chunk to FTP ETL pipeline; profile before, document before/after metrics
[ ] Build one new pattern from scratch: identify recurring problem → name it → add to KOS
```

**Q4 (Months 10–12): Demonstrate architect thinking**
```
[ ] Present a system design proposal to the team (ADR format, options + trade-offs, buy-in via reasoning)
[ ] Audit KOS: every system has a design doc; every major incident has a full chain; every pattern has a record
[ ] Write a "State of the Systems" doc — one page per system: health, known risks, open decisions
[ ] Identify weakest domain; design a focused Q1 Year 2 plan to close it
```

---

### Year 2 — Demonstrate Architect-Level Thinking

**Theme**: Lead, not just do. Influence, not just fix.

```
Month 13–15: Communication & Influence
  → Lead 3+ design reviews
  → Write 1 internal technical blog post or design proposal
  → Mentor a junior engineer through an incident analysis

Month 16–18: Cross-system architecture
  → Design a change spanning 2+ services (event contracts, consistency boundary, rollback plan)
  → Write the ADR yourself; get senior review

Month 19–21: Proactive architecture
  → Identify a systemic risk across systems; propose + lead the solution
  → Track the outcome: did it prevent an incident?

Month 22–24: Architect readiness check
  → Answer without hesitation:
    "What are the 3 biggest risks in your systems right now?"
    "Walk me through the last 3 architectural decisions you made."
    "What would you change about your architecture if you could?"
  → Portfolio: ADRs, runbooks, system reviews, incident analyses = evidence for the architect conversation
```

---

## Progress Check Protocol

When asked "how am I doing?" or "what should I focus on next?":

```
1. How many ADRs in Notion?             Target: 10+ by Month 9
2. How many incidents fully logged?     Target: all of them
3. All 3 systems through design review? Target: Q1
4. How many runbooks exist?             Target: 1 per system by Month 3
5. Trace ID propagation implemented?    Target: Q2
6. ≥1 design review led for others?    Target: Q3
```

Score each: Done / In Progress / Not Started → identify the single highest-leverage action.

**The question that cuts through everything**:
> "If your tech lead asked you to explain the 3 biggest architectural risks in your systems right now — could you answer immediately, with evidence?"
> Yes → thinking like an architect. No → that is the gap to close first.

---

## Mindset Shifts

| Shift | Still Engineer | Becoming Architect |
|-------|---------------|-------------------|
| Scope | "This PR" | "This system over time" |
| Decisions | Implicit, in code | Explicit, in ADRs |
| Incidents | Stressful surprises | Expected — have a runbook |
| Patterns | Tools to use | Lenses to think with |
| Performance | "Does it pass tests?" | "What is the query count?" |
| Documentation | "The code is the docs" | "Future me needs this written" |
| Failure | "It shouldn't fail" | "How does it fail gracefully?" |
| Reviews | "Does it work?" | "What could go wrong in 6 months?" |
