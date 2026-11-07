import pytest
from fastapi.testclient import TestClient

from app.adapters import external
from app.main import app
from app.services.engine import evaluate_condition, reconcile_segment

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    external._reset_write_state()
    yield
    external._reset_write_state()


def analyze():
    r = client.post('/api/decisions/analyze', json={'booking_id': 'ABC123'})
    assert r.status_code == 200
    return r.json()


# --- Caso base ABC123 ---

def test_degraded_source_does_not_prevail():
    s1 = next(s for s in analyze()['segments'] if s['segment_id'] == 'S1')
    assert s1['state'] == 'DELAYED' and s1['prevailing_event'] == 'E-1001'
    assert s1['conflict_detected'] is True and s1['unresolved_conflict'] is False
    assert [d['event_id'] for d in s1['discarded']] == ['E-1012']
    assert s1['informational'] == ['E-1007']


def test_missed_connection_detected():
    m = analyze()['missed_connections']
    assert m == [{'from_segment': 'S1', 'to_segment': 'S2',
                  'estimated_arrival': '2026-09-15 20:35', 'next_departure': '2026-09-15 19:05'}]


def test_policy_rules_applied_are_identifiable():
    d = analyze()
    assert d['policy_ref'] == 'POL-DELAY-2026-03'
    assert [a['rule_id'] for a in d['applied_rules']] == ['R3', 'R5']
    assert 'MEAL_VOUCHER' not in d['entitlements'] and 'CASH_COMPENSATION' not in d['entitlements']


def test_options_are_candidates_and_filtered():
    d = analyze()
    assert [o['option_id'] for o in d['candidate_options']] == ['O1']
    assert {o['option_id'] for o in d['discarded_options']} == {'O2', 'O3'}
    r = client.get('/api/trips/ABC123/options').json()
    assert 'not confirmed' in r['note']


def test_minor_forces_human_review():
    d = analyze()
    assert d['action_level'] == 'HUMAN' and d['requires_human_review'] is True
    assert d['classification'] == 'DISRUPTION_REVIEW_REQUIRED'
    assert any('R5' in reason for reason in d['human_review_reasons'])


def test_passenger_message_validated_and_without_personal_data():
    msg = analyze()['passenger_message']
    assert msg['validated'] is True and msg['policy_ref'] == 'POL-DELAY-2026-03'
    assert 'maria' not in msg['text'].lower() and 'cancel' not in msg['text'].lower()


def test_trace_covers_all_stages():
    stages = {t['stage'] for t in analyze()['decision_trace']}
    assert stages == {'reconcile', 'impact', 'policy', 'options', 'classify'}


# --- Acciones de alto impacto ---

def test_rebook_without_human_approval_rejected():
    r = client.post('/api/actions/rebook', json={'booking_id': 'ABC123', 'option_id': 'O1', 'idempotency_key': 'key-0001'})
    assert r.status_code == 409 and r.json()['error'] == 'HUMAN_APPROVAL_REQUIRED'


def test_rebook_ineligible_option_rejected():
    r = client.post('/api/actions/rebook', json={'booking_id': 'ABC123', 'option_id': 'O2', 'idempotency_key': 'key-0002',
                                                  'approved_case_id': 'HC-4471'})
    assert r.status_code == 409 and r.json()['error'] == 'OPTION_NOT_ELIGIBLE'


def test_rebook_is_idempotent():
    body = {'booking_id': 'ABC123', 'option_id': 'O1', 'idempotency_key': 'key-0003', 'approved_case_id': 'HC-4471'}
    first = client.post('/api/actions/rebook', json=body)
    second = client.post('/api/actions/rebook', json=body)
    assert first.status_code == 201 and first.json()['status'] == 'PENDING_CONFIRMATION'
    assert second.status_code == 409 and second.json() == {'error': 'DUPLICATE_REQUEST', 'request_id': first.json()['request_id']}


def test_escalate_creates_human_case():
    r = client.post('/api/actions/escalate', json={'booking_id': 'ABC123'})
    assert r.status_code == 201 and r.json()['case_id'] == 'HC-4471' and 'R5' in r.json()['reason']


def test_unknown_booking_controlled_everywhere():
    assert client.post('/api/decisions/analyze', json={'booking_id': 'NOPE'}).status_code == 404
    assert client.get('/api/trips/NOPE/options').status_code == 404


def test_notification_without_policy_ref_rejected():
    assert external.notify_passenger({'text': 'hi'})[0] == 422


# --- Escenarios adversos de la etapa 2 ---

def test_conflict_between_trusted_sources_is_unresolved():
    events = [
        {'event_id': 'A', 'segment_id': 'S1', 'type': 'DELAY', 'delay_minutes': 60, 'source': 'OPS_CORE', 'recorded_at': '2026-09-15T10:00:00Z'},
        {'event_id': 'B', 'segment_id': 'S1', 'type': 'STATUS', 'status': 'ON_TIME', 'source': 'AIRPORT_FEED', 'recorded_at': '2026-09-15T10:05:00Z'},
    ]
    r = reconcile_segment('S1', events, [], [])
    assert r['unresolved_conflict'] is True and r['state'] is None


def test_missing_fact_never_activates_rule():
    assert evaluate_condition('delay_minutes >= 180', {}) is False
    assert evaluate_condition('delay_minutes >= 240 AND international', {'delay_minutes': 300, 'international': True}) is True
