# Runbook: Incident Lifecycle SOP — On-Call Assistant

**Service:** On-Call Assistant (port 5005, https://oncall.ado-runner.com)  
**Severity:** All severities (P1/P2/P3)  
**Alert source:** Manual creation, Telegram Telegram bot, webhook from AI Incident Orchestrator  
**Response time:** Immediate (incident management framework, not a technical alert)

---

## Overview

The On-Call Assistant manages the full ADOStack incident lifecycle from detection to resolution. Incidents flow through four states: `OPEN → INVESTIGATING → MITIGATED → RESOLVED`. Every significant operational event on claw-gateway1 or the Civo k3s cluster should have a corresponding On-Call incident for traceability, shift handoffs, and post-incident review.

**On-Call Assistant:** https://oncall.ado-runner.com  
**Database:** `/home/claw/Projects/oncall-assistant/data/oncall.db`  
**Telegram:** Alerts and action buttons to Diego Perez (chat ID: 6055821277)

---

## Prerequisites

- On-Call Assistant service running: `sudo systemctl status oncall-assistant`
- Telegram bot configured and receiving messages
- Access to https://oncall.ado-runner.com API
- `sqlite3` installed for DB inspection if needed

---

## When to Open an Incident

Open an incident for **any** of the following:

| Trigger | Severity | Method |
|---------|----------|--------|
| Infra Monitor fires CPU/MEM/DISK alert | P2 or P1 | Auto-webhook from Infra Monitor |
| Any ADOStack service returns non-200 | P1 | Manual or auto via Orchestrator |
| K8s real pod failure (not demo workloads) | P2 | Manual after K8s summarizer alert |
| Cloudflare reports origin down | P1 | Manual |
| Telegram alert received but no auto-incident created | Any | Manual |
| Planned maintenance that may cause alerts | P3 | Manual (preemptive) |

---

## Opening an Incident

### Method 1: API (recommended for automation)

```bash
curl -s -X POST https://oncall.ado-runner.com/api/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "High CPU on claw-gateway1",
    "severity": "P1",
    "description": "CPU at 96%, all ADOStack services degraded. Triggered by AI Incident Logger threshold breach.",
    "source": "manual"
  }' | python3 -m json.tool
```

Response includes `incident_id` — save this for all subsequent operations.

### Method 2: Telegram action button

When AI Incident Orchestrator or Infra Monitor fires a Telegram alert, action buttons will appear:
- **Open Incident** — creates OPEN incident automatically
- **Acknowledge** — transitions to INVESTIGATING
- **Dismiss** — marks as false positive (does NOT create incident)

### Method 3: Via AI Incident Orchestrator

The Orchestrator (port 5004) runs a 5-stage pipeline and auto-creates incidents for confirmed issues:

```bash
curl -s -X POST https://orchestrator.ado-runner.com/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"alert": "CPU 96%", "service": "claw-gateway1", "metrics": {...}}' \
  | python3 -m json.tool
```

---

## Incident State Transitions

### OPEN → INVESTIGATING

Criteria: An engineer has acknowledged the alert and begun active investigation.

```bash
INCIDENT_ID=<id>
curl -s -X POST https://oncall.ado-runner.com/api/incidents/$INCIDENT_ID/status \
  -H "Content-Type: application/json" \
  -d '{"status": "INVESTIGATING", "note": "SSH into claw-gateway1, checking top consumers"}' \
  | python3 -m json.tool
```

Via Telegram: Tap the **"Investigate"** action button on the incident message.

**Do not leave an incident in OPEN for >10 minutes without moving to INVESTIGATING.**

### INVESTIGATING → MITIGATED

Criteria: The immediate symptom is resolved (e.g., CPU dropped below 80%) but root cause analysis is still ongoing.

```bash
curl -s -X POST https://oncall.ado-runner.com/api/incidents/$INCIDENT_ID/status \
  -H "Content-Type: application/json" \
  -d '{"status": "MITIGATED", "note": "Restarted ai-incident-orchestrator. CPU now at 62%. Monitoring for recurrence."}' \
  | python3 -m json.tool
```

### MITIGATED → RESOLVED

Criteria: Root cause identified, fix confirmed, Infra Monitor shows GREEN, no recurrence in last 30 min.

```bash
curl -s -X POST https://oncall.ado-runner.com/api/incidents/$INCIDENT_ID/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "RESOLVED",
    "note": "Root cause: gunicorn worker leak in orchestrator. Fixed by restart + worker count reduction to 1. Infra Monitor GREEN at 14:35 UTC."
  }' | python3 -m json.tool
```

Via Telegram: Tap **"Resolve"** action button.

---

## Escalation Triggers

Escalate (open P1 and notify via Telegram) when:

- Service down for >5 minutes and restart not effective
- Memory pressure >92% with OOM events in `journalctl -k`
- Disk at >90% and cleanup not recovering space
- All 6 ADOStack services unreachable simultaneously
- K8s node NotReady (non-demo failure)
- INVESTIGATING state has been open >30 minutes with no progress

```bash
# Check if escalation needed (review INVESTIGATING incidents > 30 min)
curl -s https://oncall.ado-runner.com/api/incidents?status=INVESTIGATING | python3 -m json.tool
```

---

## Generating Handoff Notes

Before any shift transition, generate handoff notes for each open/mitigated incident:

```bash
# For each open incident
curl -s https://oncall.ado-runner.com/api/incidents/<INCIDENT_ID>/handoff | python3 -m json.tool
```

The handoff note includes: incident title, current state, timeline, actions taken, open questions, next steps.

---

## Shift Handoff Checklist

Before handing off:

- [ ] All incidents in INVESTIGATING have status notes with current findings
- [ ] No incident has been in OPEN for >15 min without acknowledgement
- [ ] Handoff notes generated for all open/mitigated incidents
- [ ] Infra Monitor last reading confirms GREEN or explains YELLOW/RED
- [ ] All 6 ADOStack services returning 200 at health endpoints
- [ ] K8s cluster state reviewed (only expected demo failures present)

---

## Closing an Incident Cleanly

```bash
# Verify incident list before closing
curl -s https://oncall.ado-runner.com/api/incidents?status=OPEN | python3 -m json.tool
curl -s https://oncall.ado-runner.com/api/incidents?status=INVESTIGATING | python3 -m json.tool

# Close each with a resolution note
curl -s -X POST https://oncall.ado-runner.com/api/incidents/$INCIDENT_ID/status \
  -H "Content-Type: application/json" \
  -d '{"status": "RESOLVED", "note": "<root cause and fix summary>"}' \
  | python3 -m json.tool

# Confirm the DB reflects the close
sqlite3 /home/claw/Projects/oncall-assistant/data/oncall.db \
  "SELECT id, title, status, updated_at FROM incidents ORDER BY updated_at DESC LIMIT 5;"
```

---

## Verification

```bash
# Confirm On-Call Assistant is healthy
curl -s https://oncall.ado-runner.com/api/status | python3 -m json.tool

# No incidents should be stuck in OPEN or INVESTIGATING past SLA
curl -s https://oncall.ado-runner.com/api/incidents | python3 -m json.tool

# Telegram bot responding (send /status to bot to verify)

# Infra Monitor confirms system healthy
curl -s https://monitor.ado-runner.com/api/status | python3 -m json.tool
```

---

## Post-Incident

```bash
# Full incident history for the day
sqlite3 /home/claw/Projects/oncall-assistant/data/oncall.db \
  "SELECT id, title, severity, status, created_at, updated_at FROM incidents WHERE date(created_at) = date('now') ORDER BY created_at;"

# Update daily ops notes
# Review whether AI Incident Orchestrator correctly classified and routed the incident
curl -s https://orchestrator.ado-runner.com/api/status | python3 -m json.tool
```

Use post-incident data to improve thresholds in AI Incident Logger and update runbooks in the RAG Runbook Assistant.
