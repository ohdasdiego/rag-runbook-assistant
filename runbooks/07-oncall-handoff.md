# Runbook: On-Call Shift Handoff Procedure

**Service:** On-Call Assistant (port 5005), All ADOStack services 
**Severity:** P3 (routine) / P2 if open incidents exist 
**Alert source:** Scheduled shift transition 
**Response time:** Complete handoff within 15 minutes of shift start

---

## Overview

A clean shift handoff ensures the incoming engineer has full situational awareness of claw-gateway1, the Civo k3s cluster, and all 6 ADOStack services. This runbook defines the pre-handoff checklist, handoff note generation, Telegram format, access verification, and post-handoff confirmation. Skipping steps leads to blind spots and delayed incident response.

**On-Call Assistant:** https://oncall.ado-runner.com 
**On-Call DB:** `/home/claw/Projects/oncall-assistant/data/oncall.db` 
**Outgoing engineer:** completes checklist and generates notes 
**Incoming engineer:** verifies access and confirms receipt

---

## Prerequisites

- Both engineers have SSH access to `claw@161.35.229.80`
- Both have Telegram bot access (chat ID: 6055821277)
- Both can reach https://oncall.ado-runner.com
- On-Call Assistant service running: `sudo systemctl status oncall-assistant`

---

## Pre-Handoff Checklist (Outgoing Engineer)

Complete all checks before generating handoff notes. Mark each GREEN/YELLOW/RED.

### 1. Open Incidents Review

```bash
# List all non-resolved incidents
curl -s https://oncall.ado-runner.com/api/incidents | python3 -m json.tool | grep -E '"id"|"title"|"status"|"severity"'

# Any incidents in OPEN or INVESTIGATING?
curl -s "https://oncall.ado-runner.com/api/incidents?status=OPEN" | python3 -m json.tool
curl -s "https://oncall.ado-runner.com/api/incidents?status=INVESTIGATING" | python3 -m json.tool

# SQLite direct query for full view
sqlite3 /home/claw/Projects/oncall-assistant/data/oncall.db \
 "SELECT id, title, severity, status, created_at FROM incidents WHERE status != 'RESOLVED' ORDER BY created_at DESC;"
```

**Criteria for YELLOW handoff:** Any incident in MITIGATED state 
**Criteria for RED handoff:** Any incident in OPEN or INVESTIGATING — do not hand off until MITIGATED at minimum

### 2. AI Infra Monitor Status

```bash
# Current system metrics
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool

# Expected GREEN output will show:
# cpu_percent < 80, mem_percent < 85, disk_percent < 80
# ai_analysis.severity: "GREEN"

# Check when metrics were last collected
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | grep "timestamp\|last_updated\|collected_at"
```

Note the values in the handoff message. If YELLOW or RED, explain why.

### 3. K8s Cluster State

```bash
export KUBECONFIG=~/.kube/config

# Node status
kubectl get nodes -o wide

# All pods (filter out known demo failures)
kubectl get pods --all-namespaces | grep -v -E "broken-app|crashloop-demo|starved-pod"

# Any unexpected failures?
kubectl get pods --all-namespaces | grep -v -E "Running|Completed|broken-app|crashloop-demo|starved-pod"

# Recent events
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | grep Warning | grep -v -E "broken-app|crashloop-demo|starved-pod" | tail -10
```

Expected state: all non-demo pods Running, node Ready, no unexpected Warnings.

### 4. All 6 ADOStack Service Health

```bash
# Internal health check
for port in 5000 5001 5002 5003 5004 5005; do
 echo -n "Port $port: "
 STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:$port/api/status)
 echo "$STATUS"
done

# Systemd service states
systemctl is-active ai-infra-monitor ai-incident-logger rag-runbook-assistant k8s-event-summarizer ai-incident-orchestrator oncall-assistant

# Public URL check
for url in monitor incidents runbooks k8s orchestrator oncall; do
 echo -n "https://$url.ado-runner.com: "
 curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://$url.ado-runner.com/api/status
 echo
done
```

Any non-200 response must be explained in the handoff note.

### 5. Recent Alert History (last 4 hours)

```bash
curl -s https://incidents.ado-runner.com/api/incidents?limit=10 | python3 -m json.tool
sqlite3 /home/claw/Projects/oncall-assistant/data/oncall.db \
 "SELECT title, severity, status, created_at FROM incidents WHERE created_at > datetime('now', '-4 hours') ORDER BY created_at DESC;"
```

---

## Generating Handoff Notes

For each open/mitigated incident, generate a structured handoff note:

```bash
# Generate handoff note per incident
curl -s https://oncall.ado-runner.com/api/incidents/<INCIDENT_ID>/handoff | python3 -m json.tool
```

If no open incidents, generate a "clean handoff" summary:

```bash
curl -s https://oncall.ado-runner.com/api/incidents | python3 -m json.tool | head -20
# Document: "No open incidents. System GREEN."
```

---

## Telegram Handoff Message Format

Send this message to the shared ops Telegram chat after completing all checks:

```
 SHIFT HANDOFF — [DATE TIME UTC]

 Outgoing: [Name]
 Incoming: [Name]

 System Status:
• CPU: XX% [GREEN/YELLOW/RED]
• MEM: XX% [GREEN/YELLOW/RED]
• DISK: XX% [GREEN/YELLOW/RED]

 ADOStack Services: [ALL GREEN / X services degraded]
• monitor.ado-runner.com: [200/5xx]
• incidents.ado-runner.com: [200/5xx]
• runbooks.ado-runner.com: [200/5xx]
• k8s.ado-runner.com: [200/5xx]
• orchestrator.ado-runner.com: [200/5xx]
• oncall.ado-runner.com: [200/5xx]

 K8s Cluster: [NODE READY / issues]

 Open Incidents: [None / list with IDs]

 Watch items for incoming shift:
• [Any known issues, pending actions, or things to monitor]

 Handoff complete. Incoming engineer please confirm receipt.
```

---

## Incoming Engineer Verification

The incoming engineer must confirm all of the following within 10 minutes of handoff:

```bash
# 1. Verify SSH access
ssh claw@161.35.229.80 "uptime && date"

# 2. Verify Telegram bot active (send /start or check last message from bot)

# 3. Verify On-Call Assistant access
curl -s https://oncall.ado-runner.com/api/incidents | python3 -m json.tool | head -10

# 4. Confirm kubeconfig works
kubectl get nodes

# 5. Spot-check one live metric
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | grep -E "cpu_percent|mem_percent|disk_percent"
```

Reply to the handoff Telegram message: ` Access confirmed. Taking over. [Name]`

---

## Post-Handoff Verification (15 min after handoff)

```bash
# Incoming engineer: confirm no new alerts in first 15 min
curl -s "https://incidents.ado-runner.com/api/incidents?limit=3" | python3 -m json.tool

# Confirm Infra Monitor next cycle reflects clean state
curl -s https://monitor.ado-runner.com/api/status | python3 -m json.tool

# If any pre-existing MITIGATED incidents: continue monitoring for recurrence
curl -s "https://oncall.ado-runner.com/api/incidents?status=MITIGATED" | python3 -m json.tool
```

---

## Escalation

If handoff is blocked by an active P1 incident:
- Do NOT hand off until incident is at MITIGATED or RESOLVED
- Outgoing engineer stays on until stabilized
- Both engineers work in parallel if needed during stabilization
- Document the extended overlap in the incident notes:
 ```bash
 curl -s -X POST https://oncall.ado-runner.com/api/incidents/<ID>/status \
 -H "Content-Type: application/json" \
 -d '{"status": "INVESTIGATING", "note": "Handoff blocked — both engineers on call during P1 stabilization"}'
 ```

---

## Post-Incident

```bash
# At end of shift: full incident summary for daily ops log
sqlite3 /home/claw/Projects/oncall-assistant/data/oncall.db \
 "SELECT id, title, severity, status, created_at, updated_at FROM incidents WHERE date(created_at) = date('now') ORDER BY created_at;"

# Update memory/YYYY-MM-DD.md with shift summary and any lessons learned
```
