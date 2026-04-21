# Runbook: Leaked Credential / API Key Rotation

**Severity:** P1 (always)
**Owner:** Security + Platform Infrastructure
**Related alerts:** `github_secret_scan`, `credential_leak_detected`

## Overview

Any leaked credential — API key, database password, cloud access key, service account token — must be treated as P1 and rotated immediately. This runbook covers detection, rotation, and containment.

## Immediate Actions (First 10 Minutes)

1. **Do not delete the leaked commit or file yet** — preserve for forensics
2. **Revoke the credential immediately** at the provider (see provider-specific steps below)
3. Declare a P1 incident and notify Security on-call
4. Begin audit logging review for the affected credential

## Provider-Specific Rotation Steps

### AWS IAM Access Keys

```bash
# Immediately disable the leaked key
aws iam update-access-key --access-key-id <LEAKED_KEY_ID> --status Inactive --user-name <username>

# Create a replacement key
aws iam create-access-key --user-name <username>

# After confirming all services use the new key, delete the old one
aws iam delete-access-key --access-key-id <LEAKED_KEY_ID> --user-name <username>
```

### Anthropic / OpenAI API Keys

1. Log in to the provider console
2. Revoke the exposed key from the API keys page
3. Generate a new key and update it in the secrets manager (AWS Secrets Manager or Vault)
4. Roll all services that reference the key

### Database Credentials

```bash
# Connect as admin and rotate the password
psql -h <host> -U admin -c "ALTER USER <app_user> WITH PASSWORD '<new_password>';"

# Update the secret in the secrets manager
vault kv put secret/db/app-user password=<new_password>

# Trigger a rolling restart of dependent services
kubectl rollout restart deployment/<service>
```

### GitHub Personal Access Tokens

1. Revoke at https://github.com/settings/tokens
2. Generate replacement with minimum required scopes
3. Update CI/CD secrets in affected repositories

## Audit & Containment

1. Pull CloudTrail / equivalent audit logs for the window between leak and revocation
2. Check for unexpected API calls, resource creation, or data access
3. If unauthorized activity is detected:
   - Escalate to Security leadership immediately
   - Preserve all logs for legal review
   - Begin customer notification process per compliance requirements

## Cleanup

1. After rotation is confirmed working, remove the leaked credential from git history using `git filter-repo` or BFG
2. Force-push to remote (coordinate with team, as this rewrites history)
3. File a post-mortem ticket
4. Update the pre-commit secret-scanning hook configuration if the leak type was not caught

## Prevention

- All repositories must have secret scanning enabled
- Use short-lived credentials wherever possible (OIDC, IAM roles, workload identity)
- Store all secrets in Vault / Secrets Manager, never in environment files committed to git
