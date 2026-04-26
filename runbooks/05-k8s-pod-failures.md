# Runbook: Kubernetes Pod Failures — Civo k3s Cluster

**Service:** K8s Event Summarizer (port 5003, https://k8s.ado-runner.com)  
**Severity:** P2 (demo workloads) / P1 (real production pods)  
**Alert source:** K8s Event Summarizer Telegram alert, or manual kubectl observation  
**Response time:** 15 min (demo) / 5 min (production pods)

---

## Overview

The ADOStack platform monitors a Civo k3s cluster (v1.34.2+k3s1) via the K8s Event Summarizer service. The cluster intentionally runs **3 broken demo workloads** for AI analysis training purposes. Distinguishing demo failures from real failures is the primary triage skill for this runbook.

**Kubeconfig:** `~/.kube/config` (on claw-gateway1)  
**K8s Event Summarizer:** `sudo systemctl status k8s-event-summarizer`

**Known demo workloads (intentionally broken — do NOT fix these):**
| Workload | Namespace | State | Reason |
|----------|-----------|-------|--------|
| `broken-app` | default | ImagePullBackOff | Invalid image reference |
| `crashloop-demo` | default | CrashLoopBackOff | App exits with code 1 |
| `starved-pod` | default | Pending | Resource requests exceed node capacity |

---

## Prerequisites

- SSH access: `ssh claw@161.35.229.80`
- `kubectl` configured: `export KUBECONFIG=~/.kube/config`
- K8s Event Summarizer running at port 5003
- On-Call Assistant at https://oncall.ado-runner.com for escalation

---

## Triage

### 1. Check K8s Event Summarizer for AI-generated summary

```bash
curl -s https://k8s.ado-runner.com/api/status | python3 -m json.tool
curl -s https://k8s.ado-runner.com/api/events | python3 -m json.tool | head -60
```

The AI summary will describe detected failures. Check if they match the 3 known demo workloads.

### 2. Get raw cluster state

```bash
kubectl get pods --all-namespaces
kubectl get pods -n default -o wide
kubectl get nodes
```

### 3. Classify each failure

For each non-Running pod, ask:
- Is it one of the 3 known demo workloads? → Document, do NOT fix
- Is it a new/unexpected failure? → Treat as real incident

---

## Diagnostic Commands

```bash
# Full pod status with age and restarts
kubectl get pods --all-namespaces -o wide

# Events (essential for Pending/ImagePull failures)
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -30
kubectl get events -n default --sort-by='.lastTimestamp' | tail -20

# Pod describe (most detail)
kubectl describe pod broken-app -n default
kubectl describe pod crashloop-demo -n default
kubectl describe pod starved-pod -n default

# Logs from a crashing pod
kubectl logs crashloop-demo -n default
kubectl logs crashloop-demo -n default --previous   # Logs from last crash

# Node resource pressure
kubectl describe nodes | grep -A5 "Conditions:"
kubectl top nodes   # Requires metrics-server
kubectl top pods --all-namespaces 2>/dev/null

# Resource requests vs allocatable
kubectl describe nodes | grep -A10 "Allocated resources"

# Check for real ADOStack pods (non-demo)
kubectl get pods --all-namespaces | grep -v -E "broken-app|crashloop-demo|starved-pod"
```

---

## Identifying Demo vs Real Failures

### Demo workload signatures

**broken-app (ImagePullBackOff):**
```bash
kubectl describe pod broken-app -n default | grep -A3 "Events:"
# Expected: "Failed to pull image" — the image tag is intentionally invalid
# DO NOT fix — this is a demo for AI analysis
```

**crashloop-demo (CrashLoopBackOff):**
```bash
kubectl logs crashloop-demo -n default --previous
# Expected: exits immediately, non-zero exit code
# Restart count will be high (50+) — this is normal
# DO NOT fix — this is a demo scenario
```

**starved-pod (Pending):**
```bash
kubectl describe pod starved-pod -n default | grep -A5 "Events:"
# Expected: "Insufficient cpu" or "Insufficient memory"
# Resource requests are intentionally set beyond node capacity
# DO NOT fix — this is a demo scenario
```

### Real failure indicators (act on these)

```bash
# New pods in bad state that are NOT the 3 demo workloads
kubectl get pods --all-namespaces | grep -v -E "Running|Completed|broken-app|crashloop-demo|starved-pod"

# Pods that were previously running but just entered failure state
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | grep -E "Warning|Error" | grep -v -E "broken-app|crashloop-demo|starved-pod" | tail -10
```

---

## Common Root Causes

| State | Cause | Diagnosis |
|-------|-------|-----------|
| ImagePullBackOff | Wrong image name, private registry auth | `kubectl describe pod` → Events section |
| CrashLoopBackOff | App crash on start, bad config, missing env | `kubectl logs --previous` |
| Pending | Insufficient resources, no matching node | `kubectl describe pod` → Events: "Insufficient" |
| OOMKilled | Container exceeded memory limit | `kubectl describe pod` → Last State: OOMKilled |
| Error | Init container failed | `kubectl logs <pod> -c <init-container>` |
| Terminating | Stuck finalizer | `kubectl delete pod <pod> --grace-period=0 --force` |

---

## Remediation Steps

### For real ImagePullBackOff failures (non-demo)

```bash
# Identify the bad image
kubectl describe pod <pod-name> -n <namespace> | grep "Image:"

# Fix the image reference in the deployment
kubectl set image deployment/<name> <container>=<correct-image>:<tag>

# Or edit directly
kubectl edit deployment/<name> -n <namespace>

# Watch rollout
kubectl rollout status deployment/<name> -n <namespace>
```

### For real CrashLoopBackOff failures (non-demo)

```bash
# Get crash reason
kubectl logs <pod-name> -n <namespace> --previous

# Check environment variables
kubectl describe pod <pod-name> -n <namespace> | grep -A20 "Environment:"

# If config issue, update ConfigMap
kubectl get configmaps -n <namespace>
kubectl edit configmap <name> -n <namespace>

# Rollback if recent deploy caused crash
kubectl rollout undo deployment/<name> -n <namespace>
kubectl rollout status deployment/<name> -n <namespace>
```

### For real Pending pods (resource starvation, non-demo)

```bash
# Check what's consuming node resources
kubectl describe node | grep -A10 "Allocated resources:"
kubectl top pods --all-namespaces --sort-by=memory 2>/dev/null

# Reduce resource requests if over-provisioned
kubectl edit deployment/<name> -n <namespace>
# Lower resources.requests.cpu and resources.requests.memory

# Or delete lower-priority workloads to free capacity
kubectl delete pod <lower-priority-pod> -n <namespace>
```

### Rollout restart a deployment (catch-all recovery)

```bash
kubectl rollout restart deployment/<name> -n <namespace>
kubectl rollout status deployment/<name> -n <namespace>
kubectl get pods -n <namespace> -w
```

### Stuck Terminating pod

```bash
kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force
```

---

## Verification

```bash
# All non-demo pods should be Running or Completed
kubectl get pods --all-namespaces | grep -v -E "broken-app|crashloop-demo|starved-pod"

# K8s Event Summarizer should report new AI summary
curl -s https://k8s.ado-runner.com/api/status | python3 -m json.tool

# Node should not be under pressure
kubectl describe nodes | grep -A5 "Conditions:" | grep -v "False"
```

---

## Escalation

If a real production pod failure cannot be resolved within 15 minutes:

1. Open P1 incident in On-Call Assistant:
   ```bash
   curl -s -X POST https://oncall.ado-runner.com/api/incidents \
     -H "Content-Type: application/json" \
     -d '{"title":"K8s pod failure: <pod-name>","severity":"P1","description":"<describe failure>"}'
   ```
2. Check if K8s Event Summarizer service itself is healthy (not just the cluster):
   ```bash
   sudo systemctl status k8s-event-summarizer
   journalctl -u k8s-event-summarizer --since "30 minutes ago" | tail -30
   ```

---

## Post-Incident

```bash
# Confirm K8s Event Summarizer generated updated AI summary
curl -s https://k8s.ado-runner.com/api/events | python3 -m json.tool | head -30

# Document: was this a demo workload or real failure?
# If real: add to Incident Logger
curl -s https://incidents.ado-runner.com/api/incidents | python3 -m json.tool | head -20

# Record the fix applied and close incident in On-Call Assistant
# Verify demo workloads still in their expected bad states (they should be)
kubectl get pods -n default | grep -E "broken-app|crashloop-demo|starved-pod"
```
