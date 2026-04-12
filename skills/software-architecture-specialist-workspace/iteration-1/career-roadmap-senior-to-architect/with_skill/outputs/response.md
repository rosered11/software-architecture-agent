**Mode: Career Roadmap**

---

## Progress Check — Where You Are Now

Scoring the 6 indicators against your stated situation:

| Indicator | Your Status | Target |
|-----------|------------|--------|
| ADRs written | 0 | 10+ by Month 9 |
| KOS incidents fully logged | 0 | All incidents |
| Systems through design review | 0 | All systems by Month 3 |
| Runbooks exist | 0 | 1 per system by Month 3 |
| Trace ID propagation implemented | Unknown | Q2 |
| Design reviews led for others | 0 | Q3 |

Score: **0 / 6 started.** This is not a criticism — it is a clear starting line. You have 3 years of technical depth and zero architecture artifacts. That is exactly the gap between Senior Engineer and Architect.

---

## The Highest-Leverage Gap

**Domain 4: Decision Making & Architecture Documentation** is where to start.

From the competency map:

> "This is the highest-leverage gap. Architects are judged on their decisions, not their code."

You write code daily. That proves you can build. What you have not yet demonstrated is that you can *think ahead of the code* — capture context, compare options, document trade-offs, and make the decision reviewable by someone who wasn't in the room.

The fastest way to shift that perception — to yourself and to others — is to start writing ADRs on decisions you are already making.

---

## Why ADRs First (Not System Design Reviews, Not Runbooks)

System design reviews and runbooks are high-value, but they require either a dedicated block of time or a live incident. ADRs slot into work you are already doing.

Every week you make decisions:
- Should this be synchronous or async?
- Should we add a Kafka topic or call the service directly?
- Should this query batch or loop?
- Should this use EF Core or raw SQL?

Right now those decisions live in your head, in PR comments, or nowhere. An ADR forces you to name the context, list the options, state what you chose, and write one sentence about what you are sacrificing. That is it. One ADR per non-trivial decision.

The compounding effect: after 10 ADRs, you have a decision trail. You can see your own patterns. You can show a tech lead or hiring manager exactly how you think. You cannot fake that with code.

---

## Domain Connection

ADRs sit in **Domain 4** but immediately pull in:

- **Domain 1 (System Design)** — writing "Options considered" forces you to think about the system more completely than coding does
- **Domain 5 (Operational Maturity)** — the "Watch out for" section of an ADR is a pre-mortem; it is how architects avoid incidents before they happen
- **Domain 6 (Communication & Influence)** — a written ADR is influence without authority; it shapes decisions even when you are not in the meeting

---

## One Concrete Action to Start Today

Pick the last non-trivial technical decision you made this week — one where you chose between two real options. Write a 5-field ADR right now:

```
## ADR-001: [Decision Title]

Date: [today]
Status: Accepted

Context:
[What situation forced this decision? 2–3 sentences.]

Options Considered:
A. [Option A] — [one trade-off]
B. [Option B] — [one trade-off]

Decision:
[Which option and why — 1–2 sentences.]

Consequences:
[What you gain. What you give up. One sentence each.]
```

It does not need to be perfect. It needs to exist. Save it in Notion. That is ADR-001. From this point forward, every non-trivial decision gets one.

---

## Your Q1 Plan (First 3 Months)

**Month 1 — Make thinking visible**
- Write 1 ADR per week on decisions already being made (target: 4 ADRs)
- Start logging every production issue in KOS Incident format (Title, Root Cause, Fix, Lesson) — even minor ones
- Run the review checklist on every PR you touch; flag at least 1 architectural issue per sprint

**Month 2 — Extend to systems**
- Run the 7-dimension System Design Review on one existing system
- Write a runbook for that system
- Generate your first full KOS chain from an incident: I# → K# → P# → D# → TA#

**Month 3 — Lead one thing**
- Lead one design discussion — even informal, even 30 minutes — using the system design review scorecard as a guide
- Have an answer ready for: "What are the 3 biggest architectural risks in your systems right now?"

---

## The Mindset Shift That Unlocks Everything

| Still Engineer | Becoming Architect |
|---------------|-------------------|
| "Decisions are in the code." | "Decisions are written down before and after the code." |
| "I know why I chose this." | "Someone else can read why I chose this in 6 months." |
| "We can figure it out if it breaks." | "Here is the runbook for when it breaks." |

You do not need a new title to start operating at the next level. You need to make your thinking visible.

---

**Next Step:** Write ADR-001 today. Pick any recent decision. Use the 5-field template above. Everything else follows from there.

Would you like me to update `assets/career-roadmap.md` with your current Progress Check scores and set Month 1 targets based on this session?
