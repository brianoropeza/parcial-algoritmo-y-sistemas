from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.adapters.external import get_operational_events, get_trip_context
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
    classification: Literal['DISRUPTION_REVIEW_REQUIRED','NO_DISRUPTION_CONFIRMED']
    recommendation: str
    requires_human_review: bool
    can_auto_rebook: bool
    evidence: list[Evidence]
    warnings: list[str]
    policy_ref: str | None = None
    analyzed_at: str


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

@app.post('/api/decisions/analyze', response_model=Decision)
def analyze(req: AnalyzeRequest):
    # Etapa 1 (normalización) integrada. Las etapas 2 a 5 (D-002) aún no están
    # implementadas, por eso la clasificación sigue siendo conservadora.
    trip = _require_trip(req.booking_id)
    segment_ids = _segment_ids(trip)
    raw = get_operational_events(segment_ids)
    normalized = normalize_events(raw['events'], segment_ids, raw['_meta'].get('sources_degraded'))

    warnings: list[str] = []
    for sid, seg_events in normalized.by_segment.items():
        has_delay = any(e.get('type') == 'DELAY' for e in seg_events)
        says_on_time = any(e.get('status') == 'ON_TIME' for e in seg_events)
        if has_delay and says_on_time:
            warnings.append(f'Operational sources disagree about segment {sid}')
    for missing in trip.get('_meta', {}).get('missing_fields', []):
        warnings.append(f'Missing field: {missing}')
    warnings.append('Policy and option eligibility not yet verified')

    evidence = [Evidence(**e) for sid in segment_ids for e in normalized.by_segment[sid]]
    return Decision(booking_id=req.booking_id, classification='DISRUPTION_REVIEW_REQUIRED', recommendation='Verify the operational status, versioned policy and eligible alternatives; refer to a human before any rebooking or compensation.', requires_human_review=True, can_auto_rebook=False, evidence=evidence, warnings=warnings, analyzed_at=datetime.now(timezone.utc).isoformat())

@app.post('/api/actions/rebook', status_code=409)
def rebook():
    raise HTTPException(409, 'Rebooking disabled until policy, eligibility and authorization are validated')
