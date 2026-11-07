# Tasks

- [x] Define initial REST contract.
- [x] Implement booking and event mock adapters.
- [x] Implement conservative analysis response.
- [x] Block unvalidated rebooking.
- [x] Add initial automated tests.
- [x] Validate exact policy rules and options against source contracts.
- [x] Implement verified eligibility evaluation and policy references.
- [x] Add human escalation and idempotent action adapters.
- [ ] Run Docker and pytest locally; capture evidence.
- [ ] Review contract with frontend developer.
- [x] Stage 1: exam mock adapters (`get_trip_context`, `get_operational_events`) loaded from the literal exam fixtures.
- [x] Stage 1: normalize events by segment (D-002) with tests.
- [x] Apply minimum personal data exposure on `GET /api/trips/{booking_id}` (D-006).
- [x] Stage 2: source reconciliation and contradiction detection (D-003).
- [x] Stage 3: estimated arrival and missed-connection detection (D-004, D-008).
- [x] Stage 4: policy rule evaluation and classification (D-005, D-007).
- [x] Stage 5: option filtering and ordering (D-009).
- [x] Add `decision_trace` to the analysis response (D-001), additive field.
