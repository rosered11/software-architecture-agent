# 📟 Runbook Template

> Read this file when the user asks to "generate a runbook", "create a runbook for X",
> "write an operational playbook", or after completing an Incident Analysis where
> a runbook should be created as the prevention artifact.
>
> A runbook answers three questions for the on-call engineer:
>   1. How do I know this is happening? (Detection)
>   2. How do I diagnose what exactly went wrong? (Diagnosis)
>   3. How do I fix it and make sure it stays fixed? (Resolution)
>
> Always generate the complete runbook. Never leave sections empty.
> If information is unknown, write [TO FILL — describe what to look for here].
> A partial runbook is worse than none — it creates false confidence.

---

## Runbook Structure

Every runbook has 8 sections. All are required.

```
1. Header          — identity, owner, severity, last tested
2. Overview        — what this runbook covers in 2 sentences
3. Alert Condition — exactly what triggers this runbook
4. Detection       — how to confirm the issue is real
5. Diagnosis Tree  — step-by-step decision tree to find root cause
6. Fix Procedures  — one procedure per root cause branch
7. Rollback        — how to safely undo the fix if it makes things worse
8. Post-Incident   — what to do after resolution (KOS, prevention, comms)
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
| Owner | [Team or person responsible] |
| Last Updated | [YYYY-MM-DD] |
| Last Tested | [YYYY-MM-DD or "Never — test on next occurrence"] |
| Related Incident | [Link to incident-log.md entry if exists] |
| Related KOS | [Knowledge / Pattern / Decision Log entries] |

---

## Overview

[2 sentences: what problem this runbook covers, and what system/component is affected.
Example: "This runbook covers latency spikes in the GetSubOrder API caused by N+1 query
patterns in EF Core. It applies to the SubOrder Processing service when response time
exceeds 500ms or DB query count per request exceeds 50."]

---

## Alert Condition

**Trigger this runbook when:**

- [ ] [Metric/alert name]: [threshold] — e.g. `suborder_api_p99_latency > 500ms for 5 min`
- [ ] [Metric/alert name]: [threshold] — e.g. `suborder_db_queries_per_request > 50`
- [ ] [Manual trigger]: [description] — e.g. "User reports slow order loading"

**Do NOT trigger for:**
- [Condition that looks similar but is a different problem]
- [Normal behavior that triggers the alert innocuously]

---

## Detection

**Step 1 — Confirm the alert is real (not a fluke)**

```bash
# Check current P99 latency (last 10 min)
[command or Prometheus query]
# Expected healthy: < 100ms
# Unhealthy: > 500ms sustained

# Check DB query count per request
[command or log query]
# Expected healthy: < 20 queries
# Unhealthy: > 100 queries
```

**Step 2 — Scope the blast radius**

- [ ] Is this affecting all requests or a specific OrderId / SubOrderId?
- [ ] Is this affecting one instance or all instances?
- [ ] When did it start? (check deployment log for recent releases)
- [ ] Is there a correlated spike in traffic volume?

**Step 3 — Identify which component**

- [ ] Check service logs for `OnError` entries
- [ ] Check for DB connection pool exhaustion
- [ ] Check for downstream dependency timeout (Kafka, external API)

---

## Diagnosis Tree

```
START: Alert triggered — latency / query spike confirmed
│
├─► Recent deployment in last 2 hours?
│   ├─► YES → [Go to Fix A: Rollback Deploy]
│   └─► NO  → Continue
│
├─► DB query count > 50 per request?
│   ├─► YES → [Go to Fix B: N+1 Query Investigation]
│   └─► NO  → Continue
│
├─► DB connection pool exhausted?
│   ├─► YES → [Go to Fix C: Connection Pool Relief]
│   └─► NO  → Continue
│
├─► Downstream dependency (Kafka / external API) timing out?
│   ├─► YES → [Go to Fix D: Dependency Timeout]
│   └─► NO  → Continue
│
└─► None of the above match → Escalate + open new incident
```

---

## Fix Procedures

### Fix A: Rollback Deploy

**When**: Recent deployment coincides with alert start time.

```bash
# 1. Identify the previous stable version
[command — e.g. kubectl rollout history deployment/suborder-api]

# 2. Roll back
[command — e.g. kubectl rollout undo deployment/suborder-api]

# 3. Confirm rollback completed
[command — e.g. kubectl rollout status deployment/suborder-api]

# 4. Verify alert clears within 5 minutes
[Prometheus / monitoring check]
```

**Expected time to resolve**: 5–10 minutes
**Risk**: Rolling back may reintroduce a previous bug — check the rollback target's known issues first.

---

### Fix B: N+1 Query Investigation

**When**: DB query count per request is elevated (> 50).

```bash
# 1. Enable EF Core query logging temporarily
# In appsettings.json (non-production) or via feature flag:
"Logging": {
  "LogLevel": {
    "Microsoft.EntityFrameworkCore.Database.Command": "Information"
  }
}

# 2. Identify the endpoint / method generating excess queries
# Look for log lines: "Executed DbCommand" in rapid succession for same request trace ID

# 3. Find the loop + .Load() pattern
# Search codebase:
grep -rn "\.Load()" --include="*.cs"
grep -rn "\.Entry(" --include="*.cs"

# 4. Apply batch fix (see Tech Asset: Batch IN query snippet)
# Short-term: add AsNoTracking() to the offending query
# Long-term: replace .Load() in loop with batch + dictionary
```

**Expected time to resolve**: 
- Short-term mitigation: 15–30 minutes (AsNoTracking + redeploy)
- Permanent fix: 2–4 hours (batch query refactor + PR review)

**Risk**: AsNoTracking disables change tracking — safe for read-only paths, verify the method doesn't write after reading.

---

### Fix C: Connection Pool Relief

**When**: DB connection pool is exhausted — errors like "timeout waiting for connection from pool".

```bash
# 1. Check current pool usage
[command or DB admin query]

# 2. Identify which service / query is holding connections
SELECT pid, now() - query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC
LIMIT 20;

# 3. Kill long-running queries if safe
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE duration > interval '30 seconds'
AND state = 'active';

# 4. Increase pool size temporarily (if under-configured)
# In connection string: Max Pool Size=50 (default is 100 in .NET — check current)

# 5. Scale out service instances to distribute connections
[command — e.g. kubectl scale deployment/suborder-api --replicas=3]
```

**Expected time to resolve**: 5–15 minutes
**Risk**: Killing queries may leave partial writes — verify data consistency after.

---

### Fix D: Dependency Timeout

**When**: Downstream service (Kafka, external API) is slow or unresponsive.

```bash
# 1. Check Kafka consumer lag
[command — e.g. kafka-consumer-groups.sh --describe --group suborder-consumer]

# 2. Check external API health (if applicable)
curl -w "%{time_total}" -o /dev/null -s [upstream-health-endpoint]

# 3. If Kafka lag growing — check consumer group for stuck partitions
# Restart consumer if stuck:
[command — e.g. kubectl rollout restart deployment/suborder-consumer]

# 4. If external API down — enable circuit breaker fallback
[feature flag or config change to return cached/default response]
```

**Expected time to resolve**: 5–20 minutes (depends on dependency recovery)
**Risk**: Consumer restart causes reprocessing from last committed offset — ensure handlers are idempotent.

---

## Rollback

**If any fix procedure makes things worse:**

```bash
# 1. Revert the change immediately
[specific rollback command for the fix applied]

# 2. Restore previous config / deployment
[command]

# 3. Notify team of rollback
[Slack / communication channel]

# 4. Do NOT attempt a second fix without a diagnosis step
# Return to Diagnosis Tree with new information
```

**Rollback decision rule**: If latency/error rate does not improve within 10 minutes of applying a fix, rollback and escalate.

---

## Post-Incident Checklist

Complete this after the issue is fully resolved:

```
[ ] Alert cleared and stable for 30+ minutes
[ ] Root cause confirmed (not just symptoms resolved)
[ ] Fix deployed and verified in production
[ ] KOS updated:
    [ ] Incident record created in Notion (or updated if existing)
    [ ] Knowledge record created if new concept learned
    [ ] Pattern record updated if pattern was applied
    [ ] Tech Asset created if new code snippet written
[ ] Runbook updated with any new diagnosis steps found during this incident
[ ] Prevention task created: [what code/config change prevents recurrence]
[ ] Team communication sent: [summary of what happened, what was done, ETA for permanent fix]
[ ] Monitoring: new alert added if this would have been caught earlier with better metrics
```

---

## Runbook Maintenance Rules

- **Update after every use** — add any diagnosis step that was missing, remove any that led nowhere
- **Test annually** — walk through the detection steps in a staging environment
- **Link to incidents** — every incident that uses this runbook should be linked in the Header
- **Version in git** — runbook changes should be committed with the incident ID in the commit message
```

---

## Filled Example — GetSubOrder Latency Runbook

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
| Related Incident | incident-log.md → GetSubOrder API Latency Spike |
| Related KOS | Knowledge: N+1 Query Problem, Batch Query Pattern |

---

## Overview

This runbook covers API latency spikes in the GetSubOrder endpoint caused by excessive
DB query generation from EF Core lazy loading patterns. It applies when P99 response time
exceeds 500ms or DB queries per request exceed 50, specifically on the SubOrder Processing service.

---

## Alert Condition

**Trigger this runbook when:**
- [ ] `suborder_api_p99_latency_seconds > 0.5` for 5 consecutive minutes
- [ ] `suborder_db_query_count_per_request > 50` (if instrumented)
- [ ] On-call receives report of slow order loading from fulfillment team

**Do NOT trigger for:**
- Cold start latency spike (first request after deployment — resolves within 60s)
- Single outlier request > 500ms with no sustained pattern

---

## Detection

**Step 1 — Confirm the alert is real**
Check Prometheus: `histogram_quantile(0.99, suborder_api_request_duration_seconds_bucket)`
Healthy: < 100ms | Unhealthy: > 500ms sustained over 5 min

**Step 2 — Scope**
- [ ] Search logs for trace IDs with duration > 500ms
- [ ] Check if specific SourceOrderId or SourceSubOrderId is involved
- [ ] Check deployment history — was there a release in the last 2 hours?

**Step 3 — Identify component**
- [ ] Search logs for `OnError ---- GetSubOrder` entries
- [ ] Count "Executed DbCommand" log lines grouped by trace ID
  — if > 50 per trace: N+1 confirmed, go to Fix B

---

## Diagnosis Tree

START: Latency spike confirmed
│
├─► Recent deployment? → YES → Fix A: Rollback
│
├─► DB query count > 50 per request? → YES → Fix B: N+1 Investigation
│
├─► DB connection errors in logs? → YES → Fix C: Connection Pool
│
└─► None match → Escalate, open new incident

---

## Fix B: N+1 Query (Primary Fix for This System)

**Root cause pattern** (known from 2024 incident):
`.Entry(x).Reference(p).Load()` and `.Entry(x).Collection(p).Load()` inside item foreach loop
in `GetSubOrderMessage()`. Also: `Any() + FirstOrDefault()` double-query pattern.

**Short-term (15–30 min)**:
Add `AsNoTracking()` to the SubOrder query — reduces EF tracking overhead immediately.
Redeploy. Verify latency drops below 200ms.

**Permanent fix (2–4 hours)**:
Replace all `.Load()` inside loops with batch IN query + Dictionary<id,entity>.
See Tech Asset: "Batch load related entities with IN clause".
Target: < 20 queries per request, < 100ms P99.

**Verify fix**:
Enable EF logging, run a test request, count "Executed DbCommand" lines.
Expected after fix: ≤ 10 queries per GetSubOrder call.

---

## Post-Incident Checklist

- [ ] Alert cleared 30+ min
- [ ] Query count per request confirmed < 20
- [ ] Incident record updated in Notion KOS
- [ ] Prevention: add "DB call in loop" to PR checklist gate
- [ ] Add query count metric to standard API dashboard
```

---

## Generation Rules for Claude

When generating a runbook from an incident:

1. **Read `references/incident-log.md`** if the incident is already logged — use Root Cause, Fix, and Prevention fields to populate the runbook directly
2. **Populate all 8 sections** — use `[TO FILL — ...]` for anything unknown rather than skipping
3. **Make the Diagnosis Tree specific** — generic trees are useless on-call at 2am
4. **Every Fix Procedure needs**: commands, expected resolution time, and risk statement
5. **End with KOS action**: state exactly which Notion records to create or update after using this runbook
6. **Suggest the file path**: `runbooks/[system-name]-[problem-slug].md` for saving in the repo