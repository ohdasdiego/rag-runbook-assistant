# Runbook: Incident Severity Classification and Escalation

**Owner:** Incident Commander rotation
**Audience:** All on-call engineers

## Severity Levels

### P1 — Critical
- Production is completely down or severely degraded for all customers
- Data loss or corruption confirmed
- Security breach in progress
- Revenue-generating features unavailable

**Response target:** Acknowledge within 5 minutes, mitigation within 30 minutes.

### P2 — High
- Single region or single service degraded
- Subset of customers affected
- Non-critical features unavailable
- Sustained infrastructure alerts (e.g. high CPU, disk pressure)

**Response target:** Acknowledge within 15 minutes, mitigation within 2 hours.

### P3 — Medium
- Intermittent errors that do not block users
- Internal tooling degraded
- Backlog accumulation without SLA breach

**Response target:** Acknowledge within 1 hour, mitigation within 1 business day.

### P4 — Low
- Minor UI issues
- Non-urgent alerts
- Cosmetic bugs

**Response target:** Next business day.

## Escalation Path

1. **First responder (on-call engineer)** — triages the alert and attempts remediation using the relevant runbook
2. **Secondary on-call** — paged automatically if primary does not acknowledge within 5 minutes (P1) or 15 minutes (P2)
3. **Team lead** — paged if the incident lasts longer than 30 minutes without clear mitigation path
4. **Engineering Manager** — paged for P1 incidents lasting longer than 1 hour
5. **VP Engineering** — paged for P1 incidents with customer communication implications or lasting more than 2 hours

## Declaring an Incident

For P1 and P2:

1. Create a dedicated Slack channel using `/incident new <title>`
2. Assign an Incident Commander (separate from hands-on-keyboard engineer)
3. Post initial status in `#status-internal` within 10 minutes
4. Open a tracking ticket in Jira with the `incident` label

## Customer Communication

- P1: Status page update within 15 minutes of confirmation, every 30 minutes thereafter
- P2: Status page update if customer-facing, every hour
- Do not speculate about root cause in customer communications

## Incident Roles

- **Incident Commander (IC)** — runs the incident, not typing commands
- **Operations Lead** — hands on keyboard, executes remediation
- **Communications Lead** — handles status page and customer updates
- **Scribe** — timestamped timeline of events
