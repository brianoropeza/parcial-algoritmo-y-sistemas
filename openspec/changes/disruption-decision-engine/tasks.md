# Tasks

- [x] Define initial REST contract.
- [x] Implement booking and event mock adapters.
- [x] Implement conservative analysis response.
- [x] Block unvalidated rebooking.
- [x] Add initial automated tests.
- [ ] Validate exact policy rules and options against source contracts.
- [ ] Implement verified eligibility evaluation and policy references.
- [ ] Add human escalation and idempotent action adapters.
- [ ] Run Docker and pytest locally; capture evidence.
- [ ] Review contract with frontend developer.
- [x] Stage 1: exam mock adapters (`get_trip_context`, `get_operational_events`) loaded from the literal exam fixtures.
- [x] Stage 1: normalize events by segment (D-002) with tests.
- [x] Apply minimum personal data exposure on `GET /api/trips/{booking_id}` (D-006).
- [ ] Stage 2: source reconciliation and contradiction detection (D-003).
- [ ] Stage 3: estimated arrival and missed-connection detection (D-004, D-008).
- [ ] Stage 4: policy rule evaluation and classification (D-005, D-007).
- [ ] Stage 5: option filtering and ordering (D-009).
- [ ] Add `decision_trace` to the analysis response (D-001), agreed with frontend.
