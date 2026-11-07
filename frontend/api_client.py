"""HTTP client for the backend.

Rules:
- The frontend decides nothing: it only consumes the contract (contracts/openapi.yaml).
- Every response becomes an ApiResult; the UI never receives an exception.
- Writes (rebook, human case) are never retried automatically.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import requests

DEFAULT_BACKEND_URL = "http://localhost:8000"
READ_TIMEOUT_S = 5
WRITE_TIMEOUT_S = 10


@dataclass
class ApiResult:
    ok: bool
    status: int | None = None
    data: Any = None
    kind: str = "ok"          # ok | unavailable | not_found | duplicate | conflict | indeterminate | invalid | not_implemented | server_error
    message: str = ""
    extra: dict = field(default_factory=dict)


def backend_url() -> str:
    return os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL).rstrip("/")


def _detail(resp: requests.Response) -> tuple[str, dict]:
    """Extract the backend error message without assuming its exact shape."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200], {}
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body.get("message") or ""
        if isinstance(detail, (list, dict)):   # FastAPI validation errors
            detail = "Invalid request data"
        return str(detail), body
    return "", {}


def classify(resp: requests.Response, *, is_write: bool) -> ApiResult:
    """Map the HTTP status to a result kind the UI knows how to display."""
    status = resp.status_code
    if 200 <= status < 300:
        try:
            data = resp.json()
        except ValueError:
            data = None
        return ApiResult(ok=True, status=status, data=data)

    message, body = _detail(resp)
    if status == 404:
        kind = "not_found"
    elif status == 405 or status == 501:
        kind = "not_implemented"
    elif status == 409:
        # 409 with request_id = request already exists (idempotency). Without it = blocked.
        kind = "duplicate" if body.get("request_id") or body.get("error") == "DUPLICATE_REQUEST" else "conflict"
    elif status == 422:
        kind = "invalid"
    elif status in (502, 503, 504) and is_write:
        # On a write the real outcome is unknown: do NOT retry.
        kind = "indeterminate"
    else:
        kind = "server_error"
    return ApiResult(ok=False, status=status, kind=kind, message=message, extra=body)


class BackendClient:
    def __init__(self, base_url: str | None = None, session: requests.Session | None = None):
        self.base_url = (base_url or backend_url()).rstrip("/")
        self.session = session or requests.Session()

    def _call(self, method: str, path: str, *, json: dict | None = None, is_write: bool = False) -> ApiResult:
        timeout = WRITE_TIMEOUT_S if is_write else READ_TIMEOUT_S
        try:
            resp = self.session.request(method, f"{self.base_url}{path}", json=json, timeout=timeout)
        except requests.Timeout:
            kind = "indeterminate" if is_write else "unavailable"
            return ApiResult(ok=False, kind=kind, message="The backend did not respond in time")
        except requests.RequestException:
            return ApiResult(ok=False, kind="unavailable", message="Could not connect to the backend")
        return classify(resp, is_write=is_write)

    # ---- Reads ----------------------------------------------------------
    def health(self) -> ApiResult:
        return self._call("GET", "/api/health")

    def get_trip(self, booking_id: str) -> ApiResult:
        return self._call("GET", f"/api/trips/{booking_id}")

    def analyze(self, booking_id: str) -> ApiResult:
        return self._call("POST", "/api/decisions/analyze", json={"booking_id": booking_id})

    # ---- Writes (high impact) ------------------------------------------
    def request_rebooking(self, booking_id: str, option_id: str, idempotency_key: str) -> ApiResult:
        payload = {"booking_id": booking_id, "option_id": option_id, "idempotency_key": idempotency_key}
        return self._call("POST", "/api/actions/rebook", json=payload, is_write=True)

    def create_human_case(self, booking_id: str, reason: str) -> ApiResult:
        payload = {"booking_id": booking_id, "reason": reason}
        return self._call("POST", "/api/actions/escalate", json=payload, is_write=True)
