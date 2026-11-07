# Disruption Companion — Engineering README

Final exam 2026-B · Algorithms and Systems Analysis · UDES · Backend: Brian Oropeza (FastAPI) · Frontend: Diego Triana (Streamlit)

## 1. Problem and expected outcome
Nubara Airlines needs to explain to a passenger what happened to a modified itinerary, what they are entitled to under policy, and when a person must step in — without communicating unvalidated information or executing high-impact actions without control. Outcome: a FastAPI backend with a deterministic decision engine that combines booking, operational events, eligible options and versioned policies, plus a Streamlit passenger screen that only displays what the backend decides.

**Base case ABC123 (verified by tests):** S1 (NB500) is delayed 160 min according to OPS_CORE. LEGACY_MIRROR's `ON_TIME` is discarded because the source is degraded and its record is older. The estimated arrival in LIM is 20:35, after S2 departs (19:05), so the connection is missed. R3 (`REBOOK_NO_FEE`) and R5 (minor in the group, requires human approval) apply. R1 and R2 do not (160 < 180/240), so there is no meal voucher. O1 (NB2412, Sep 16 08:15) is the only candidate; O2 is discarded (1 seat for 2 passengers and a fare difference) and so is O3 (refund policy not retrieved, LOW confidence). Automation level: **HUMAN** — the system explains and shows O1, but rebooking requires an approved human case.

## 2. Assumptions and scope
- Mock data is a literal transcription of the exam samples (`backend/app/data/exam_fixtures_abc123.json`). Missing fields (`change_penalty_amount`) are reported, never filled in.
- Estimated arrival = `scheduled_arrival + delay_minutes` in local time (assumption: flight duration does not change).
- Implemented: the 7 exam contracts as mocks, the 5 engine stages, endpoints `trips`, `events`, `options`, `analyze`, `rebook` (idempotent) and `escalate`, and validation of the passenger message.
- Frontend in Streamlit (`frontend/`), built by the teammate; it consumes the contract and makes no decisions. Out of scope: real persistence, authentication and real verification of `approved_case_id`.

## 3. Main decisions and discarded alternatives
Full detail in `docs/DECISIONS.md` (D-001 to D-014, written in Spanish).
| Decision | Chosen | Discarded |
|---|---|---|
| Algorithm (D-002) | Deterministic 5-stage pipeline | Single rule table; AI agent |
| Source conflicts (D-003, D-010) | Trust hierarchy; a degraded source never prevails; conflict between trusted sources → human | "Latest record wins" |
| Personal data (D-006) | API returns only id, name and type | Exposing the full booking |
| Human rule R5 (D-007) | Blocks every high-impact action in the case | Blocking only priority handling |
| Options (D-009) | Filter by seats, fare, policy and confidence; lexicographic order | Showing all options as received |
| Policy conditions (D-011) | Safe parser, no `eval`; missing fact → rule not triggered | `eval()` |

## 4. Algorithm and complexity
| Stage | File | Complexity |
|---|---|---|
| 1 Normalize events by segment | `services/normalization.py` | O(n log n) |
| 2 Reconcile sources | `services/engine.py · reconcile_segment` | O(n) |
| 3 Connection impact | `connection_impact` | O(s) |
| 4 Evaluate policy | `evaluate_policy` | O(r) |
| 5 Filter and rank options | `filter_options` | O(m log m) |
Each stage appends steps to `decision_trace`, returned by `/api/decisions/analyze`.

## 5. Deterministic, AI and human
| Step | Classification | Risk | Control / fallback |
|---|---|---|---|
| Event reconciliation, connection, rules and options | Deterministic | Contradictory data | Source hierarchy; unresolved conflict → human |
| Passenger message | Deterministic (template) | Communicating something unvalidated | Engine facts only; `notify_passenger` rejects messages without `policy_ref` (422) |
| Rebooking | Human or passenger confirmation | Cost and policy breach | Candidate option, human approval (D-007) and idempotency |
| Compensation / refund | Human | High cost | Never automatic |
No AI is used at runtime. The rules are verifiable, and AI would add latency, cost and non-reproducibility with no benefit for this scope. A possible future use is drafting the message text from already-validated fields, without access to personal data.

## 6. How to run and validate (guide for the reviewer)

### Quick start — one command
Requires only **Python 3.12 or later** (tested with 3.12, 3.13 and 3.14) and Git.
```powershell
git clone https://github.com/brianoropeza/parcial-algoritmo-y-sistemas.git
cd parcial-algoritmo-y-sistemas
py run.py              # Windows  (Linux / macOS: python3 run.py)
```
`run.py` creates a local `.venv` the first time, installs all dependencies, starts the backend and the frontend, and opens the browser at `http://localhost:8501`. **Ctrl+C stops both.**

To run every automated test (backend and frontend) with one command:
```powershell
py run.py --test       # expected: 27 passed (backend) + 27 passed (frontend)
```
Other options: `--no-install` (skip dependency installation), `--no-browser`.

### Prerequisites
| Requirement | Version | Required? |
|---|---|---|
| Python | 3.12 or later | Yes |
| Git | any | Yes, to clone |
| Internet | only the first time (`pip install`) | Yes, the first time |
| Docker Desktop + Docker Compose | Docker 29 / Compose 5 | Optional (option B) |

**Not needed:** database, API keys, environment variables, external services or AI models — every external system is mocked with the exam data.

Dependencies (installed automatically by `run.py`): `backend/requirements.txt` (`fastapi`, `uvicorn`, `pydantic` v2, `pytest`, `httpx`) and `frontend/requirements.txt` (`streamlit` ≥ 1.50, `requests`, `pytest`).

### Option A — manual (if you prefer separate terminals)
```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r frontend\requirements.txt
# terminal 1
cd backend;  ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# terminal 2
cd frontend; ..\.venv\Scripts\python.exe -m streamlit run app.py
```
Linux / macOS: same steps with `python3 -m venv .venv` and `.venv/bin/python`.

### Option B — Docker
```bash
docker compose up --build -d
docker compose exec backend pytest -q
docker compose exec frontend pytest -q
# API at http://localhost:8000/docs · Frontend at http://localhost:8501 ; stop with: docker compose down
```
*Docker could not be verified on the development machine (WSL 2 still installing); `run.py` and option A are verified.*

### Demonstrating the main decision
**Frontend:** open `http://localhost:8501`, enter `ABC123` and click **Check my trip**. The rebooking button is blocked (R5) and **Talk to a person** creates case HC-4471.

**API:** at `http://localhost:8000/docs`, run `POST /api/decisions/analyze` with `{"booking_id": "ABC123"}`, or in PowerShell:
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/decisions/analyze -ContentType "application/json" -Body '{"booking_id":"ABC123"}'
```
Expected: `classification = DISRUPTION_REVIEW_REQUIRED`, `action_level = HUMAN`, `missed_connections` S1→S2 (20:35 > 19:05), `applied_rules` R3 and R5, `candidate_options` only O1, and `decision_trace` covering the 5 stages.

| Endpoint | What it shows |
|---|---|
| `GET /api/trips/ABC123` | Booking with minimum personal data; `NOPE` → 404 |
| `GET /api/trips/ABC123/events` | Booking events, including the conflict |
| `GET /api/trips/ABC123/options` | Candidate and discarded options with reasons |
| `POST /api/actions/rebook` | Without approval → 409; repeated with the same key → 409 `DUPLICATE_REQUEST` |
| `POST /api/actions/escalate` | Creates human case HC-4471 |

**Validation:** 27 backend tests (base case, degraded source, conflict between trusted sources, missed connection, rules, option filtering, human approval, idempotency, escalation, 404, notification without `policy_ref`, personal data) and 27 frontend tests (input validation, personal-data allow-list, HTTP error handling, rendering of the real backend response). Integration verified with both services running (`run.py`, Windows with Python 3.14 and Linux with Python 3.13).

## 7. Risks, limitations and next steps
- `approved_case_id` is not verified against a real approval system. Next step: a registry of approved cases.
- Idempotency is stored in memory and lost on restart. Next step: persistence.
- `503 UPSTREAM_TIMEOUT` is not handled yet in the backend; proposed strategy: retry with the same key (the frontend already treats it as indeterminate and does not retry).
- The 120 s option TTL is not enforced.
- The airport → country mapping used for the `international` condition is hard-coded.
- No passenger authentication; the booking code alone is enough to look up a trip.
- Docker has not been verified on the development machine.

## 8. Ambiguous or complex query (task 5.2)
**Example:** *"Was my flight cancelled? Will you pay for a hotel in Lima for me and my son?"*
1. **Interpret (AI-assisted, optional):** classify free text into closed intents (`STATUS`, `ENTITLEMENT:HOTEL`). The output is validated against that list; if it does not match, the system asks for clarification. The model receives only the text, never personal data.
2. **Retrieve context (deterministic):** `get_trip_context`, `get_operational_events`, `get_policy_rules('DELAY')` and `get_eligible_options`.
3. **Resolve (deterministic):** there is no `CANCELLATION` event; OPS_CORE reports a delay → answer "delayed, not cancelled". No rule in POL-DELAY-2026-03 grants a hotel → nothing is promised.
4. **Stop and escalate (human):** hotel not covered, minor in the group (R5) and an overnight stay in Lima → `create_human_case` with the trace as evidence. The passenger only receives validated content, with `policy_ref`.
No agent is used: the tools and their order are fixed. An agent would add the risk of unauthorized actions with no benefit.
