# Proposal: disruption decision engine

## Why
Passengers need an evidence-based explanation of disruptions, without unverified high-impact actions.

## What changes
- Read booking and operational evidence.
- Detect inconsistent statuses and missing information.
- Produce a conservative, traceable decision.
- Block rebooking until policies, eligibility and approvals are validated.

## Scope
First vertical slice: ABC123, read/analyze endpoints, deterministic mocks, automated tests. Future increments: policy verification, options, human cases, notification and idempotent rebooking.
