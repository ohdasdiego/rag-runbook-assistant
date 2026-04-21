# Runbook: Disk Space Alert

**Severity:** P2 (P1 if filesystem is 100% full on a production host)
**Owner:** Platform Infrastructure
**Related alerts:** `disk_usage_high`, `disk_full`, `inode_exhaustion`

## Overview

Triggered when a filesystem exceeds 85% usage or when inode exhaustion is detected. A full disk on a production host can cause service crashes, corrupted writes, and cascading failures.

## Initial Triage

1. Identify the host and mount point from the alert payload
2. SSH into the host immediately — do not wait

## Diagnostic Commands

```bash
# Overall disk usage by mount
df -h

# Check inode usage separately
df -i

# Find the largest directories quickly
du -h --max-depth=2 / 2>/dev/null | sort -hr | head -20

# Find files larger than 1GB
find / -type f -size +1G 2>/dev/null

# Check for deleted-but-held-open files (common cause of "mystery" usage)
lsof +L1
```

## Common Root Causes

### Log file growth
Most frequent cause. Check `/var/log/` and application log directories. Logs may have grown because:
- Log rotation is misconfigured or broken
- A service is logging at DEBUG level in production
- Rapid error loops are producing massive log volume

### Core dumps
Check `/var/crash/` and application-configured core dump directories. Each dump can be several GB.

### Docker / container storage
```bash
# Reclaim space from unused images, containers, volumes
docker system df
docker system prune -a --volumes
```

### Held-open deleted files
If `lsof +L1` shows files with large sizes still held open by a process, restarting that process will release the space. Common offender: a log file rotated but the service still has the old file open.

## Safe Remediation

1. **Before deleting anything, confirm it is safe** — check ownership, modification time, whether a service depends on it
2. For log files, truncate rather than delete if the service has it open:
   ```bash
   truncate -s 0 /var/log/app/application.log
   ```
3. Rotate logs manually if needed:
   ```bash
   logrotate -f /etc/logrotate.conf
   ```
4. Clear package manager caches:
   ```bash
   apt-get clean       # Debian/Ubuntu
   dnf clean all       # RHEL/Fedora
   ```

## Emergency Actions (100% full)

If the filesystem is at 100% and the host is unresponsive:

1. Identify the largest removable file and truncate (do not delete) it
2. Do not restart services until at least 5% free is recovered
3. If SSH itself is affected, use the console access for the cloud provider

## Post-Incident

- Review log rotation configuration for the affected service
- Consider adding earlier alerting at 75% threshold
- If the cause was unbounded growth from an application bug, file a follow-up ticket
