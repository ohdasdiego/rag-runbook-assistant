# Runbook: High CPU Alert — claw-gateway1

**Service:** AI Infra Monitor, All ADOStack services  
**Severity:** P2 (>80% warning) / P1 (>95% critical)  
**Alert source:** AI Incident Logger (port 5001) via Telegram to Diego Perez (chat ID: 6055821277)  
**Response time:** 15 min (P2) / 5 min (P1)

---

## Overview

claw-gateway1 (161.35.229.80, Ubuntu 24.04, 4GB RAM, 2 vCPU) runs all 6 ADOStack services under systemd backed by gunicorn. Sustained CPU above 80% degrades API response times and can cause Nginx 504 timeouts to Cloudflare. Above 95%, services may become unresponsive and OOM-killer risk increases.

---

## Prerequisites

- SSH access: `ssh claw@161.35.229.80`
- `sudo` privileges for systemctl operations
- Telegram alerts configured and receiving (verify bot is alive if no alerts arrive)
- Access to https://monitor.ado-runner.com for dashboard view

---

## Triage

### 1. Check AI Infra Monitor metrics first (no SSH needed)

```bash
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool
curl -s https://monitor.ado-runner.com/api/status
```

Look for `cpu_percent`, `ai_analysis.severity`, and `recommendations` fields.  
If metrics are stale (>35 min old), the monitor cron may itself be failing — check that first.

### 2. Confirm alert via Incident Logger

```bash
curl -s https://incidents.ado-runner.com/api/incidents?limit=5 | python3 -m json.tool
```

Cross-reference the triggered threshold with live readings.

### 3. SSH and get a live snapshot

```bash
ssh claw@161.35.229.80
top -bn1 | head -20
uptime
```

---

## Diagnostic Commands

```bash
# Live CPU by process (top consumers)
ps aux --sort=-%cpu | head -20

# Per-service gunicorn process CPU
ps aux | grep gunicorn | grep -v grep

# CPU steal (cloud VPS over-provisioning indicator)
top -bn1 | grep "%Cpu" 

# Context switches / interrupts
vmstat 2 5

# Which systemd service is consuming most
systemctl status ai-infra-monitor ai-incident-logger rag-runbook-assistant k8s-event-summarizer ai-incident-orchestrator oncall-assistant

# Load average trend
cat /proc/loadavg

# Check for runaway cron jobs
ps aux | grep cron
journalctl -u cron --since "30 minutes ago"
```

---

## Common Root Causes

| Cause | Signal |
|-------|--------|
| Gunicorn worker storm | Many `gunicorn worker` PIDs, each >10% CPU |
| AI Orchestrator pipeline spike | Port 5004 service high during incident ingestion |
| ChromaDB embedding generation | `rag-runbook-assistant` CPU spike during ingest |
| Claude API call backlog | Analyzer loop in `ai-infra-monitor` stuck retrying |
| K8s poller tight loop | `k8s-event-summarizer` re-fetching cluster events |
| Nginx log growth causing I/O wait | High `wa%` in top with moderate CPU |
| Runaway cron collector | `/home/claw/Projects/ai-infra-monitor/collector.py` spawning duplicates |

---

## Remediation Steps

### Step 1: Identify the offending service

```bash
ps aux --sort=-%cpu | head -10
# Note the CMD column — maps to gunicorn app or python script
```

### Step 2: Per-service restart procedures (in safe order)

```bash
# Non-critical first (least dependencies)
sudo systemctl restart rag-runbook-assistant
sudo systemctl restart k8s-event-summarizer
sudo systemctl restart ai-incident-logger

# Core pipeline second
sudo systemctl restart ai-infra-monitor
sudo systemctl restart ai-incident-orchestrator
sudo systemctl restart oncall-assistant
```

Wait 15 seconds between restarts. Verify each with:

```bash
sudo systemctl is-active <service-name>
curl -s http://localhost:<port>/api/status
```

### Step 3: Reduce gunicorn workers if overloaded

Edit the systemd unit or gunicorn config:

```bash
sudo systemctl edit ai-incident-orchestrator
# Add: --workers 1 --threads 2
sudo systemctl daemon-reload && sudo systemctl restart ai-incident-orchestrator
```

### Step 4: Kill runaway processes (last resort)

```bash
# Find PID of runaway
ps aux --sort=-%cpu | head -5
kill -15 <PID>   # SIGTERM first
sleep 5
kill -9 <PID>    # SIGKILL if still alive
```

### Step 5: If CPU steal >10%, the VPS host is the problem

- Document the steal percentage from `top`
- Open ticket with DigitalOcean if sustained >15 min

---

## Verification

```bash
# CPU should drop within 60 seconds of restart
watch -n 5 'ps aux --sort=-%cpu | head -10'

# Confirm all services healthy
for port in 5000 5001 5002 5003 5004 5005; do
  echo -n "Port $port: "
  curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/api/status
  echo
done

# Confirm Infra Monitor registers GREEN
curl -s https://monitor.ado-runner.com/api/status | python3 -m json.tool
```

Cooldown window: wait 35 min for next Infra Monitor cron cycle to confirm GREEN status.

---

## Escalation

If CPU remains >80% after 3 restart attempts:

1. Open an incident via On-Call Assistant:
   ```bash
   curl -s -X POST https://oncall.ado-runner.com/api/incidents \
     -H "Content-Type: application/json" \
     -d '{"title":"High CPU claw-gateway1","severity":"P1","description":"CPU sustained >80% after service restarts"}'
   ```
2. Use Telegram action buttons on the incident alert to escalate
3. Consider rebooting as last resort: `sudo reboot` (expect 2-3 min downtime)

---

## Post-Incident

```bash
# Review logs for root cause
journalctl -u <offending-service> --since "1 hour ago" | tail -50

# Log the incident in Incident Logger
curl -s https://incidents.ado-runner.com/api/incidents | python3 -m json.tool

# Update MEMORY.md or daily note with findings
# Verify next Infra Monitor cycle shows GREEN
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool
```

Review whether gunicorn worker count needs permanent reduction via systemd unit file.
