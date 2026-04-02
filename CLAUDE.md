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
    ├── kos-incident.md             # I# incident log — root cause, fix, before/after, results
    ├── kos-knowledge.md            # K# concept and technology knowledge records
    ├── kos-patterns.md             # P# patterns — solution blueprints with measured results
    ├── kos-decisions.md            # D# decision log + ## DECISION RULES section (thresholds, if/then rules)
    ├── kos-tech-assets.md          # TA# reusable code snippets and templates
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
- `references/kos-incident.md` and `references/kos-decisions.md` are the highest-value files to keep current — they personalize the skill to the user's actual system history.

## Growing the Knowledge Base

After significant incidents or architecture decisions, update:
1. `references/kos-incident.md` — add the incident (`### I#: Title` + KV block + rich markdown)
2. `references/kos-knowledge.md` — add any new concept or technology insight learned (`### K#: Title` + KV block)
3. `references/kos-patterns.md` — add any new pattern discovered (`### P#: Title` + KV block + rich markdown)
4. `references/kos-decisions.md` — add new D# entries (KV block) and/or threshold rules under `## DECISION RULES`
5. `references/kos-tech-assets.md` — add reusable code snippets or templates extracted from the fix (`### TA#: Name` + KV block)

All 5 files use the same format: `### PREFIX#: Title` + KV block + optional rich markdown below.
Commit after each update so knowledge is versioned.

**Cross-linking rule — run after every new record:**
After saving a new record, go back and add its ID to the Related fields of every record it references.
Common missed back-links: new P# → update I# Related Pattern + D# Related Pattern; new D# → update I# Related Decisions.
Full checklist in `kos-decisions.md` under `## DECISION RULES → KOS Cross-Linking`.

## Notion Sync — CRITICAL

A PostToolUse hook (`sync/hook_filter.py`) syncs `kos-*.md` files to Notion automatically on every Edit/Write.

| Notion Database | File |
|-----------------|------|
| Incidents (I)   | `references/kos-incident.md` |
| Knowledge (K)   | `references/kos-knowledge.md` |
| Patterns (P)    | `references/kos-patterns.md` |
| Decisions (D)   | `references/kos-decisions.md` |
| Tech Assets (TA)| `references/kos-tech-assets.md` |

**File format (all 5 files use the same structure):**
```
### PREFIX#: Title

` `` `
Key1:   Value
Key2:   Value
` `` `

Rich markdown content here — Claude reads this, Notion ignores it.
```

- The Notion sync parser (`sync/kos_sync.py`) splits on `### (K|P|D|TA|I)\d+:` headers and reads only the first KV block per section. Everything below (rich markdown, `##` sections) is Claude-only.
- `kos-decisions.md` has an extra `## DECISION RULES` section after all D# entries — Claude context only, never synced.

**When adding a new record**, add `### PREFIX#: Title` + KV block + rich markdown to the correct file:
- New incident → `kos-incident.md`
- New concept / learning → `kos-knowledge.md`
- New pattern → `kos-patterns.md`
- New decision or threshold rule → `kos-decisions.md`
- New reusable snippet → `kos-tech-assets.md`

## Tech Stack the Skill Is Calibrated For

| Layer | Technology |
|-------|-----------|
| API / Business | .NET (EF Core) |
| Background services | Go |
| Messaging | Kafka |
| Storage | PostgreSQL |
| Auth | Azure AD B2C |
| Observability | Prometheus + structured logs |
