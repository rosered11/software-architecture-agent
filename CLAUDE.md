# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A Claude Code skill for a **Software Architecture Specialist** agent. It contains no application code — only Markdown files that define an AI agent's behavior and its reference knowledge base.

The core loop the skill teaches and applies:
> **Incident → Knowledge → Pattern → Decision → Reuse**

## Repository Structure

```
skills/software-architecture-specialist/
├── SKILL.md                        # Agent definition and mode dispatch logic
├── assets/
│   ├── career-roadmap.md           # 6-domain competency map + 2-year quarterly plan
│   ├── notion-kos-template.md      # Notion Knowledge Operating System templates
│   └── runbook-template.md         # Operational runbook template with GetSubOrder example
└── references/
    ├── decision-rules.md           # Concrete thresholds and if/then rules (query count, retry, cache TTL, etc.)
    ├── incident-log.md             # Real incident log — root cause, fix, before/after, results
    ├── patterns.md                 # 10 patterns with code examples for .NET/Go/Kafka/PostgreSQL
    ├── review-checklists.md        # Per-technology code review checklists (EF Core, Kafka, Go, PostgreSQL, API, ETL)
    └── system-design-review.md     # 7-dimension scorecard for system audits
```

## How the Skill Is Used

**Option 1 — Installed as a Claude skill** (`.skill` file upload in Claude.ai Settings → Skills)

**Option 2 — Direct from repo**: paste at the start of a conversation:
```
Read the file software-architecture-specialist/SKILL.md and act as the Software Architecture Specialist described there.
```
Then paste the relevant reference file (e.g. `references/review-checklists.md` for code review).

## Editing the Skill

- `SKILL.md` controls mode dispatch — edit it to add new modes or change how existing modes are triggered.
- Reference files (`references/`, `assets/`) are loaded on-demand per mode. They are meant to be kept updated as the user's real incidents and decisions accumulate.
- `references/incident-log.md` and `references/decision-rules.md` are the highest-value files to keep current — they personalize the skill to the user's actual system history.

## Growing the Knowledge Base

After significant incidents or architecture decisions, update:
1. `references/incident-log.md` — add the incident
2. `references/patterns.md` — add any new pattern discovered
3. `references/decision-rules.md` — add any new threshold or rule extracted

Commit after each update so knowledge is versioned.

## Tech Stack the Skill Is Calibrated For

| Layer | Technology |
|-------|-----------|
| API / Business | .NET (EF Core) |
| Background services | Go |
| Messaging | Kafka |
| Storage | PostgreSQL |
| Auth | Azure AD B2C |
| Observability | Prometheus + structured logs |
