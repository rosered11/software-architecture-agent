# CLAUDE.md

A Claude Code skill for a **Software Architecture Specialist** agent.
Contains no application code — only Markdown files defining agent behavior and a reference knowledge base.

Core loop: **Incident → Knowledge → Pattern → Decision → Reuse**

---

## Rules

- After every Incident Analysis, generate all 5 KOS records (I#, K#, P#, D#, TA#) without being asked.
- After saving any new record, immediately run cross-linking (see below). Never skip this step.
- Never modify `SKILL.md` unless explicitly asked.
- Never add a record to only one KOS file — incidents touch all 5.
- `kos-incident.md` and `kos-decisions.md` are the highest-value files — keep them current.

---

## Repository Structure

```
skills/software-architecture-specialist/
├── SKILL.md                        # Agent definition and mode dispatch logic
├── assets/
│   ├── career-roadmap.md           # 6-domain competency map + 2-year quarterly plan
│   ├── notion-kos-template.md      # Notion Knowledge Operating System templates
│   └── runbook-template.md         # Operational runbook template
└── references/
    ├── kos-incident.md             # I# — incident log: root cause, fix, before/after, results
    ├── kos-knowledge.md            # K# — concept and technology knowledge records
    ├── kos-patterns.md             # P# — solution blueprints with measured results
    ├── kos-decisions.md            # D# — decision log + DECISION RULES (thresholds, if/then)
    ├── kos-tech-assets.md          # TA# — reusable code snippets and templates
    ├── review-checklists.md        # Per-technology review checklists (EF Core, Kafka, Go, PostgreSQL, API, ETL)
    └── system-design-review.md     # 7-dimension scorecard for system audits
```

---

## KOS Record Format

All 5 files use the same structure:

```
### PREFIX#: Title

```
Key1:   Value
Key2:   Value
```

Rich markdown content here — Claude reads this, Notion ignores it.
```

Valid prefixes: `I` (incident), `K` (knowledge), `P` (pattern), `D` (decision), `TA` (tech asset).

**File → Notion database mapping:**

| File                        | Notion Database  |
|-----------------------------|------------------|
| `references/kos-incident.md`    | Incidents (I)    |
| `references/kos-knowledge.md`   | Knowledge (K)    |
| `references/kos-patterns.md`    | Patterns (P)     |
| `references/kos-decisions.md`   | Decisions (D)    |
| `references/kos-tech-assets.md` | Tech Assets (TA) |

The sync parser (`sync/kos_sync.py`) splits on `### (I|K|P|D|TA)\d+:` headers and reads only the first KV block per section. Everything below the KV block is Claude-only context.

The `## DECISION RULES` section in `kos-decisions.md` is Claude-only; it is never synced.

---

## Growing the Knowledge Base

After a significant incident or architecture decision, add records in this order:

1. `kos-incident.md` — `### I#: Title` + KV block + rich markdown
2. `kos-knowledge.md` — `### K#: Title` + KV block (new concept or insight)
3. `kos-patterns.md` — `### P#: Title` + KV block + rich markdown
4. `kos-decisions.md` — `### D#: Title` + KV block; add threshold rules under `## DECISION RULES`
5. `kos-tech-assets.md` — `### TA#: Name` + KV block (reusable snippet from the fix)

Commit after each update so knowledge is versioned.

---

## Cross-Linking (mandatory after every new record)

After saving a new record, add its ID to the `Related` field of every record it references.

Common missed back-links:
- New `P#` → update `I#` Related Pattern + `D#` Related Pattern
- New `D#` → update `I#` Related Decisions

Full checklist: `kos-decisions.md` → `## DECISION RULES → KOS Cross-Linking`.

---

## Editing the Skill

- `SKILL.md` controls mode dispatch — edit to add new modes or change trigger logic.
- Reference files (`references/`, `assets/`) are loaded on-demand per mode.

---

## Tech Stack

| Layer               | Technology                  |
|---------------------|-----------------------------|
| API / Business      | .NET (EF Core)              |
| Background services | Go                          |
| Messaging           | Kafka                       |
| Storage             | PostgreSQL                  |
| Auth                | Azure AD B2C                |
| Observability       | Prometheus + structured logs |
