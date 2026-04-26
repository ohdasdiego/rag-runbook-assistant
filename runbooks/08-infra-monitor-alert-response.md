# Runbook: AI Infra Monitor Alert Response

**Service:** AI Infra Monitor (port 5000, https://monitor.ado-runner.com)  
**Severity:** P2 (YELLOW) / P1 (RED)  
**Alert source:** AI Infra Monitor → webhook → On-Call Assistant; Telegram Telegram alert  
**Response time:** 15 min (YELLOW) / 5 min (RED)

---

## Overview

The AI Infra Monitor collects CPU, memory, and disk metrics from claw-gateway1 every 30 minutes via cron, runs Claude AI analysis, and emits a GREEN/YELLOW/RED status. When YELLOW or RED, it fires a webhook to the On-Call Assistant (port 5005) and sends a Telegram alert to Diego Perez (chat ID: 6055821277). A 30-minute cooldown prevents alert flooding. This runbook covers reading the alert payload, distinguishing false positives, manually triggering analysis, and verifying the alert pipeline.

**Monitor project:** `/home/claw/Projects/ai-infra-monitor/`  
**Alert state file:** `/home/claw/Projects/ai-infra-monitor/data/alert_state.json`  
**Collector script:** `/home/claw/Projects/ai-infra-monitor/collector.py`  
**Analyzer script:** `/home/claw/Projects/ai-infra-monitor/analyzer.py`

---

## Prerequisites

- SSH access: `ssh claw@161.35.229.80`
- AI Infra Monitor running: `sudo systemctl status ai-infra-monitor`
- On-Call Assistant running: `sudo systemctl status oncall-assistant`
- Telegram bot operational

---

## Understanding GREEN / YELLOW / RED

| Status | CPU | Memory | Disk | Action Required |
|--------|-----|--------|------|-----------------|
| GREEN | <80% | <85% | <80% | None — log and continue |
| YELLOW | 80–95% | 85–92% | 80–90% | Investigate within 15 min |
| RED | >95% | >92% | >90% | Act immediately, P1 |

The AI analysis enriches raw numbers with contextual recommendations. Always read `ai_analysis` before acting.

---

## Reading the /api/metrics Payload

```bash
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool
```

Key fields to read:

```json
{
  "timestamp": "2026-04-26T00:00:00Z",
  "cpu_percent": 76.2,
  "mem_percent": 81.4,
  "mem_used_gb": 3.26,
  "mem_total_gb": 4.0,
  "disk_percent": 68.1,
  "disk_used_gb": 17.0,
  "disk_total_gb": 25.0,
  "ai_analysis": {
    "severity": "YELLOW",
    "summary": "Memory pressure building. Gunicorn worker count likely too high for 4GB host.",
    "recommendations": [
      "Reduce gunicorn workers on ai-incident-orchestrator to 1",
      "Check for memory leak in rag-runbook-assistant"
    ],
    "risk_level": "MEDIUM"
  }
}
```

Always read `ai_analysis.recommendations` — Claude provides context the raw numbers don't.

```bash
# Just the AI analysis section
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('ai_analysis',{}), indent=2))"

# Just severity
curl -s https://monitor.ado-runner.com/api/status | python3 -m json.tool
```

---

## Diagnostic Commands

```bash
# Check alert state (last sent alert, cooldown status)
cat /home/claw/Projects/ai-infra-monitor/data/alert_state.json | python3 -m json.tool

# Review collector output
tail -50 /home/claw/Projects/ai-infra-monitor/logs/collector.log 2>/dev/null || \
  journalctl -u ai-infra-monitor --since "1 hour ago" | tail -50

# Check analyzer output
tail -50 /home/claw/Projects/ai-infra-monitor/logs/analyzer.log 2>/dev/null

# Confirm cron is scheduled (collector runs every 30 min)
crontab -l | grep collector
sudo crontab -l | grep collector

# Verify webhook to On-Call Assistant is configured
grep -r "oncall\|5005\|webhook" /home/claw/Projects/ai-infra-monitor/*.py /home/claw/Projects/ai-infra-monitor/*.json 2>/dev/null | head -10

# Check HMAC secret is set (webhook authentication)
grep -r "HMAC\|SECRET\|hmac" /home/claw/Projects/ai-infra-monitor/ 2>/dev/null | grep -v ".pyc" | head -5
```

---

## Common Root Causes

| Issue | Signal | Fix |
|-------|--------|-----|
| Stale metrics (>35 min old) | `timestamp` is old in /api/metrics | Run collector manually (see below) |
| Alert not firing | alert_state.json shows recent RED but no Telegram | Check webhook URL and HMAC config |
| False positive (spike during deploy) | CPU/mem spike for <5 min then drops | Check cooldown, dismiss in Telegram |
| Monitor service down | port 5000 not responding | `sudo systemctl restart ai-infra-monitor` |
| Cron not running | No recent log entries | Re-add cron entry |
| Claude API error in analyzer | `anthropic` error in logs | Check ANTHROPIC_API_KEY env var |
| On-Call webhook rejected | 401/403 in monitor logs | Verify HMAC secret matches oncall-assistant config |

---

## Manually Triggering Collector and Analyzer

Use this when metrics are stale or you need an immediate reading:

```bash
cd /home/claw/Projects/ai-infra-monitor

# Step 1: Run collector (gathers CPU/mem/disk, saves raw metrics)
source venv/bin/activate  # or: venv/bin/python3
venv/bin/python3 collector.py
echo "Exit code: $?"

# Step 2: Run analyzer (sends metrics to Claude, generates GREEN/YELLOW/RED + recommendations)
venv/bin/python3 analyzer.py
echo "Exit code: $?"

# Step 3: Verify updated metrics
curl -s http://localhost:5000/api/metrics | python3 -m json.tool
```

Check `data/alert_state.json` after analyzer runs:

```bash
cat /home/claw/Projects/ai-infra-monitor/data/alert_state.json | python3 -m json.tool
# Expected fields: last_status, last_alert_sent_at, cooldown_active
```

---

## How the Webhook to On-Call Assistant Works

1. `analyzer.py` determines severity (GREEN/YELLOW/RED)
2. If YELLOW or RED AND cooldown not active (30-min window):
   - POST to `http://localhost:5005/api/webhook/infra-alert`
   - Payload signed with HMAC secret
   - On-Call Assistant creates incident and sends Telegram alert
3. Cooldown resets after 30 min — prevents duplicate alerts for sustained issues
4. `alert_state.json` tracks last alert time and status

```bash
# Manually fire a test webhook (use with caution — creates a real incident)
PAYLOAD='{"severity":"YELLOW","cpu_percent":82,"mem_percent":87,"disk_percent":71,"summary":"Manual test alert"}'
HMAC=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $2}')
curl -s -X POST http://localhost:5005/api/webhook/infra-alert \
  -H "Content-Type: application/json" \
  -H "X-Signature: $HMAC" \
  -d "$PAYLOAD" | python3 -m json.tool
```

---

## Verifying alert_state.json

```bash
cat /home/claw/Projects/ai-infra-monitor/data/alert_state.json | python3 -m json.tool
```

Example healthy state (GREEN, no cooldown):
```json
{
  "last_status": "GREEN",
  "last_alert_sent_at": null,
  "cooldown_active": false,
  "last_collected_at": "2026-04-26T00:00:00Z"
}
```

Example post-alert state (cooldown active):
```json
{
  "last_status": "YELLOW",
  "last_alert_sent_at": "2026-04-26T00:05:00Z",
  "cooldown_active": true,
  "cooldown_expires_at": "2026-04-26T00:35:00Z"
}
```

If `cooldown_active: true` but issue is resolved, you can manually reset:
```bash
python3 -c "
import json, datetime
state = json.load(open('/home/claw/Projects/ai-infra-monitor/data/alert_state.json'))
state['cooldown_active'] = False
state['last_status'] = 'GREEN'
json.dump(state, open('/home/claw/Projects/ai-infra-monitor/data/alert_state.json','w'), indent=2)
print('Cooldown reset.')
"
```

---

## False Positive Handling

A false positive occurs when metrics spike briefly (deploy, cron job, ingest) and normalize within one collection cycle.

```bash
# Check if current live metrics are now normal
ps aux --sort=-%cpu | head -5
free -h
df -h /

# If metrics are now GREEN, manually run analyzer to update state
cd /home/claw/Projects/ai-infra-monitor && venv/bin/python3 analyzer.py

# Dismiss the incident in On-Call Assistant
curl -s -X POST https://oncall.ado-runner.com/api/incidents/<INCIDENT_ID>/status \
  -H "Content-Type: application/json" \
  -d '{"status": "RESOLVED", "note": "False positive — brief spike during scheduled ChromaDB ingest. System now GREEN."}'

# Reset cooldown if needed (see above)
```

---

## Re-Indexing Runbooks After Changes

When runbooks are updated, re-index them in the RAG Runbook Assistant:

```bash
cd /home/claw/Projects/rag-runbook-assistant
venv/bin/python3 ingest.py

# Verify re-index succeeded
curl -s -X POST http://localhost:5002/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "infra monitor alert_state.json cooldown"}' | python3 -m json.tool
```

---

## Verification

```bash
# Confirm monitor is healthy
sudo systemctl is-active ai-infra-monitor
curl -s http://localhost:5000/api/status | python3 -m json.tool

# Confirm metrics are fresh
curl -s http://localhost:5000/api/metrics | python3 -m json.tool | grep "timestamp\|last_collected"

# Confirm alert_state reflects current truth
cat /home/claw/Projects/ai-infra-monitor/data/alert_state.json | python3 -m json.tool

# Confirm On-Call Assistant received and processed the webhook
curl -s https://oncall.ado-runner.com/api/incidents?limit=3 | python3 -m json.tool
```

---

## Escalation

If AI Infra Monitor itself is failing (port 5000 down, analyzer crashing):

```bash
sudo systemctl restart ai-infra-monitor
journalctl -u ai-infra-monitor --since "30 minutes ago" | tail -30

# If ANTHROPIC_API_KEY missing or expired:
sudo systemctl edit ai-infra-monitor   # Add Environment=ANTHROPIC_API_KEY=...
sudo systemctl daemon-reload && sudo systemctl restart ai-infra-monitor
```

If monitor cannot be restored in 10 minutes, manually check system health using raw commands (see runbooks 01, 02, 03) and open a manual On-Call incident.

---

## Post-Incident

```bash
# Confirm monitor GREEN
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | grep "severity\|cpu_percent\|mem_percent\|disk_percent"

# Review incident in On-Call Assistant — resolve cleanly
curl -s https://oncall.ado-runner.com/api/incidents | python3 -m json.tool | head -30

# Log findings in daily memory file
# Update alert thresholds if false positive rate is too high
grep -r "threshold\|CPU_THRESHOLD\|MEM_THRESHOLD\|DISK_THRESHOLD" /home/claw/Projects/ai-infra-monitor/ --include="*.py" --include="*.json" 2>/dev/null | head -10
```
