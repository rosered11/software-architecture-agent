---
name: Project: Software Architecture Agent
description: Overview of the KOS system, Notion sync pipeline, file structure, and tech stack for this project
type: project
---

A Claude Code skill project for a **Software Architecture Specialist** agent.

**Why:** Serves as a personal knowledge operating system (KOS) for architecture decisions, incidents, patterns, and reusable tech assets — all synced to Notion.

**How to apply:** Use this as orientation context when navigating the repo or when the user asks about any KOS file, sync behavior, or Notion integration.

---

## Repository Layout

```
skills/software-architecture-specialist/
├── SKILL.md                        # Agent definition and mode dispatch
├── memory/                         # Claude reads only — never synced to Notion
│   ├── feedback_notion_sync_standard.md  # Notion sync rendering rules (ALWAYS apply)
│   └── project_overview.md              # This file — project context and layout
├── assets/
│   ├── career-roadmap.md
│   ├── notion-kos-template.md
│   └── runbook-template.md
└── references/
    ├── kos-incident.md             # I# records
    ├── kos-knowledge.md            # K# records
    ├── kos-patterns.md             # P# records
    ├── kos-decisions.md            # D# records
    ├── kos-tech-assets.md          # TA# records
    ├── review-checklists.md
    └── system-design-review.md

sync/
├── kos_sync.py                     # Main sync script → Notion
├── config.json                     # Notion API keys + DB IDs (gitignored)
├── config.example.json
└── requirements.txt
```

## Tech Stack

| Layer | Technology |
|---|---|
| API / Business | .NET (EF Core) |
| Background services | Go |
| Messaging | Kafka |
| Storage | PostgreSQL |
| Auth | Azure AD B2C |
| Observability | Prometheus + structured logs |

## KOS Record Counts (as of 2026-04-10)
- I# Incidents: I1–I6+
- K# Knowledge: K1–K32+
- P# Patterns: P1–P23+
- D# Decisions: D1–D17+
- TA# Tech Assets: TA1–TA20+

## Notion Sync
- Script: `sync/kos_sync.py`
- Triggered automatically by Claude Code hook on every KOS file edit
- Full sync standard in `memory/feedback_notion_sync_standard.md`
- Syncs 5 databases: Knowledge, Patterns, Decisions, Tech Assets, Incidents
- Memory files (`memory/`) are Claude-only — not synced to Notion
