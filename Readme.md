# How to use Agent

### Option 1 — Install the .skill file (Recommended)

- Go to Claude.ai → Settings → Skills
- Upload software-architecture-specialist.skill
- The skill is now active in your conversations

Once installed, it triggers automatically — you don't need to say "use the skill". Just talk naturally:

```
"Review this code"           → Code Review mode
"I have a production issue"  → Incident Analysis mode
"Should I use Outbox here?"  → Pattern Guidance mode
"Generate a runbook for X"   → Runbook Generator mode
"How am I progressing?"      → Career Roadmap mode
```

### Option 2 — Use it directly from the Git repo

If you're working from the repo without installing, paste this at the start of any conversation:

```
Read the file software-architecture-specialist/SKILL.md and act as the 
Software Architecture Specialist described there.
```
Then paste the relevant reference file when needed — e.g. paste references/review-checklists.md when you want a code review.

### Day-to-day workflow

The intended rhythm is:

```
Write code → paste for Code Review → fix BLOCKs before merging

Hit a production issue → Incident Analysis → add to incident-log.md → generate Runbook

Make an architecture choice → write ADR using the Decision format → log in Notion KOS

Ask "what should I focus on?" → Career Roadmap progress check → 1 concrete next action
```

### Growing the skill over time

The real power comes from keeping the reference files updated. After every significant incident or decision:

```
1. Add the incident to  references/incident-log.md
2. Add new patterns to  references/patterns.md
3. Add new rules to     references/decision-rules.md
4. Commit to git        → your knowledge is versioned
```

The skill becomes more useful the more you feed it. Six months from now, incident-log.md is your personal evidence base. A year from now, decision-rules.md reflects your own architectural instincts, not just the defaults that ship today.