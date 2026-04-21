# Runbook: Service Deployment Rollback

**Severity:** Matches severity of the incident it is addressing
**Owner:** Deployment requester + on-call engineer

## Overview

A recently-deployed change has caused a production incident. This runbook covers when to roll back, how to do it safely, and what to do after.

## When to Roll Back

Roll back immediately if:
- Error rate has spiked above 1% and the cause is confirmed to be the new deployment
- A critical feature is broken for users
- The on-call engineer cannot identify a quick forward-fix within 15 minutes

Do NOT roll back if:
- The new deployment contains schema migrations that have already been applied (roll forward instead)
- The root cause is external (upstream dependency, infrastructure) — rolling back will not help

## Rollback Procedures

### Kubernetes Deployment

```bash
# Check deployment history
kubectl rollout history deployment/<n> -n <namespace>

# Roll back to the previous revision
kubectl rollout undo deployment/<n> -n <namespace>

# Or roll back to a specific revision
kubectl rollout undo deployment/<n> -n <namespace> --to-revision=<N>

# Watch the rollback progress
kubectl rollout status deployment/<n> -n <namespace>
```

### ArgoCD-managed Deployment

1. Open the Argo UI for the app
2. Select "History and Rollback"
3. Choose the last known good sync
4. Confirm rollback

### AWS ECS Service

```bash
# Update service to the previous task definition
aws ecs update-service \
  --cluster <cluster> \
  --service <service> \
  --task-definition <service>:<previous-revision-number>
```

## Verification After Rollback

1. Error rate is returning to baseline (check within 5 minutes)
2. Latency is back to normal
3. No new alerts triggered by the rollback itself
4. Customer-reported issues have stopped

## If Rollback Does Not Fix the Issue

If the symptoms persist after rollback completes:

1. The root cause is likely not the deployment — revisit the incident
2. Check for infrastructure issues, upstream dependency failures, or database problems
3. Consider whether a database migration left the system in a partially-migrated state

## Schema Migration Considerations

Rolling back a deployment with a schema migration is risky:

- If the new code introduced a new column the old code doesn't know about → safe to roll back (old code will ignore the column)
- If the new code removed a column the old code needs → DO NOT roll back; roll forward with a fix
- If the new code renamed a column → DO NOT roll back; both versions will fail

When in doubt, page the DBA before rolling back.

## Post-Incident

1. Open a ticket on the broken deployment with full incident details
2. Require a fix + test before the change can be redeployed
3. Review whether better testing or a safer rollout strategy (canary, blue-green) would have caught it
4. Update the deployment checklist if a procedural gap contributed
