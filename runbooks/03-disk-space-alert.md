# Runbook: Disk Space Alert — claw-gateway1

**Service:** All ADOStack services (host-level storage)  
**Severity:** P2 (>80% warning) / P1 (>90% critical)  
**Alert source:** AI Incident Logger (port 5001) — DISK threshold alert → Telegram (chat ID: 6055821277)  
**Response time:** 30 min (P2) / 10 min (P1)

---

## Overview

claw-gateway1 runs on a single VPS disk (typically 25-50GB SSD). Disk pressure comes from six sources: application logs across 6 services, ChromaDB vector data, SQLite databases, Nginx access/error logs, Python venv packages, and /tmp accumulation. At 90%+ disk usage, SQLite writes fail, ChromaDB ingest aborts, and Nginx may stop serving — cascading all services to 502.

---

## Prerequisites

- SSH access: `ssh claw@161.35.229.80`
- `sudo` privileges (for Nginx log access and /tmp cleanup)
- Infra Monitor at https://monitor.ado-runner.com for current disk reading
- On-Call Assistant at https://oncall.ado-runner.com if escalation needed

---

## Triage

### 1. Get current disk reading from Infra Monitor

```bash
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | grep -A5 "disk"
```

Look for `disk_percent`, `disk_used_gb`, `disk_total_gb`.

### 2. SSH and get filesystem overview

```bash
ssh claw@161.35.229.80
df -h
df -h /   # Root partition detail
```

If root partition >80%, proceed immediately to remediation.

---

## Diagnostic Commands

```bash
# Top-level disk consumers (run from /)
sudo du -sh /* 2>/dev/null | sort -rh | head -15

# ADOStack project directories
du -sh /home/claw/Projects/*/
du -sh /home/claw/Projects/*/ | sort -rh

# Per-service log directories
du -sh /home/claw/Projects/ai-infra-monitor/logs/ 2>/dev/null
du -sh /home/claw/Projects/ai-incident-logger/logs/ 2>/dev/null
du -sh /home/claw/Projects/rag-runbook-assistant/logs/ 2>/dev/null
du -sh /home/claw/Projects/k8s-event-summarizer/logs/ 2>/dev/null
du -sh /home/claw/Projects/ai-incident-orchestrator/logs/ 2>/dev/null
du -sh /home/claw/Projects/oncall-assistant/logs/ 2>/dev/null

# ChromaDB vector store (can grow large after ingest)
du -sh /home/claw/Projects/rag-runbook-assistant/data/chroma/
du -sh /home/claw/Projects/rag-runbook-assistant/data/chroma/* 2>/dev/null | sort -rh

# SQLite databases
ls -lh /home/claw/Projects/ai-incident-logger/data/incidents.db
ls -lh /home/claw/Projects/oncall-assistant/data/oncall.db

# Nginx logs
sudo du -sh /var/log/nginx/
sudo ls -lh /var/log/nginx/

# System journal size
journalctl --disk-usage

# /tmp usage
du -sh /tmp/

# Python venvs (large but don't delete without care)
du -sh /home/claw/Projects/*/venv/ 2>/dev/null | sort -rh
```

---

## Common Root Causes

| Cause | Typical Size | Safe to Delete |
|-------|-------------|----------------|
| Application logs (no rotation) | 100MB–5GB | Yes (old logs only) |
| Nginx access logs | 500MB–2GB | Yes (rotate/truncate) |
| ChromaDB chroma/ dir growth | 200MB–2GB | Partial (re-ingest needed) |
| System journal bloat | 100MB–1GB | Yes (vacuum) |
| /tmp accumulation | 50MB–500MB | Yes |
| SQLite WAL files | Varies | Safe after VACUUM |
| Old Python venv packages | 300MB–1GB per venv | With caution |

---

## Remediation Steps

### Step 1: Rotate and truncate application logs (immediate, safe)

```bash
# Rotate logs for each service (keeps file, truncates content)
for svc in ai-infra-monitor ai-incident-logger rag-runbook-assistant k8s-event-summarizer ai-incident-orchestrator oncall-assistant; do
  LOG_DIR="/home/claw/Projects/$svc/logs"
  if [ -d "$LOG_DIR" ]; then
    echo "=== $svc ==="
    ls -lh $LOG_DIR/
    # Keep last 1000 lines of each log file, truncate the rest
    for f in $LOG_DIR/*.log; do
      [ -f "$f" ] && tail -1000 "$f" > "$f.tmp" && mv "$f.tmp" "$f" && echo "Truncated $f"
    done
  fi
done
```

### Step 2: Clean Nginx logs

```bash
# Compress old nginx logs
sudo gzip /var/log/nginx/access.log.1 2>/dev/null
sudo gzip /var/log/nginx/error.log.1 2>/dev/null

# Truncate current logs if >100MB
sudo ls -lh /var/log/nginx/
sudo truncate -s 0 /var/log/nginx/access.log
sudo truncate -s 0 /var/log/nginx/error.log
sudo nginx -s reopen   # Tell nginx to reopen log files
```

### Step 3: Vacuum system journal

```bash
sudo journalctl --vacuum-size=200M
sudo journalctl --disk-usage   # Confirm reduction
```

### Step 4: Clean /tmp

```bash
sudo find /tmp -type f -mtime +1 -delete
sudo find /tmp -type d -empty -delete 2>/dev/null
du -sh /tmp/
```

### Step 5: SQLite VACUUM (reclaim deleted rows)

```bash
# Vacuum Incident Logger DB
sqlite3 /home/claw/Projects/ai-incident-logger/data/incidents.db "VACUUM;"
sqlite3 /home/claw/Projects/ai-incident-logger/data/incidents.db "PRAGMA wal_checkpoint(FULL);"

# Vacuum On-Call DB
sqlite3 /home/claw/Projects/oncall-assistant/data/oncall.db "VACUUM;"
sqlite3 /home/claw/Projects/oncall-assistant/data/oncall.db "PRAGMA wal_checkpoint(FULL);"
```

### Step 6: ChromaDB cleanup (if >500MB and runbooks haven't changed)

Only do this if disk is at critical (>90%) and other steps insufficient:

```bash
# Stop service, wipe chroma dir, re-ingest
sudo systemctl stop rag-runbook-assistant
rm -rf /home/claw/Projects/rag-runbook-assistant/data/chroma/*
cd /home/claw/Projects/rag-runbook-assistant && venv/bin/python3 ingest.py
sudo systemctl start rag-runbook-assistant
```

### Step 7: Set up log rotation (permanent fix)

```bash
# Create logrotate config for ADOStack services
sudo tee /etc/logrotate.d/adostack << 'EOF'
/home/claw/Projects/*/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
sudo logrotate -f /etc/logrotate.d/adostack
```

---

## Verification

```bash
# Disk should be below 80% threshold
df -h /

# Confirm Infra Monitor picks up the change (next 30-min cycle)
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool | grep disk_percent

# Verify all services still running after any ChromaDB wipe
for port in 5000 5001 5002 5003 5004 5005; do
  echo -n "Port $port: "
  curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/api/status
  echo
done
```

---

## Escalation

If disk >90% and cannot be cleared below 85% within 10 minutes:

1. Open P1 incident via On-Call Assistant
2. Consider resizing VPS disk via DigitalOcean control panel (requires reboot)
3. Emergency: delete oldest ChromaDB collection and re-ingest only current runbooks

---

## Post-Incident

```bash
# Document disk baseline after cleanup
df -h && du -sh /home/claw/Projects/*/

# Verify logrotate is in place
cat /etc/logrotate.d/adostack

# Check next Infra Monitor reading confirms GREEN disk
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool
```

Schedule periodic disk review via Infra Monitor dashboard. Set logrotate as permanent measure to prevent recurrence.
