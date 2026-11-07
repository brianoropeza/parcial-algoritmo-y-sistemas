# Frontend — Disruption Companion (Streamlit)

Passenger-facing screen. **It decides nothing**: it displays what the backend returns (`contracts/openapi.yaml`).

## Run

Fastest way, from the repository root (starts backend + frontend with one command):

```sh
py run.py          # Windows  (Linux / macOS: python3 run.py)
py run.py --test   # backend + frontend tests
```

With Docker (from the repository root, starts backend + frontend):

```sh
docker compose up --build -d
docker compose exec frontend pytest -q
```

Frontend: http://localhost:8501 · Backend: http://localhost:8000/docs

Requires Python 3.12 or later and Streamlit ≥ 1.50 (`streamlit==1.39.0` was unpinned because it cannot be installed on Python 3.14).
`BACKEND_URL` defaults to `http://localhost:8000`.

## What it does

1. **Look up booking**: validates the code (5–8 letters/digits) before calling the backend.
2. **Your trip**: passengers and segments. Allow-listed fields only: never ID document, email, phone or loyalty tier.
3. **What happened?**: classification, warnings and evidence with source and timestamp (degraded sources flagged).
4. **What can you do?**: recommended option with its `policy_ref`, discarded options with their reason, and two actions:
   - **Request rebooking**: enabled only when the backend allows it (`requires_human_review=false` and `action_level=AUTOMATIC_WITH_CONFIRMATION`). Requires confirmation and sends an `idempotency_key` that is **reused** if the user clicks again.
   - **Talk to a person**: creates a human case (`/api/actions/escalate`).

## Error handling

| Response | What the user sees |
|---|---|
| Backend down / read timeout | "We could not reach the system" |
| 404 on booking | "We could not find a booking with that code" |
| 409 with `request_id` | Request already registered, no new one created |
| 409 without `request_id` | Action not allowed yet |
| 503 or timeout on a write | **Indeterminate** outcome: do not retry, an agent verifies |
| 422 | The system rejected the data |
| 404/405 on an action | "This action is not available yet" |

## Contract consumed

Endpoints used (see `contracts/openapi.yaml`):

- `GET /api/trips/{booking_id}` — public booking view (no personal contact data).
- `POST /api/decisions/analyze` — `{"booking_id"}` → `Decision`.
- `POST /api/actions/rebook` — `{"booking_id", "option_id", "idempotency_key"}`.
- `POST /api/actions/escalate` — `{"booking_id", "reason"}`.

`Decision` fields displayed: `classification`, `action_level`, `missed_connections`, `passenger_message.text`
(only if `validated`), `entitlements`, `applied_rules`, `human_review_reasons`, `candidate_options`
(first = recommended, already ranked by the backend), `discarded_options[].reasons`, `evidence`,
`segments[].discarded` (marks events not used, e.g. the degraded `LEGACY_MIRROR`), `warnings`, `decision_trace`.

The rebooking button is enabled only when `requires_human_review` is false and `action_level` is
`AUTOMATIC_WITH_CONFIRMATION` (D-005). For ABC123 the backend returns `HUMAN` (rule R5, minor on board),
so the screen explains why and offers "Talk to a person".

`tests/backend_abc123.json` is the real backend output for ABC123 and is used to test the screen logic
against the actual contract.

## Known limitations

- No mock mode: if the backend is down, the screen says so and never invents data.
- No passenger authentication; the booking code is enough to look up a trip (acceptable only for this first version).
- Tests cover the presentation logic and the HTTP client; the Streamlit UI itself is verified manually.
