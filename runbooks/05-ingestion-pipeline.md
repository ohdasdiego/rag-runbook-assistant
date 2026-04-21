# Runbook: Data Ingestion Pipeline Failure

**Severity:** P2 (P1 if customer data ingestion is blocked)
**Owner:** Data Platform team
**Related alerts:** `ingestion_lag_high`, `ingestion_pipeline_stuck`, `kafka_consumer_lag`

## Overview

The ingestion pipeline moves data from customer sources through Kafka, transformation workers, and into the warehouse. Failures here cause data to back up and may eventually cause Kafka retention to drop messages.

## Architecture Quick Reference

```
Customer → API Gateway → Kafka (raw) → Transformer → Kafka (clean) → Warehouse Loader → Snowflake
```

## Initial Triage

1. Identify the stage that is failing from the alert
2. Check the pipeline dashboard at `grafana.internal/d/ingestion-overview`
3. Check the on-call channel for any ongoing upstream incidents

## Stuck Pipeline — Diagnostic Steps

```bash
# Check Kafka consumer lag
kubectl exec -it kafka-client -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe --group ingestion-transformer

# Check worker pod health
kubectl get pods -n data-platform -l app=transformer

# Tail recent logs
kubectl logs -n data-platform -l app=transformer --tail=200 --follow
```

## Common Failure Modes

### Poison message
A malformed message that crashes the transformer. The same message is retried infinitely.

**Fix:** Identify the offset from logs, then skip it:
```bash
kubectl exec -it kafka-client -- kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --group ingestion-transformer \
  --topic raw-events \
  --reset-offsets --to-offset <OFFSET+1> --execute
```

File the bad message in the dead-letter queue for later analysis.

### Downstream warehouse unavailable
Check Snowflake status. If warehouse is down, the loader will retry — this is expected. Alert may auto-resolve when the warehouse returns.

### Schema mismatch
A new field was added upstream that the transformer doesn't understand. Check recent deployments on the producing service.

**Fix:** Deploy an updated transformer schema, or roll back the producer change if it was unintentional.

### Resource exhaustion
Transformer pods OOMing or CPU-throttled.

**Fix:** Scale up replicas:
```bash
kubectl scale deployment/transformer -n data-platform --replicas=10
```

Or increase resource limits if a single pod cannot handle its partition load.

## Restarting the Pipeline

If the pipeline is stuck and restart is the right call:

```bash
# Rolling restart — preserves partitions
kubectl rollout restart deployment/transformer -n data-platform

# Wait for rollout to complete
kubectl rollout status deployment/transformer -n data-platform
```

Do NOT delete pods directly — use rollout restart so Kubernetes handles graceful shutdown and consumer group rebalancing correctly.

## Verifying Recovery

1. Consumer lag should be decreasing (check dashboard)
2. Transformer pods show no recent errors in logs
3. Data arriving in the warehouse within the last 5 minutes

## Post-Incident

- If data was dropped or reordered, notify the customer success team
- If the root cause was a poison message, file a ticket to improve transformer error handling
- Update this runbook with any new failure modes
