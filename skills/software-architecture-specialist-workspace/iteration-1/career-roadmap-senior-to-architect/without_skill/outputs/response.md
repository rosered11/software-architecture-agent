# From Senior Developer to Software Architect: Where to Focus First

**Context:** 3 years as a senior developer, strong daily coding practice, no ADRs, no design leadership, no formal post-mortems.

## The Core Gap to Close

The difference between a senior developer and a software architect is not technical depth — you already have that. The gap is **decision ownership and communication**. Architects are accountable for choices that affect teams, systems, and business outcomes over months or years. The three things you listed — system design sessions, ADRs, and incident post-mortems — are exactly the three primary artifacts that demonstrate that accountability.

Focus there first.

## Priority 1: Start Writing Architecture Decision Records (ADRs)

**Why first:** ADRs are the lowest-friction entry point. You don't need a title change, a promotion, or anyone's permission. You can start today, on your current team.

**What to do:**
- Pick any significant technical decision your team made in the last 30 days and write an ADR for it retrospectively.
- Use a simple template: Context / Decision / Consequences (the Nygard format). One page maximum.
- Propose to your team that all future non-trivial decisions get an ADR. Volunteer to write the first three.

**Concrete goal:** Write one ADR per week for the next 8 weeks.

## Priority 2: Lead at Least One System Design Session

**Why second:** Design sessions expose the political and collaborative dimension of architecture. Find an upcoming feature or migration, volunteer to facilitate the design meeting, prepare a one-page problem statement, and write the ADR afterward.

## Priority 3: Write One Formal Incident Post-Mortem

**Why third:** Post-mortems teach you to reason about system failure at the structural level. Use a blameless format: timeline, contributing factors, systemic root cause, and action items with owners.

## A Realistic 90-Day Plan

| Weeks | Focus |
|-------|-------|
| 1–2 | Write 2 retrospective ADRs on past decisions |
| 3–4 | Propose ADR practice to team; identify a design opportunity |
| 5–8 | Lead one system design session; write the ADR from it |
| 9–12 | Own the next incident post-mortem end-to-end |

By week 12 you will have a concrete portfolio that a promotion committee or architect hiring manager will ask to see.
