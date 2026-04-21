# Runbook: On-Call Handbook

**Audience:** All engineers in the on-call rotation

## Overview

This runbook covers on-call expectations, the handoff process, and what to do when you cannot take a shift.

## Shift Structure

- Shifts are one week, Monday 9:00 AM to the following Monday 9:00 AM (local time)
- Primary and secondary on-call are scheduled at the same time
- Secondary is paged if primary does not acknowledge within the severity-specific window (see incident escalation runbook)

## Responsibilities

While on-call you are expected to:

1. Be reachable within 5 minutes (P1) or 15 minutes (P2) of a page
2. Carry your laptop and working internet when not at your desk
3. Not consume alcohol or be otherwise impaired during shift
4. Check in on the on-call channel at least twice per day
5. Triage and either resolve or escalate all pages during your shift
6. Document every incident in the incident tracker — no matter how small

## Handoff

At the end of your shift:

1. Post a handoff note in `#on-call-handoff` with:
   - Open incidents and their current state
   - Flaky alerts that fired during your shift
   - Any changes you made that the next person should know about
2. Join the handoff sync at 9:30 AM Monday if there are active incidents
3. Transfer PagerDuty override if it was in place

## When You Cannot Take a Shift

If you cannot take your scheduled shift:

1. Post in `#on-call-swaps` as early as possible
2. Find a swap partner — the expectation is engineer-to-engineer arrangement
3. Once confirmed, update PagerDuty directly
4. Notify your team lead by DM if it is a last-minute swap (same week)

## Emergency Swaps

If you become unavailable mid-shift (illness, family emergency):

1. Page the secondary on-call and hand off
2. Notify your manager and the on-call rotation owner
3. Secondary will cover until a longer-term replacement is found

## Compensation

- Time-in-lieu is granted for weekend or holiday pages
- Nights spent responding to pages count toward time-in-lieu
- Submit via the HR tool within 30 days

## Resources

- PagerDuty: https://our-org.pagerduty.com
- On-call calendar: https://our-org.pagerduty.com/schedules
- Runbook index: https://wiki.internal/runbooks
- Incident tracker: https://jira.internal/incidents
