import json

import pytest
import requests

from api_client import ApiResult, BackendClient, classify
from presenter import (action_feedback, decision_view, normalize_booking_id,
                       rebook_permission, safe_trip)

# get_trip_context("ABC123") response as given in the case statement (includes personal data).
TRIP_FROM_EXAM = {
    "booking_id": "ABC123",
    "passengers": [
        {"passenger_id": "P1", "name": "María Silva", "type": "ADULT", "email": "maria.silva@example.com",
         "phone": "+56 9 8765 4321", "document_id": "12.345.678-9", "loyalty_tier": "GOLD"},
        {"passenger_id": "P2", "name": "Tomás Silva", "type": "CHILD", "age": 7},
    ],
    "segments": [
        {"segment_id": "S1", "flight_number": "NB500", "origin": "SCL", "destination": "LIM",
         "date": "2026-09-15", "scheduled_departure": "14:30", "scheduled_arrival": "17:55"},
        {"segment_id": "S2", "flight_number": "NB2410", "origin": "LIM", "destination": "MEX",
         "date": "2026-09-15", "scheduled_departure": "19:05", "scheduled_arrival": "23:40"},
    ],
    "_meta": {"completeness": "PARTIAL", "missing_fields": ["fare_conditions.change_penalty_amount"]},
}

# CURRENT backend response (contract v0.1.0): no options.
DECISION_V01 = {
    "booking_id": "ABC123", "classification": "DISRUPTION_REVIEW_REQUIRED",
    "recommendation": "Verify the operational status...", "requires_human_review": True,
    "can_auto_rebook": False, "warnings": ["Operational sources disagree about segment S1"],
    "evidence": [
        {"event_id": "E-1001", "segment_id": "S1", "type": "DELAY", "source": "OPS_CORE",
         "recorded_at": "2026-09-15T10:48:00Z", "delay_minutes": 160},
        {"event_id": "E-1012", "segment_id": "S1", "type": "STATUS", "source": "LEGACY_MIRROR",
         "recorded_at": "2026-09-15T09:30:00Z", "status": "ON_TIME"},
    ],
    "policy_ref": None, "analyzed_at": "2026-09-15T11:03:00Z",
}

# Proposed EXTENDED response: missed connection, O1 recommended, minor => human approval.
DECISION_EXTENDED = {
    **DECISION_V01,
    "classification": "MISSED_CONNECTION", "missed_connection": True,
    "policy_ref": "POL-DELAY-2026-03", "applied_rules": ["R3", "R5"],
    "sources_degraded": ["LEGACY_MIRROR"],
    "recommended_option": {"option_id": "O1", "type": "REBOOK", "flight_number": "NB2412", "origin": "LIM",
                           "destination": "MEX", "date": "2026-09-16", "departure": "08:15",
                           "policy_ref": "POL-DELAY-2026-03"},
    "discarded_options": [
        {"option_id": "O2", "type": "REBOOK", "flight_number": "NB2450",
         "reason": "Only 1 seat for 2 passengers and fare difference"},
        {"option_id": "O3", "type": "REFUND", "reason": "Non-refundable fare"},
    ],
}


# ---------------------------------------------------------------- input validation
@pytest.mark.parametrize("raw, expected", [("ABC123", "ABC123"), ("  abc123 ", "ABC123")])
def test_booking_id_valid(raw, expected):
    assert normalize_booking_id(raw) == (expected, None)


@pytest.mark.parametrize("raw", ["", None, "AB", "ABC/../1", "ABC123; DROP", "ÑANDÚ12"])
def test_booking_id_rejected_before_calling_backend(raw):
    value, error = normalize_booking_id(raw)
    assert value is None and error


# ---------------------------------------------------------------- privacy
def test_safe_trip_never_exposes_personal_data():
    view = safe_trip(TRIP_FROM_EXAM)
    dumped = json.dumps(view, ensure_ascii=False)
    for secret in ("maria.silva@example.com", "+56 9 8765 4321", "12.345.678-9", "GOLD"):
        assert secret not in dumped
    assert view["has_minor"] is True
    assert view["completeness"] == "PARTIAL"


# ---------------------------------------------------------------- decision
def test_current_backend_response_renders_and_blocks_rebook():
    view = decision_view(DECISION_V01)
    assert view["recommended_option"] is None
    assert len(view["evidence"]) == 2
    allowed, reason = rebook_permission(view)
    assert allowed is False and reason


def test_extended_response_recommends_o1_but_requires_human_for_minor():
    view = decision_view(DECISION_EXTENDED)
    assert view["recommended_option"]["option_id"] == "O1"
    assert [o["option_id"] for o in view["discarded_options"]] == ["O2", "O3"]
    assert any("(degraded)" in e["Source"] for e in view["evidence"])
    allowed, reason = rebook_permission(view)
    assert allowed is False and "agent" in reason


def test_rebook_enabled_only_when_backend_authorizes():
    view = decision_view({**DECISION_EXTENDED, "requires_human_review": False, "can_auto_rebook": True})
    assert rebook_permission(view) == (True, "")


def test_missing_fields_default_to_safe_values():
    view = decision_view({"booking_id": "ABC123"})
    assert view["requires_human_review"] is True and view["can_auto_rebook"] is False


# ---------------------------------------------------------------- HTTP errors
def _resp(status, body):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(body).encode()
    return r


def test_409_with_request_id_is_duplicate_not_new_request():
    res = classify(_resp(409, {"error": "DUPLICATE_REQUEST", "request_id": "RBK-88231"}), is_write=True)
    level, msg = action_feedback(res, "rebook")
    assert res.kind == "duplicate" and "RBK-88231" in msg and level == "info"


def test_409_from_current_backend_is_blocked():
    res = classify(_resp(409, {"detail": "Rebooking disabled until policy..."}), is_write=True)
    assert res.kind == "conflict"


def test_503_on_write_is_indeterminate_and_says_do_not_retry():
    res = classify(_resp(503, {"error": "UPSTREAM_TIMEOUT"}), is_write=True)
    level, msg = action_feedback(res, "rebook")
    assert res.kind == "indeterminate" and "Do not repeat it" in msg


def test_422_and_success_messages():
    assert classify(_resp(422, {"detail": [{"msg": "x"}]}), is_write=True).kind == "invalid"
    ok = classify(_resp(201, {"case_id": "HC-4471", "queue": "DISRUPTION_L2", "sla_minutes": 45}), is_write=True)
    level, msg = action_feedback(ok, "human")
    assert level == "success" and "HC-4471" in msg and "45" in msg


class _FailingSession:
    def __init__(self, exc):
        self.exc = exc

    def request(self, *args, **kwargs):
        raise self.exc


def test_backend_down_returns_result_not_exception():
    client = BackendClient("http://backend:8000", session=_FailingSession(requests.ConnectionError()))
    assert client.get_trip("ABC123").kind == "unavailable"


def test_write_timeout_is_indeterminate():
    client = BackendClient("http://backend:8000", session=_FailingSession(requests.Timeout()))
    res = client.request_rebooking("ABC123", "O1", "ABC123-O1-key")
    assert res.kind == "indeterminate"
    assert action_feedback(res, "rebook")[0] == "warning"


def test_unimplemented_action_is_reported_cleanly():
    level, _ = action_feedback(ApiResult(ok=False, status=404, kind="not_found"), "human")
    assert level == "info"


def test_escalate_classification_forces_human_review_and_shows_trace():
    view = decision_view({**DECISION_EXTENDED, "classification": "ESCALATE_HUMAN",
                          "requires_human_review": False, "can_auto_rebook": True,
                          "decision_trace": [{"stage": "reconcile_sources", "result": "LEGACY_MIRROR discarded"},
                                             "missed connection: 20:35 > 19:05"]})
    assert view["requires_human_review"] is True
    assert rebook_permission(view)[0] is False
    assert view["decision_trace"][0] == "reconcile_sources: LEGACY_MIRROR discarded"


# ---------------------------------------------------------------- real backend contract
# tests/backend_abc123.json = actual output of the backend engine for ABC123 (GET trip + POST analyze).
REAL = json.load(open(__import__("pathlib").Path(__file__).parent / "backend_abc123.json", encoding="utf-8"))


def test_real_backend_response_is_rendered_correctly():
    view = decision_view(REAL["decision"])
    assert view["missed_connection"] is True
    assert view["missed_connections"][0]["estimated_arrival"].endswith("20:35")
    assert view["recommended_option"]["option_id"] == "O1"
    assert {o["option_id"] for o in view["discarded_options"]} == {"O2", "O3"}
    assert all(o["reason"] != "Not recommended" for o in view["discarded_options"])
    assert "Rebooking at no extra cost" in view["entitlements"]
    assert any(r.startswith("R5") and "human approval" in r for r in view["applied_rules"])
    legacy = next(e for e in view["evidence"] if e["Event"] == "E-1012")
    assert legacy["Used"].startswith("No")
    assert view["decision_trace"] and all(isinstance(line, str) for line in view["decision_trace"])


def test_real_backend_minor_blocks_rebook_with_reason():
    allowed, reason = rebook_permission(decision_view(REAL["decision"]))
    assert allowed is False and "R5" in reason


def test_automatic_with_confirmation_enables_rebook():
    d = {**REAL["decision"], "action_level": "AUTOMATIC_WITH_CONFIRMATION",
         "requires_human_review": False, "human_review_reasons": []}
    assert rebook_permission(decision_view(d)) == (True, "")


def test_real_trip_has_no_personal_data():
    trip = safe_trip(REAL["trip"])
    assert [p["type_text"] for p in trip["passengers"]] == ["Adult", "Child"]
    assert "email" not in json.dumps(REAL["trip"])


def test_backend_conflict_codes_are_human_readable():
    res = classify(_resp(409, {"error": "HUMAN_APPROVAL_REQUIRED", "reasons": ["R5"]}), is_write=True)
    assert res.kind == "conflict"
    assert "agent must approve" in action_feedback(res, "rebook")[1]


def test_escalate_endpoint_is_used():
    class Capture:
        def request(self, method, url, **kw):
            self.url = url
            return _resp(201, {"case_id": "HC-4471", "sla_minutes": 45})
    session = Capture()
    BackendClient("http://backend:8000", session=session).create_human_case("ABC123", "x")
    assert session.url.endswith("/api/actions/escalate")
