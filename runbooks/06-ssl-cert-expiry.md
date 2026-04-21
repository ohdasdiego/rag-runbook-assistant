# Runbook: SSL/TLS Certificate Expiry

**Severity:** P2 (P1 if customer-facing cert is already expired)
**Owner:** Platform Infrastructure
**Related alerts:** `cert_expiring_soon`, `cert_expired`

## Overview

Certificates are normally renewed automatically by cert-manager or Let's Encrypt. This runbook covers cases where automation has failed.

## Initial Triage

1. Identify the hostname and certificate from the alert
2. Check current cert status:

```bash
# Check expiry date for a hostname
echo | openssl s_client -servername <hostname> -connect <hostname>:443 2>/dev/null \
  | openssl x509 -noout -dates

# Check cert-manager certificate resource in Kubernetes
kubectl get certificate -A
kubectl describe certificate <cert-name> -n <namespace>
```

## Common Failure Modes

### cert-manager stuck on DNS-01 challenge
Most frequent cause. DNS propagation delay or misconfigured DNS provider credentials.

```bash
# Check the ACME challenge
kubectl get challenges -A
kubectl describe challenge <challenge-name> -n <namespace>
```

If credentials are the issue, update the `ClusterIssuer` secret and the challenge will retry automatically.

### Rate limit hit
Let's Encrypt has strict rate limits. Check the cert-manager logs for `rateLimited` errors. If hit, wait the specified duration — do not retry repeatedly.

### Manual cert in use
Some legacy services use manually-issued certificates. Check the vault location for renewal tracking.

## Emergency Manual Issue

If automation cannot recover before expiry:

1. Issue a cert manually via the provider (Let's Encrypt, internal CA, etc.)
2. Load it into the Kubernetes secret or load balancer directly
3. File a follow-up ticket to fix the automation
4. Do not leave the manual cert in place long-term

## Verification

After renewal:

```bash
# Confirm the new cert is in place
echo | openssl s_client -servername <hostname> -connect <hostname>:443 2>/dev/null \
  | openssl x509 -noout -dates

# Confirm expiry is at least 60 days out
```

## Post-Incident

- If cert-manager automation failed, file a P2 ticket to investigate
- If this was a manually-tracked cert, migrate it to cert-manager
