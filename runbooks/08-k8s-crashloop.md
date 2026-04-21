# Runbook: Kubernetes Pod CrashLoopBackOff

**Severity:** P2 (P1 if it affects all replicas of a critical service)
**Owner:** Platform Infrastructure
**Related alerts:** `pod_crashloopbackoff`, `deployment_unavailable`

## Overview

A pod is repeatedly crashing and being restarted by Kubernetes. The backoff timer increases with each restart (10s, 20s, 40s... up to 5 minutes).

## Initial Triage

```bash
# Identify the crashing pod
kubectl get pods -n <namespace> | grep -i crashloop

# Get detailed pod events
kubectl describe pod <pod-name> -n <namespace>

# Logs from the current (crashed) container
kubectl logs <pod-name> -n <namespace>

# Logs from the previous container — often has the actual error
kubectl logs <pod-name> -n <namespace> --previous
```

## Common Root Causes

### Application error on startup
Check the `--previous` logs. Most crashloops reveal themselves in the first 100 lines of previous-container logs: missing config, failed database connection, panic on boot.

### Missing secret or ConfigMap
`kubectl describe pod` will show an event like `MountVolume.SetUp failed for volume "config": configmap "app-config" not found`.

**Fix:** Verify the referenced secret/configmap exists in the correct namespace.

### Failed liveness probe
The container starts fine but the liveness probe fails, so Kubernetes kills it.

**Fix:**
- Check whether the probe endpoint is correct
- Increase `initialDelaySeconds` if the app is slow to boot
- Review the probe timeout and failure threshold

### Resource limits
Container is being OOMKilled. Look for `OOMKilled` in the pod description.

```bash
kubectl describe pod <pod-name> -n <namespace> | grep -A 2 "Last State"
```

**Fix:** Increase the memory limit in the deployment manifest.

### Image pull issue
`ErrImagePull` or `ImagePullBackOff` — typically a bad tag or missing registry credentials.

**Fix:** Verify the image tag exists in the registry. Check the `imagePullSecret` is present in the namespace.

## Remediation

Once you identify the cause, the fix is usually a deployment update:

```bash
# Apply a fixed manifest
kubectl apply -f deployment.yaml

# Or patch an existing deployment (e.g. memory limit)
kubectl set resources deployment/<name> -n <namespace> \
  --limits=memory=1Gi

# Force a restart if the fix is config-side
kubectl rollout restart deployment/<name> -n <namespace>
```

## If It Cannot Be Fixed Quickly

If the service is critical and cannot be recovered within the incident window:

1. Roll back to the last known good deployment:
   ```bash
   kubectl rollout undo deployment/<name> -n <namespace>
   ```
2. Verify with `kubectl rollout status`
3. File a follow-up ticket to investigate the broken version in a non-production environment

## Post-Incident

- Add the specific failure mode to this runbook if it was novel
- Consider whether the liveness/readiness probes need tuning
- If resource limits were the cause, review whether this service has been monitored for trend growth
