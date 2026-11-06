from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    assert client.get('/api/health').json() == {'status': 'ok'}

def test_unknown_booking():
    assert client.get('/api/trips/UNKNOWN').status_code == 404

def test_analyze_preserves_conflict_and_blocks_action():
    result = client.post('/api/decisions/analyze', json={'booking_id':'ABC123'})
    assert result.status_code == 200
    data = result.json()
    assert data['requires_human_review'] is True
    assert data['can_auto_rebook'] is False
    assert any(e['source'] == 'LEGACY_MIRROR' for e in data['evidence'])
    assert any('disagree' in w for w in data['warnings'])

def test_rebooking_blocked():
    assert client.post('/api/actions/rebook').status_code == 409
