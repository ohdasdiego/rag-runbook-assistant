# Runbook: ADOStack Service Down

**Service:** Any/all ADOStack services (ports 5000–5005)  
**Severity:** P1 (any production service unreachable)  
**Alert source:** AI Incident Logger Telegram alert, Cloudflare health check failure, or manual discovery  
**Response time:** 5 min

---

## Overview

All 6 ADOStack services run as gunicorn Python apps behind Nginx reverse proxy, fronted by Cloudflare. A 502/504 from the public URL means either (a) the systemd service is down, (b) gunicorn crashed/stopped binding, or (c) Nginx misconfiguration. This runbook covers triage and full restart for all services with correct dependency ordering.

**Service map:**
| Service | Systemd Unit | Port | Public URL |
|---------|-------------|------|-----------|
| AI Infra Monitor | `ai-infra-monitor` | 5000 | https://monitor.ado-runner.com |
| AI Incident Logger | `ai-incident-logger` | 5001 | https://incidents.ado-runner.com |
| RAG Runbook Assistant | `rag-runbook-assistant` | 5002 | https://runbooks.ado-runner.com |
| K8s Event Summarizer | `k8s-event-summarizer` | 5003 | https://k8s.ado-runner.com |
| AI Incident Orchestrator | `ai-incident-orchestrator` | 5004 | https://orchestrator.ado-runner.com |
| On-Call Assistant | `oncall-assistant` | 5005 | https://oncall.ado-runner.com |

---

## Prerequisites

- SSH access: `ssh claw@161.35.229.80`
- `sudo` privileges for systemctl and nginx
- Nginx configs in `/etc/nginx/sites-available/`
- All services configured for `Restart=on-failure` in systemd

---

## Triage

### 1. Determine scope (one service or all services)

```bash
# Quick health check all 6 ports from inside the server
for port in 5000 5001 5002 5003 5004 5005; do
  echo -n "Port $port: "
  curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:$port/api/status
  echo
done
```

- **All ports 000/timeout** → Nginx down or system-level issue
- **One port 000/timeout** → Single service down
- **All ports 200 but public URLs 502** → Nginx or Cloudflare issue

### 2. Check Nginx status

```bash
sudo systemctl status nginx
sudo nginx -t   # Test config validity
curl -s -o /dev/null -w "%{http_code}" http://localhost/   # Direct nginx health
```

### 3. Check all systemd service statuses

```bash
sudo systemctl status ai-infra-monitor ai-incident-logger rag-runbook-assistant k8s-event-summarizer ai-incident-orchestrator oncall-assistant
```

---

## Diagnostic Commands

```bash
# Detailed status of a specific service
sudo systemctl status ai-incident-orchestrator -l

# Recent logs for a service
journalctl -u ai-incident-orchestrator --since "30 minutes ago" --no-pager | tail -50

# Error log paths per service
tail -50 /home/claw/Projects/ai-infra-monitor/logs/app.log
tail -50 /home/claw/Projects/ai-incident-logger/logs/app.log
tail -50 /home/claw/Projects/rag-runbook-assistant/logs/app.log
tail -50 /home/claw/Projects/k8s-event-summarizer/logs/app.log
tail -50 /home/claw/Projects/ai-incident-orchestrator/logs/app.log
tail -50 /home/claw/Projects/oncall-assistant/logs/app.log

# Verify gunicorn is bound to the correct port
ss -tlnp | grep -E '5000|5001|5002|5003|5004|5005'

# Check gunicorn master process exists
ps aux | grep gunicorn | grep -v grep

# Nginx config for a specific service
sudo cat /etc/nginx/sites-available/ai-infra-monitor
sudo cat /etc/nginx/sites-available/oncall-assistant

# Check for port conflicts
sudo ss -tlnp | grep LISTEN | sort -k4

# Disk full? (causes write failures → service exit)
df -h /

# OOM kill?
journalctl -k | grep -i "killed process" | tail -10
```

---

## Common Root Causes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `systemctl status` shows `failed` | Crash / unhandled exception | Check logs, restart |
| Port not in `ss -tlnp` | gunicorn never started / exited | Check startup logs, restart |
| Port present, HTTP 500 | App exception in handler | Check app.log for traceback |
| Nginx `test failed` | Config syntax error | Fix nginx config, reload |
| All services down | Host reboot, disk full, or nginx crash | Full restart sequence |
| `Connection refused` on port | Service crashed after start | journalctl for crash reason |
| `ANTHROPIC_API_KEY` error in logs | Env var not set in systemd unit | Check unit environment |
| ChromaDB collection error | Corrupt chroma data dir | Wipe and re-ingest |

---

## Remediation Steps

### Scenario A: Single service down

```bash
SERVICE=ai-incident-orchestrator  # Replace with actual service

# Check why it failed
journalctl -u $SERVICE --since "1 hour ago" --no-pager | tail -30

# Restart it
sudo systemctl restart $SERVICE
sleep 5
sudo systemctl is-active $SERVICE
curl -s http://localhost:5004/api/status   # Adjust port
```

### Scenario B: All services down (full restart sequence)

Dependency order: Nginx → Infra Monitor → Incident Logger → Orchestrator → RAG → K8s → On-Call

```bash
# 1. Ensure Nginx is up
sudo systemctl restart nginx
sudo nginx -t && sudo systemctl reload nginx

# 2. Start foundation services
sudo systemctl restart ai-infra-monitor
sleep 10
sudo systemctl restart ai-incident-logger
sleep 10

# 3. Start pipeline services
sudo systemctl restart ai-incident-orchestrator
sleep 10
sudo systemctl restart rag-runbook-assistant
sleep 10
sudo systemctl restart k8s-event-summarizer
sleep 10

# 4. Start user-facing services
sudo systemctl restart oncall-assistant
sleep 5

# 5. Verify all
for port in 5000 5001 5002 5003 5004 5005; do
  echo -n "Port $port: "
  curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:$port/api/status
  echo
done
```

### Scenario C: Nginx 502 but service is running

```bash
# Test the nginx config
sudo nginx -t

# Check Cloudflare IPs are in the allowed list
sudo grep -n "allow" /etc/nginx/sites-available/*

# Reload nginx without downtime
sudo systemctl reload nginx

# Check if port mismatch in nginx config vs actual binding
sudo grep -n "proxy_pass" /etc/nginx/sites-available/*
ss -tlnp | grep -E '500[0-5]'
```

### Scenario D: Environment variable missing

```bash
# Check env vars in systemd unit
sudo systemctl cat ai-infra-monitor | grep -E "Environment|EnvironmentFile"

# Edit unit to add missing var
sudo systemctl edit ai-infra-monitor
# Add under [Service]:
# Environment=ANTHROPIC_API_KEY=sk-ant-...

sudo systemctl daemon-reload && sudo systemctl restart ai-infra-monitor
```

---

## Verification

```bash
# Full public URL health check
for url in monitor incidents runbooks k8s orchestrator oncall; do
  echo -n "https://$url.ado-runner.com: "
  curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://$url.ado-runner.com/api/status
  echo
done

# Confirm no systemd failures
systemctl --failed | grep -E "ai-|rag-|k8s-|oncall-"
```

---

## Escalation

If any service cannot be recovered after 3 restart attempts:
1. Open On-Call incident: `curl -X POST https://oncall.ado-runner.com/api/incidents ...`
2. Check GitHub for recent deployments: https://github.com/ohdasdiego
3. Roll back last commit if recent deploy broke the service:
   ```bash
   cd /home/claw/Projects/<service-dir>
   git log --oneline -5
   git checkout <previous-commit>
   sudo systemctl restart <service>
   ```

---

## Post-Incident

```bash
# Confirm Infra Monitor saw the outage and recovery
curl -s https://monitor.ado-runner.com/api/metrics | python3 -m json.tool

# Review all service logs for the outage window
journalctl --since "2 hours ago" -u ai-infra-monitor -u ai-incident-logger -u rag-runbook-assistant -u k8s-event-summarizer -u ai-incident-orchestrator -u oncall-assistant | grep -i "error\|critical\|exception" | tail -30

# Verify Incident Logger recorded the event
curl -s https://incidents.ado-runner.com/api/incidents?limit=5 | python3 -m json.tool

# Update On-Call incident to RESOLVED
curl -s -X POST https://oncall.ado-runner.com/api/incidents/<ID>/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution":"Service restarted, root cause: <cause>"}'
```
