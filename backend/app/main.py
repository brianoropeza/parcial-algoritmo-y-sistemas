from datetime import datetime, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title='Disruption Companion API', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173'], allow_methods=['GET','POST'], allow_headers=['*'])

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

TRIPS = {'ABC123': {'booking_id':'ABC123','passengers':[{'passenger_id':'P1','name':'María Silva','type':'ADULT'},{'passenger_id':'P2','name':'Tomás Silva','type':'CHILD','age':7}], 'segments':[{'segment_id':'S1','flight_number':'NB500','origin':'SCL','destination':'LIM','scheduled_departure':'2026-09-15T14:30:00','scheduled_arrival':'2026-09-15T17:55:00'},{'segment_id':'S2','flight_number':'NB2410','origin':'LIM','destination':'MEX','scheduled_departure':'2026-09-15T19:05:00','scheduled_arrival':'2026-09-15T23:40:00'}], 'fare_conditions':{'changeable':True,'refundable':False,'fare_family':'LIGHT'}, 'completeness':'PARTIAL'}}
EVENTS = [
 {'event_id':'E-1001','segment_id':'S1','type':'DELAY','source':'OPS_CORE','recorded_at':'2026-09-15T10:48:00Z','delay_minutes':160},
 {'event_id':'E-1007','segment_id':'S1','type':'GATE_CHANGE','source':'AIRPORT_FEED','recorded_at':'2026-09-15T10:55:00Z'},
 {'event_id':'E-1012','segment_id':'S1','type':'STATUS','source':'LEGACY_MIRROR','recorded_at':'2026-09-15T10:30:00Z','status':'ON_TIME'},
 {'event_id':'E-2003','segment_id':'S2','type':'STATUS','source':'OPS_CORE','recorded_at':'2026-09-15T10:48:00Z','status':'SCHEDULED'},
]

@app.get('/api/health')
def health():
    return {'status':'ok'}

@app.get('/api/trips/{booking_id}')
def trip(booking_id: str):
    if booking_id not in TRIPS:
        raise HTTPException(404, 'Booking not found')
    return TRIPS[booking_id]

@app.get('/api/trips/{booking_id}/events', response_model=list[Evidence])
def events(booking_id: str):
    if booking_id not in TRIPS:
        raise HTTPException(404, 'Booking not found')
    return EVENTS

@app.post('/api/decisions/analyze', response_model=Decision)
def analyze(req: AnalyzeRequest):
    if req.booking_id not in TRIPS:
        raise HTTPException(404, 'Booking not found')
    delay = any(e.get('type') == 'DELAY' for e in EVENTS)
    contradictory = delay and any(e.get('status') == 'ON_TIME' for e in EVENTS if e['segment_id'] == 'S1')
    warnings = ['Operational sources disagree about segment S1'] if contradictory else []
    warnings += ['Fare penalty amount is missing', 'Policy and option eligibility not yet verified']
    return Decision(booking_id=req.booking_id, classification='DISRUPTION_REVIEW_REQUIRED', recommendation='Verify the operational status, versioned policy and eligible alternatives; refer to a human before any rebooking or compensation.', requires_human_review=True, can_auto_rebook=False, evidence=[Evidence(**e) for e in EVENTS], warnings=warnings, analyzed_at=datetime.now(timezone.utc).isoformat())

@app.post('/api/actions/rebook', status_code=409)
def rebook():
    raise HTTPException(409, 'Rebooking disabled until policy, eligibility and authorization are validated')
