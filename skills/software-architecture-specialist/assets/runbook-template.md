# Runbook Template

> Triggered by: "generate a runbook", "create a runbook for X", "write an operational playbook", or after Incident Analysis.
> A runbook answers: (1) How do I know this is happening? (2) How do I diagnose what went wrong? (3) How do I fix it?
> Always generate the complete runbook. Write `[TO FILL — ...]` for unknowns. A partial runbook creates false confidence.

## Structure (8 sections, all required)

```
1. Header          — identity, owner, severity, last tested
2. Overview        — what this runbook covers (2 sentences)
3. Alert Condition — exactly what triggers this runbook
4. Detection       — confirm the issue is real
5. Diagnosis Tree  — step-by-step decision tree to root cause
6. Fix Procedures  — one procedure per root cause branch
7. Rollback        — how to undo the fix safely
8. Post-Incident   — KOS update, prevention, comms
```

---

## Template

```markdown
# Runbook: [System Name] — [Problem Name]

## Header

| Field | Value |
|-------|-------|
| System | [System name] |
| Severity | Low / Medium / High / Critical |
| Owner | [Team or person] |
| Last Updated | [YYYY-MM-DD] |
| Last Tested | [YYYY-MM-DD or "Never — test on next occurrence"] |
| Related Incident | [kos-incident.md entry] |
| Related KOS | [Knowledge / Pattern / Decision records] |

---

## Overview

[2 sentences: what problem this covers + which system/component is affected.
Example: "This runbook covers latency spikes in GetSubOrder caused by N+1 EF Core queries.
It applies when P99 > 500ms or DB queries per request > 50 on SubOrder Processing."]

---

## Alert Condition

**Trigger when:**
- [ ] [Metric]: [threshold] — e.g. `suborder_api_p99_latency > 500ms for 5 min`
- [ ] [Metric]: [threshold] — e.g. `suborder_db_queries_per_request > 50`
- [ ] [Manual]: [description] — e.g. "User reports slow order loading"

**Do NOT trigger for:**
- [Condition that looks similar but is a different problem]
- [Normal behaviour that innocuously fires the alert]

---

## Detection

**Step 1 — Confirm the alert is real**
```bash
# Check current P99 latency (last 10 min)
[Prometheus query or command]
# Healthy: < 100ms | Unhealthy: > 500ms sustained
```

**Step 2 — Scope the blast radius**
- [ ] Affecting all requests or a specific entity ID?
- [ ] One instance or all instances?
- [ ] When did it start? (check deployment log)
- [ ] Correlated traffic spike?

**Step 3 — Identify which component**
- [ ] Check service logs for error entries
- [ ] Check DB connection pool exhaustion
- [ ] Check for downstream dependency timeout (Kafka, external API)

---

## Diagnosis Tree

```
START: Alert confirmed
│
├─► Recent deployment (< 2h)? → YES → Fix A: Rollback
│
├─► DB query count elevated?  → YES → Fix B: N+1 Investigation
│
├─► DB connection pool errors? → YES → Fix C: Connection Pool Relief
│
├─► Downstream dependency timeout? → YES → Fix D: Dependency Timeout
│
└─► None match → Escalate + open new incident
```

---

## Fix Procedures

### Fix A: Rollback Deploy
**When**: Recent deployment coincides with alert start.

```bash
# 1. Identify previous stable version
[e.g. kubectl rollout history deployment/service-name]

# 2. Roll back
[e.g. kubectl rollout undo deployment/service-name]

# 3. Confirm rollback completed
[e.g. kubectl rollout status deployment/service-name]

# 4. Verify alert clears within 5 min
[Prometheus / monitoring check]
```

**ETA**: 5–10 min | **Risk**: Rollback may reintroduce a previous bug — check target version's known issues.

---

### Fix B: N+1 Query Investigation
**When**: DB query count per request is elevated (> 50).

```bash
# 1. Enable EF Core query logging (appsettings.json or feature flag)
"Logging": { "LogLevel": { "Microsoft.EntityFrameworkCore.Database.Command": "Information" } }

# 2. Identify endpoint generating excess queries
# Look for: "Executed DbCommand" lines in rapid succession per trace ID

# 3. Locate the loop + .Load() pattern
grep -rn "\.Load()" --include="*.cs"
grep -rn "\.Entry(" --include="*.cs"

# 4. Short-term: add AsNoTracking() to offending query + redeploy
# Long-term: replace .Load() in loop with batch IN query + Dictionary
# (See Tech Asset: Batch IN query snippet)
```

**ETA**: 15–30 min (mitigation) · 2–4 h (permanent fix)
**Risk**: AsNoTracking disables change tracking — safe for read-only paths; verify method doesn't write after reading.

---

### Fix C: Connection Pool Relief
**When**: Errors like "timeout waiting for connection from pool".

```bash
# 1. Identify which queries are holding connections
SELECT pid, now() - query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC
LIMIT 20;

# 2. Kill long-running queries if safe
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE now() - query_start > interval '30 seconds'
AND state = 'active';

# 3. Increase pool size temporarily (check current — default 100 in .NET)
# Connection string: Max Pool Size=150

# 4. Scale out service instances to distribute load
[e.g. kubectl scale deployment/service-name --replicas=3]
```

**ETA**: 5–15 min | **Risk**: Killing queries may leave partial writes — verify data consistency after.

---

### Fix D: Dependency Timeout
**When**: Kafka or external API is slow or unresponsive.

```bash
# 1. Check Kafka consumer lag
[e.g. kafka-consumer-groups.sh --describe --group service-consumer]

# 2. Check external API health
curl -w "%{time_total}" -o /dev/null -s [upstream-health-endpoint]

# 3. If Kafka lag growing — restart consumer (idempotent handlers assumed)
[e.g. kubectl rollout restart deployment/service-consumer]

# 4. If external API down — enable circuit breaker fallback
[feature flag or config change to return cached/default response]
```

**ETA**: 5–20 min | **Risk**: Consumer restart causes reprocessing from last committed offset — ensure handlers are idempotent.

---

## Rollback

**If any fix makes things worse:**

```bash
# 1. Revert the change immediately
[specific rollback command for the fix applied]

# 2. Restore previous config / deployment
[command]

# 3. Notify team
[Slack / comms channel]

# 4. Do NOT attempt a second fix without a new diagnosis step
# Return to Diagnosis Tree with updated information
```

**Decision rule**: If latency/error rate does not improve within 10 min of applying a fix → rollback and escalate.

---

## Post-Incident Checklist

```
[ ] Alert cleared and stable for 30+ min
[ ] Root cause confirmed (not just symptoms resolved)
[ ] Fix deployed and verified in production
[ ] KOS updated:
    [ ] Incident record created/updated in Notion
    [ ] Knowledge record created if new concept learned
    [ ] Pattern record updated if pattern was applied
    [ ] Tech Asset created if new snippet written
[ ] Runbook updated with any new diagnosis steps found during this incident
[ ] Prevention task created: [what change prevents recurrence]
[ ] Team communication sent: [summary, what was done, ETA for permanent fix]
[ ] New alert added if this could have been caught earlier with better metrics
```

---

## Maintenance Rules

- **Update after every use** — add missing diagnosis steps, remove steps that led nowhere
- **Test annually** — walk through detection steps in staging
- **Link to incidents** — every incident using this runbook linked in Header
- **Version in git** — commit runbook changes with incident ID in the message
```

---

## Filled Example — GetSubOrder Latency

```markdown
# Runbook: SubOrder Processing — GetSubOrder API Latency Spike

## Header

| Field | Value |
|-------|-------|
| System | SubOrder Processing |
| Severity | High |
| Owner | Backend Platform Team |
| Last Updated | 2024-XX-XX |
| Last Tested | Never — test on next occurrence |
| Related Incident | kos-incident.md → GetSubOrder API Latency Spike |
| Related KOS | K: N+1 Query Problem, Batch Query Pattern |

## Overview

Covers API latency spikes in GetSubOrder caused by EF Core lazy loading inside foreach loops.
Applies when P99 > 500ms or DB queries per request > 50 on the SubOrder Processing service.

## Alert Condition

**Trigger when:**
- [ ] `suborder_api_p99_latency_seconds > 0.5` for 5 consecutive minutes
- [ ] `suborder_db_query_count_per_request > 50` (if instrumented)
- [ ] On-call receives report of slow order loading from fulfillment team

**Do NOT trigger for:**
- Cold start spike after deployment (resolves within 60s)
- Single outlier > 500ms with no sustained pattern

## Detection

**Step 1 — Confirm**
`histogram_quantile(0.99, suborder_api_request_duration_seconds_bucket)`
Healthy: < 100ms | Unhealthy: > 500ms sustained over 5 min

**Step 2 — Scope**
- [ ] Check logs for trace IDs with duration > 500ms
- [ ] Check if specific SourceOrderId / SourceSubOrderId involved
- [ ] Check deployment history — release in last 2 hours?

**Step 3 — Identify component**
- [ ] Search logs for `OnError ---- GetSubOrder` entries
- [ ] Count "Executed DbCommand" lines per trace ID → if > 50: N+1 confirmed → Fix B

## Diagnosis Tree

```
START: Latency spike confirmed
├─► Recent deployment? → YES → Fix A: Rollback
├─► DB query count > 50 per request? → YES → Fix B: N+1 Investigation
├─► DB connection errors? → YES → Fix C: Connection Pool
└─► None match → Escalate, open new incident
```

## Fix B: N+1 Query (Primary Fix for This System)

**Known root cause** (from 2024 incident):
`.Entry(x).Reference(p).Load()` and `.Entry(x).Collection(p).Load()` inside item foreach in `GetSubOrderMessage()`.
Also: `Any() + FirstOrDefault()` double-query pattern.

**Short-term (15–30 min)**: Add `AsNoTracking()` to SubOrder query → redeploy → verify P99 drops below 200ms.

**Permanent fix (2–4 h)**: Replace all `.Load()` inside loops with batch IN + Dictionary.
See Tech Asset: "Batch load related entities with IN clause". Target: < 20 queries/request, < 100ms P99.

**Verify**: Enable EF logging, run test request, count "Executed DbCommand" lines.
Expected after fix: ≤ 10 queries per GetSubOrder call.

## Post-Incident Checklist

- [ ] Alert cleared 30+ min
- [ ] Query count per request confirmed < 20
- [ ] Incident record updated in Notion KOS
- [ ] Prevention: add "DB call in loop" to PR checklist gate
- [ ] Add query count metric to standard API dashboard
```

---

## Generation Rules

When generating a runbook from an incident:

1. Read `kos-incident.md` if incident is already logged — use Root Cause, Fix, and Prevention to populate directly
2. Populate all 8 sections — `[TO FILL — ...]` for unknowns, never skip
3. Make the Diagnosis Tree specific — generic trees are useless on-call at 2am
4. Every Fix Procedure needs: commands, ETA, and risk statement
5. End with KOS action: state exactly which Notion records to create/update after using this runbook
6. Suggest file path: `runbooks/[system-name]-[problem-slug].md`
