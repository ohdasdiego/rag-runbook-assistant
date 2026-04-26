# Runbook: Memory Pressure — claw-gateway1

**Service:** All ADOStack services (claw-gateway1 host-level)  
**Severity:** P2 (>85% warning) / P1 (>92% critical)  
**Alert source:** AI Incident Logger (port 5001) — MEM threshold alert → Telegram (chat ID: 6055821277)  
**Response time:** 15 min (P2) / 5 min (P1)

---

## Overview

claw-gateway1 has 4GB RAM shared across 6 gunicorn-backed Python services, ChromaDB, SQLite, Nginx, and system processes. At 85% (~3.4GB used), latency increases and swap pressure begins. At 92% (~3.7GB used), OOM-killer risk is imminent — it will kill the highest-memory process without warning, typically a gunicorn worker or ChromaDB.

---

## Prerequisites

- SSH access: `ssh claw@161.35.229.80`
- `sudo` privileges
- Infra Monitor accessible at https://monitor.ado-runner.com
- On-Call Assistant at https://oncall.ado-runner.com for incident creation

---

## Triage

### 1. Pull current memory reading from Infra Monitor

```bash
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | grep -A5 "memory"
```

Look for `mem_percent`, `mem_used_gb`, `mem_total_gb`, and `ai_analysis.severity`.

### 2. Check Incident Logger for alert history

```bash
curl -s https://incidents.ado-runner.com/api/incidents?limit=10 | python3 -m json.tool
```

Determine if this is a spike or gradual climb (memory leak pattern).

### 3. SSH and get live reading

```bash
ssh claw@161.35.229.80
free -h
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree|Cached|Buffers"
```

---

## Diagnostic Commands

```bash
# Top memory consumers
ps aux --sort=-%mem | head -20

# Gunicorn worker memory per service
ps aux | grep gunicorn | grep -v grep | awk '{print $6/1024 " MB\t" $11 " " $12 " " $13}'

# OOM killer history (critical — if present, a process already died)
journalctl -k | grep -i "oom\|killed process\|out of memory" | tail -20

# Swap usage
swapon --show
vmstat -s | grep -E "swap|memory"

# ChromaDB memory footprint (may hold vectors in RAM)
ps aux | grep chroma | grep -v grep

# SQLite files (disk only, but check for large mmap)
ls -lh /home/claw/Projects/ai-incident-logger/data/incidents.db
ls -lh /home/claw/Projects/oncall-assistant/data/oncall.db

# Page cache pressure
cat /proc/meminfo | grep -E "Cached|Buffers|Dirty|Writeback"
```

---

## Common Root Causes

| Cause | Signal |
|-------|--------|
| Too many gunicorn workers | Each worker holds ~150-250MB; 3 workers × 6 services = ~2.7GB baseline |
| ChromaDB vector cache growth | `rag-runbook-assistant` RSS grows after ingest or heavy query load |
| AI Orchestrator pipeline accumulation | 5-stage pipeline buffers large LLM responses in memory |
| Python memory leak (unreleased objects) | Service RSS grows monotonically over hours/days |
| OOM event already occurred | `journalctl -k` shows "killed process" entries |
| Swap exhausted | `free -h` shows swap 0B free |

---

## Remediation Steps

### Step 1: Drop page cache (safe, no service impact)

```bash
sync && sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
free -h   # Should recover buffer/cache memory immediately
```

This is always safe and often recovers 200-500MB on a busy system.

### Step 2: Reduce gunicorn workers on memory-heavy services

Priority order for reduction (heaviest consumers first):

```bash
# AI Incident Orchestrator (5-stage pipeline — most memory-hungry)
sudo systemctl edit ai-incident-orchestrator
# Under [Service], add to ExecStart or create override:
# ExecStart=... --workers 1 --threads 2 --worker-class gthread

# RAG Runbook Assistant (ChromaDB in-process)
sudo systemctl edit rag-runbook-assistant
# --workers 1

sudo systemctl daemon-reload
sudo systemctl restart ai-incident-orchestrator rag-runbook-assistant
```

### Step 3: Restart services with memory leaks

Restart in dependency-safe order (least critical first):

```bash
sudo systemctl restart k8s-event-summarizer
sleep 10
sudo systemctl restart ai-incident-logger
sleep 10
sudo systemctl restart ai-incident-orchestrator
sleep 10
sudo systemctl restart rag-runbook-assistant
sleep 10
sudo systemctl restart ai-infra-monitor
sleep 10
sudo systemctl restart oncall-assistant
```

After each restart, verify health:
```bash
sudo systemctl is-active <service>
```

### Step 4: Check and expand swap if needed

```bash
swapon --show
# If no swap or swap < 1GB:
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
# Make permanent: echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Step 5: If OOM event occurred — identify victim and restore

```bash
journalctl -k | grep "killed process" | tail -5
# Restart the killed service
sudo systemctl restart <affected-service>
sudo systemctl status <affected-service>
```

---

## Verification

```bash
# Memory should be below 85% within 2-3 minutes of restarts
watch -n 10 'free -h && echo "---" && ps aux --sort=-%mem | head -8'

# Confirm all 6 services responding
for port in 5000 5001 5002 5003 5004 5005; do
  echo -n "Port $port: "
  curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/api/status
  echo
done

# Wait for next Infra Monitor cycle and confirm
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | grep mem_percent
```

Target: `mem_percent` < 80% before closing the incident.

---

## Escalation

If memory remains >92% after all steps above:

1. Create P1 incident in On-Call Assistant:
   ```bash
   curl -s -X POST https://oncall.ado-runner.com/api/incidents \
     -H "Content-Type: application/json" \
     -d '{"title":"Critical memory pressure claw-gateway1","severity":"P1","description":"MEM >92% after remediation attempts, OOM imminent"}'
   ```
2. Prepare for emergency reboot: `sudo reboot` (2-3 min downtime, all services auto-restart via systemd)
3. Post-reboot: immediately check `journalctl -k` for OOM events before reboot

---

## Post-Incident

```bash
# Capture memory baseline after remediation
free -h
ps aux --sort=-%mem | head -15

# Review OOM logs to identify victim
journalctl -k | grep -i oom | tail -20

# Check for permanent worker count changes needed
grep -r "workers" /home/claw/Projects/*/gunicorn*.conf 2>/dev/null || true
grep -r "ExecStart" /etc/systemd/system/ai-*.service /etc/systemd/system/rag-*.service /etc/systemd/system/oncall-*.service /etc/systemd/system/k8s-*.service 2>/dev/null

# Log findings in incident
curl -s https://incidents.ado-runner.com/api/incidents | python3 -m json.tool | head -30
```

Consider adding swap permanently if not present. Document worker count changes in the relevant service unit files.
