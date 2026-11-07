from fastapi.testclient import TestClient

from app.adapters.external import get_operational_events, get_trip_context
from app.main import app
from app.services.normalization import normalize_events

client = TestClient(app)


# --- Adaptadores (contrato del examen) ---

def test_trip_context_preserves_missing_fields():
    trip = get_trip_context('ABC123')
    assert trip['_meta']['completeness'] == 'PARTIAL'
    assert trip['_meta']['missing_fields'] == ['fare_conditions.change_penalty_amount']
    assert 'change_penalty_amount' not in trip['fare_conditions']


def test_trip_context_unknown_booking_returns_none():
    assert get_trip_context('ZZZ999') is None


def test_operational_events_filter_by_segment_and_keep_meta():
    result = get_operational_events(['S2'])
    assert [e['event_id'] for e in result['events']] == ['E-2003']
    assert result['_meta']['sources_degraded'] == ['LEGACY_MIRROR']


def test_adapter_returns_copies():
    get_trip_context('ABC123')['passengers'].clear()
    assert len(get_trip_context('ABC123')['passengers']) == 2


# --- Etapa 1: normalización ---

def test_events_grouped_by_segment_and_sorted():
    raw = get_operational_events(['S1', 'S2'])
    result = normalize_events(raw['events'], ['S1', 'S2'], raw['_meta']['sources_degraded'])
    assert [e['event_id'] for e in result.by_segment['S1']] == ['E-1012', 'E-1001', 'E-1007']
    assert [e['event_id'] for e in result.by_segment['S2']] == ['E-2003']
    assert result.ignored == []
    assert result.degraded_sources == ['LEGACY_MIRROR']


def test_event_from_foreign_segment_is_ignored_not_lost():
    foreign = {'event_id': 'X-1', 'segment_id': 'S9', 'type': 'STATUS', 'source': 'OPS_CORE', 'recorded_at': '2026-09-15T10:00:00Z'}
    result = normalize_events([foreign], ['S1', 'S2'])
    assert result.by_segment == {'S1': [], 'S2': []}
    assert result.ignored == [foreign]


# --- API ---

def test_events_endpoint_returns_booking_events_with_exam_fields():
    data = client.get('/api/trips/ABC123/events').json()
    assert {e['segment_id'] for e in data} == {'S1', 'S2'}
    delay = next(e for e in data if e['event_id'] == 'E-1001')
    assert delay['new_departure'] == '17:10' and delay['delay_minutes'] == 160


def test_trip_endpoint_exposes_minimum_personal_data():
    data = client.get('/api/trips/ABC123').json()
    for p in data['passengers']:
        assert set(p) <= {'passenger_id', 'name', 'type'}
    body = str(data)
    for secret in ('maria.silva@example.com', '8765 4321', '12.345.678-9', 'GOLD'):
        assert secret not in body
    assert data['missing_fields'] == ['fare_conditions.change_penalty_amount']
