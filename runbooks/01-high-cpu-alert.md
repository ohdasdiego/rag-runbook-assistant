# Runbook: High CPU Alert Response

**Severity:** P2
**On-call team:** Platform Infrastructure
**Related alerts:** `cpu_usage_high`, `cpu_saturation_critical`

## Overview

This runbook covers response procedures when a host or container reports sustained CPU usage above threshold (default: 85% for 5 minutes).

## Initial Triage

1. Confirm the alert in Grafana at `dashboards/infra/host-overview`
2. Identify the affected host or pod from the alert payload
3. Check whether the host is production, staging, or dev — production takes priority
4. Check related alerts (memory, disk I/O) to rule out cascading failure

## Diagnostic Commands

SSH into the affected host and run the following:

```bash
# Top processes by CPU
top -b -n 1 | head -20

# Identify long-running high-CPU processes
ps aux --sort=-%cpu | head -10

# Check load average trend
uptime

# For containerized workloads
docker stats --no-stream
```

## Common Root Causes

### Runaway process
A stuck or infinite-looping process. Identify the PID from `ps aux` and capture a stack trace with `py-spy dump --pid <PID>` for Python or `jstack <PID>` for Java before killing.

### Traffic spike
Check load balancer metrics. If traffic has genuinely increased, scale horizontally — do not simply kill processes.

### Noisy neighbor
On shared hosts, another workload may be consuming CPU. Check `cgroup` limits with `systemd-cgtop`.

## Remediation Steps

1. If a runaway process is identified and safe to restart: `systemctl restart <service>`
2. If traffic is legitimate: trigger horizontal scale-out via `kubectl scale deployment/<name> --replicas=+2`
3. If cause is unclear: capture diagnostics, then failover to a healthy replica

## Escalation

- After 15 minutes without resolution: page the platform lead
- If customer-facing impact is confirmed: declare an incident via the incident channel and promote to P1

## Post-Incident

- File a post-mortem ticket within 24 hours
- Update this runbook if new failure modes were identified
