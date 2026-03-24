# 🎯 Career Roadmap — Software Engineer → Software Architect

> Read this file when the user asks about career growth, "how do I become an architect?",
> "what should I focus on?", "am I making progress?", "what do I need to prove?",
> or when Career Coaching mode is triggered.
>
> This is not a generic learning list. It is a competency framework mapped directly
> to the user's real work — their systems, their incidents, their decisions.
> Every competency has: what it means, how to demonstrate it, and evidence already earned.
>
> Goal: Software Architect in 2 years.
> Current context: .NET, Go, Kafka, PostgreSQL — microservices, data sync, event-driven systems.

---

## The Architect Competency Map

There are 6 competency domains. Each has 3–5 specific skills.
For each skill: current evidence is tracked, gaps are identified, next actions are defined.

---

### Domain 1: System Design

The ability to design systems that are correct, scalable, and maintainable — before writing code.

| Skill | What it means | Evidence earned | Gap |
|-------|--------------|-----------------|-----|
| Define flow + edge cases + failure modes | Every system has happy path, edge cases, and failure handling documented | Stock Sync, SubOrder Processing defined in Notion | FTP ETL failure modes not fully documented |
| Choose the right architecture pattern | Select Outbox, CQRS, Saga, etc. based on concrete trade-offs | Outbox considered for Stock Sync events | No CQRS decision documented yet |
| Design for scalability from the start | Identify O(n) risks, batch thresholds, horizontal scale path | GetSubOrder batch fix addresses scalability | No load estimation done for FTP ETL |
| Make trade-offs explicit | Document what is sacrificed, not just what is chosen | GetSubOrder ADR documents 3 options | Most decisions still undocumented |

**Current level**: Intermediate — you design working systems but decisions are often implicit.
**Target**: Senior — every non-trivial decision has an ADR. System review is a habit, not a reaction.

---

### Domain 2: Distributed Systems

The ability to reason about systems that span multiple services, databases, and message queues.

| Skill | What it means | Evidence earned | Gap |
|-------|--------------|-----------------|-----|
| Event-driven design | Design Kafka flows with correct partition key, ordering guarantees, DLQ | Kafka used in current systems | No documented partition key decisions |
| Data consistency across services | Understand when to use Outbox, Saga, or direct calls | Aware of Outbox pattern | No Saga designed yet |
| Failure isolation | One service failing should not cascade | Circuit breaker not yet implemented | |
| Idempotency by default | All retryable operations are safe to repeat | Awareness present | Not consistently applied across services |
| Observability across services | Trace ID propagation, cross-service correlation | Prometheus in use | No trace ID propagation confirmed |

**Current level**: Intermediate — you work in distributed systems but don't yet design the contracts.
**Target**: Senior — you define the event contracts, consistency boundaries, and failure isolation strategy.

---

### Domain 3: Performance & Optimization

The ability to identify, diagnose, and fix performance problems — and prevent them in design.

| Skill | What it means | Evidence earned | Gap |
|-------|--------------|-----------------|-----|
| Diagnose N+1 and query patterns | Identify DB anti-patterns from code and metrics | GetSubOrder incident — full root cause found | |
| Batch and chunk large datasets | Know when and how to apply batch + chunk patterns | GetSubOrder fix applied | FTP ETL chunking not confirmed |
| Profile before optimizing | Measure query count and latency before writing a fix | EF Core logging used in GetSubOrder | No systematic profiling process defined |
| Write performance into design | Flag O(n) risks during design review, not after incident | System Design Review checklist now available | Not yet habit — needs consistent application |

**Current level**: Intermediate-Advanced — you can fix performance problems. The gap is catching them earlier.
**Target**: Senior — performance review is part of every PR and every system design, not a post-incident activity.

---

### Domain 4: Decision Making & Architecture Documentation

The ability to make explicit, reasoned decisions and document them for future reference and teams.

| Skill | What it means | Evidence earned | Gap |
|-------|--------------|-----------------|-----|
| Write ADRs | Capture context, options, decision, trade-offs in structured form | GetSubOrder batch query ADR created | Only 1 ADR documented — many decisions undocumented |
| Evaluate options with trade-offs | Never pick one option without naming what you lose | GetSubOrder: 3 options compared | Not consistent on other decisions |
| Know when NOT to use a pattern | Equally important as knowing when to use one | Patterns library includes anti-conditions | Needs practice in real decisions |
| Build a decision audit trail | Your past decisions are traceable and reviewable | Notion KOS Decision Log exists | Sparse — most decisions not logged yet |

**Current level**: Early — you can write ADRs but rarely do. The habit is not formed yet.
**Target**: Senior — every non-trivial architectural choice has an ADR. Your decision trail is reviewable by anyone.

**This is the highest-leverage gap to close.** Architects are judged on their decisions, not their code.

---

### Domain 5: Operational Maturity

The ability to run systems reliably in production — observability, incidents, runbooks, prevention.

| Skill | What it means | Evidence earned | Gap |
|-------|--------------|-----------------|-----|
| Root cause analysis | Find the real cause, not the symptom | GetSubOrder incident fully analysed | Needs more incidents documented in KOS |
| Write and maintain runbooks | Operational playbooks that work at 2am without you | GetSubOrder runbook template available | No runbooks written yet for live systems |
| Define and own SLAs | Know what "healthy" looks like and alert on deviation | Prometheus in use | No explicit SLA targets defined per system |
| Post-incident learning | Every incident generates a Knowledge + Prevention record | KOS structure in place | Process not yet consistently followed |
| Proactive system review | Run pre-mortems before incidents happen | System Design Review checklist available | Not yet applied to existing systems |

**Current level**: Reactive — you handle incidents well but systems lack proactive coverage.
**Target**: Senior — every system has a runbook, SLA targets, and has been through a design review.

---

### Domain 6: Communication & Influence

The ability to communicate architectural decisions to non-technical stakeholders and to mentor others.

| Skill | What it means | Evidence earned | Gap |
|-------|--------------|-----------------|-----|
| Explain trade-offs simply | Translate technical decisions into business impact | — | Not yet tracked |
| Lead a design review | Facilitate a structured review of another engineer's design | — | Not yet done |
| Write for future readers | ADRs, runbooks, and system docs are clear to someone new | Notion KOS structured | Content quality not yet evaluated |
| Influence without authority | Get buy-in for architectural changes without formal power | GetSubOrder fix adopted | More examples needed |

**Current level**: Not yet demonstrated — this domain needs intentional focus in Year 2.
**Target**: Senior — you regularly lead design discussions and your documentation is referenced by others.

---

## 2-Year Roadmap

### Year 1 — Build the Foundation (Months 1–12)

**Theme**: Close the reactive gaps. Make structured thinking a habit.

**Q1 — Months 1–3: Establish the baseline**
```
[ ] Run System Design Review on ALL 3 existing systems (Stock Sync, SubOrder, FTP ETL)
    → Find gaps before they become incidents
    → Generate at least 3 ADRs from the findings

[ ] Write runbooks for all 3 systems
    → Use runbook-template.md
    → Start with the highest-severity system first

[ ] Log every incident in KOS — no exceptions
    → Title, Root Cause, Fix, Lesson Learned, Related Pattern
    → Goal: 0 incidents without a KOS entry

[ ] Establish code review habit
    → Run review-checklists.md on every PR you touch
    → Flag at least 1 architectural issue per sprint
```

**Q2 — Months 4–6: Deepen distributed systems**
```
[ ] Design and implement Outbox pattern for at least 1 system
    → Document as ADR: why Outbox, what alternatives, what trade-offs
    → Add to Tech Assets in KOS

[ ] Define partition key strategy for all Kafka topics you own
    → Document reasoning in ADR
    → Add to decision-rules.md

[ ] Add trace ID propagation to at least 1 service
    → Verify trace ID appears on every log line
    → Document as Tech Asset

[ ] Define SLA targets for each system
    → Latency P99, error rate, consumer lag thresholds
    → Add alert for each
```

**Q3 — Months 7–9: Own architectural decisions**
```
[ ] Write an ADR for every non-trivial decision going forward
    → Target: 10+ ADRs in Notion Decision Log by end of Q3
    → Include at least 2 options with trade-offs in each

[ ] Lead at least 1 design review for another engineer's work
    → Use system-design-review.md as the framework
    → Write up findings as a design review document

[ ] Apply batch + chunk pattern to FTP ETL pipeline
    → Profile current performance first
    → Document before/after metrics in incident-log.md (even as a proactive finding)

[ ] Build one new pattern from scratch
    → Identify a recurring problem in your systems
    → Design a reusable solution, name it, document it in KOS Patterns
```

**Q4 — Months 10–12: Demonstrate architect thinking**
```
[ ] Present a system design proposal to your team
    → Use ADR format
    → Include options considered and explicit trade-offs
    → Get buy-in through reasoning, not authority

[ ] Audit your KOS: does it tell the story of your growth?
    → Every system has a design document
    → Every major incident has a full KOS chain
    → Every pattern you use has a record

[ ] Write a "State of the Systems" document
    → One page per system: health, known risks, open decisions
    → This is what architects produce — system ownership artifacts

[ ] Identify your weakest domain from the competency map
    → Design a focused Q1 Year 2 plan to close it
```

---

### Year 2 — Demonstrate Architect-Level Thinking (Months 13–24)

**Theme**: Lead, not just do. Influence, not just fix.

**Focus areas**:
```
Month 13–15: Communication & Influence
  → Lead 3+ design reviews
  → Write 1 internal technical blog post or design proposal
  → Mentor a junior engineer through an incident analysis

Month 16–18: Cross-system architecture
  → Design a change that spans 2+ services
  → Define the event contracts, consistency boundary, and rollback plan
  → Write the ADR yourself, get senior review

Month 19–21: Proactive architecture
  → Identify a systemic risk across your systems
  → Propose and lead the solution (not just implement it)
  → Track the outcome: did it prevent an incident?

Month 22–24: Architect readiness
  → Can you answer these without hesitation?
    - "What are the 3 biggest risks in your systems right now?"
    - "Walk me through the last 3 architectural decisions you made."
    - "What would you change about your current architecture if you could?"
  → Build a portfolio: ADRs, runbooks, system reviews, incident analyses
  → These are your evidence for the architect conversation
```

---

## Progress Check Protocol

When the user asks "how am I doing?" or "what should I focus on next?",
run through this assessment:

```
1. How many ADRs exist in Notion? (Target: 10+ by Month 9)
2. How many incidents are fully logged in KOS? (Target: all of them)
3. Have all 3 systems been through a System Design Review? (Target: Q1)
4. How many runbooks exist? (Target: 1 per system by Month 3)
5. Is trace ID propagation implemented? (Target: Q2)
6. Has at least 1 design review been led for another engineer? (Target: Q3)
```

Score each: Done / In Progress / Not Started
Then identify the single highest-leverage action to take next.

**The question that cuts through everything**:
> "If your tech lead asked you to explain the 3 biggest architectural risks in your systems
> right now — could you answer immediately, with evidence?"

If yes → you are thinking like an architect.
If no → that is the gap to close first.

---

## Mindset Shifts — Progress Markers

These are not skills to learn — they are ways of thinking to internalise.
Use them to self-assess honestly.

| Shift | Still Engineer | Becoming Architect |
|-------|---------------|-------------------|
| Scope | "This PR" | "This system over time" |
| Decisions | Implicit, in code | Explicit, in ADRs |
| Incidents | Stressful surprises | Expected — have a runbook |
| Patterns | Tools to use | Lenses to think with |
| Performance | "Does it pass tests?" | "What is the query count?" |
| Documentation | "The code is the docs" | "Future me needs this written down" |
| Failure | "It shouldn't fail" | "How does it fail gracefully?" |
| Reviews | "Does it work?" | "What could go wrong in 6 months?" |