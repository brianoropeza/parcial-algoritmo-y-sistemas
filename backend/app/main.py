from datetime import datetime, timezone
from typing import Literal
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.adapters.external import (create_human_case, create_rebooking_request, get_eligible_options,
                                   get_operational_events, get_policy_rules, get_trip_context, notify_passenger)
from app.services.engine import analyze_trip, passenger_message
from app.services.normalization import normalize_events

app = FastAPI(title='Disruption Companion API', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173'], allow_methods=['GET','POST'], allow_headers=['*'])

# D-006: únicos campos de pasajero que la API puede devolver.
PASSENGER_PUBLIC_FIELDS = ('passenger_id', 'name', 'type')


class AnalyzeRequest(BaseModel):
    booking_id: str = Field(min_length=1)

class Evidence(BaseModel):
    event_id: str
    segment_id: str
    type: str
    source: str
    recorded_at: str
    delay_minutes: int | None = None
    status: str | None = None
    new_departure: str | None = None
    gate: str | None = None

class Decision(BaseModel):
    booking_id: str
    classification: Literal['DISRUPTION_REVIEW_REQUIRED','DISRUPTION_DETECTED','NO_DISRUPTION_CONFIRMED']
    recommendation: str
    requires_human_review: bool
    can_auto_rebook: bool
    evidence: list[Evidence]
    warnings: list[str]
    policy_ref: str | None = None
    analyzed_at: str
    # Campos aditivos (etapas 2 a 5). Compatibles con el contrato anterior.
    action_level: Literal['AUTOMATIC','AUTOMATIC_WITH_CONFIRMATION','HUMAN'] | None = None
    relevant_modification: bool | None = None
    human_review_reasons: list[str] = []
    missed_connections: list[dict] = []
    applied_rules: list[dict] = []
    entitlements: list[str] = []
    candidate_options: list[dict] = []
    discarded_options: list[dict] = []
    segments: list[dict] = []
    passenger_message: dict | None = None
    decision_trace: list[dict] = []

class RebookRequest(BaseModel):
    booking_id: str = Field(min_length=1)
    option_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8)
    approved_case_id: str | None = None

class EscalateRequest(BaseModel):
    booking_id: str = Field(min_length=1)
    reason: str | None = None


def _require_trip(booking_id: str) -> dict:
    trip = get_trip_context(booking_id)
    if trip is None:
        raise HTTPException(404, 'Booking not found')
    return trip


def _segment_ids(trip: dict) -> list[str]:
    return [s['segment_id'] for s in trip.get('segments', [])]


def _public_trip(trip: dict) -> dict:
    """Vista mínima de la reserva (D-006). Los campos faltantes se informan, no se rellenan."""
    meta = trip.get('_meta', {})
    return {
        'booking_id': trip['booking_id'],
        'passengers': [{k: p[k] for k in PASSENGER_PUBLIC_FIELDS if k in p} for p in trip.get('passengers', [])],
        'segments': trip.get('segments', []),
        'fare_conditions': trip.get('fare_conditions', {}),
        'completeness': meta.get('completeness'),
        'missing_fields': meta.get('missing_fields', []),
    }


@app.get('/api/health')
def health():
    return {'status':'ok'}

@app.get('/api/trips/{booking_id}')
def trip(booking_id: str):
    return _public_trip(_require_trip(booking_id))

@app.get('/api/trips/{booking_id}/events', response_model=list[Evidence])
def events(booking_id: str):
    trip = _require_trip(booking_id)
    return get_operational_events(_segment_ids(trip))['events']

def _run_engine(booking_id: str):
    trip = _require_trip(booking_id)
    segment_ids = _segment_ids(trip)
    raw = get_operational_events(segment_ids)
    normalized = normalize_events(raw['events'], segment_ids, raw['_meta'].get('sources_degraded'))
    policy = get_policy_rules('DELAY')
    result = analyze_trip(trip, normalized, get_eligible_options(trip), policy)
    return trip, normalized, policy, result


@app.post('/api/decisions/analyze', response_model=Decision)
def analyze(req: AnalyzeRequest):
    trip, normalized, policy, r = _run_engine(req.booking_id)
    segment_ids = _segment_ids(trip)
    policy_ref = policy['version'] if policy else None

    warnings: list[str] = []
    for seg in r['segments']:
        if seg['conflict_detected']:
            warnings.append(f"Operational sources disagree about segment {seg['segment_id']}"
                            + (' (unresolved)' if seg['unresolved_conflict'] else f" (resolved by trust: {seg['prevailing_event']})"))
    for missing in trip.get('_meta', {}).get('missing_fields', []):
        warnings.append(f'Missing field: {missing}')

    human = r['action_level'] == 'HUMAN'
    if human:
        classification, rec = 'DISRUPTION_REVIEW_REQUIRED', 'Show the explanation and candidate options; a human agent must approve any rebooking (D-007).'
    elif r['relevant_modification']:
        classification, rec = 'DISRUPTION_DETECTED', 'Offer the candidate options; rebook only after passenger confirmation.'
    else:
        classification, rec = 'NO_DISRUPTION_CONFIRMED', 'Inform the passenger; no action needed.'

    msg = passenger_message(req.booking_id, r, policy_ref)
    status, _ = notify_passenger(msg)  # validación previa: el mock rechaza mensajes sin policy_ref
    msg['validated'] = status == 202

    evidence = [Evidence(**e) for sid in segment_ids for e in normalized.by_segment[sid]]
    return Decision(booking_id=req.booking_id, classification=classification, recommendation=rec,
                    requires_human_review=human, can_auto_rebook=False, evidence=evidence, warnings=warnings,
                    policy_ref=policy_ref, analyzed_at=datetime.now(timezone.utc).isoformat(),
                    action_level=r['action_level'], relevant_modification=r['relevant_modification'],
                    human_review_reasons=r['human_review_reasons'], missed_connections=r['missed_connections'],
                    applied_rules=r['applied_rules'], entitlements=r['entitlements'],
                    candidate_options=r['candidate_options'], discarded_options=r['discarded_options'],
                    segments=r['segments'], passenger_message=msg, decision_trace=r['decision_trace'])


@app.get('/api/trips/{booking_id}/options')
def options(booking_id: str):
    _, _, _, r = _run_engine(booking_id)
    return {'booking_id': booking_id, 'note': 'Candidates only, not confirmed bookings.',
            'candidate_options': r['candidate_options'], 'discarded_options': r['discarded_options']}


@app.post('/api/actions/escalate', status_code=201)
def escalate(req: EscalateRequest):
    _, _, _, r = _run_engine(req.booking_id)
    reason = req.reason or '; '.join(r['human_review_reasons']) or 'passenger requested human review'
    _, case = create_human_case(reason, r['decision_trace'])
    return {'booking_id': req.booking_id, **case}


@app.post('/api/actions/rebook', status_code=201)
def rebook(req: RebookRequest | None = Body(default=None)):
    if req is None:
        raise HTTPException(409, 'Rebooking requires booking_id, option_id and idempotency_key')
    _, _, _, r = _run_engine(req.booking_id)
    option = next((o for o in r['candidate_options'] if o['option_id'] == req.option_id), None)
    if option is None:
        return JSONResponse(status_code=409, content={'error': 'OPTION_NOT_ELIGIBLE', 'option_id': req.option_id,
                                                      'discarded': r['discarded_options']})
    if r['action_level'] == 'HUMAN' and not req.approved_case_id:
        return JSONResponse(status_code=409, content={'error': 'HUMAN_APPROVAL_REQUIRED', 'reasons': r['human_review_reasons']})
    status, body = create_rebooking_request(option, req.idempotency_key)
    return JSONResponse(status_code=status, content=body)
