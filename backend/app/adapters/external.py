"""Mocks de los sistemas externos del examen (sección 2 del enunciado).

Los nombres y parámetros de las funciones respetan el contrato del examen.
Los datos salen literalmente de data/exam_fixtures_abc123.json, sin completar
campos faltantes. Cada llamada devuelve una copia para que ninguna capa
modifique la fuente.
"""

import copy
import json
from pathlib import Path

_FIXTURES_PATH = Path(__file__).resolve().parent.parent / "data" / "exam_fixtures_abc123.json"


def _load_fixtures() -> dict:
    with _FIXTURES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


_FIXTURES = _load_fixtures()


def get_trip_context(booking_id: str) -> dict | None:
    """Lectura. Puede devolver información parcial (ver _meta.completeness).

    Devuelve None si la reserva no existe.
    """
    trip = _FIXTURES["get_trip_context"].get(booking_id)
    return copy.deepcopy(trip) if trip is not None else None


def get_operational_events(segment_ids: list[str]) -> dict:
    """Lectura. Devuelve solo los eventos de los segmentos pedidos, con su _meta.

    El _meta del examen (incluido sources_degraded) se conserva sin cambios.
    """
    source = _FIXTURES["get_operational_events"]
    wanted = set(segment_ids)
    return {
        "events": [copy.deepcopy(e) for e in source["events"] if e["segment_id"] in wanted],
        "_meta": copy.deepcopy(source["_meta"]),
    }


def get_eligible_options(trip_context: dict) -> dict:
    """Lectura. Alternativas candidatas, no una decisión final."""
    if trip_context.get("booking_id") not in _FIXTURES["get_trip_context"]:
        return {"options": [], "_meta": {}}
    return copy.deepcopy(_FIXTURES["get_eligible_options"])


def get_policy_rules(scenario: str) -> dict | None:
    """Lectura. Reglas versionadas; None si el escenario no existe en el mock."""
    policy = _FIXTURES["get_policy_rules"].get(scenario)
    return copy.deepcopy(policy) if policy is not None else None


# --- Escritura (respuestas de ejemplo del examen) ---

_REBOOKINGS: dict[str, dict] = {}


def create_rebooking_request(option: dict, idempotency_key: str) -> tuple[int, dict]:
    """Alto impacto. Idempotente: la misma clave nunca crea una segunda solicitud."""
    sample = _FIXTURES["write_tools_sample_responses"]["create_rebooking_request"]
    if idempotency_key in _REBOOKINGS:
        return 409, {"error": "DUPLICATE_REQUEST", "request_id": _REBOOKINGS[idempotency_key]["request_id"]}
    created = {**sample["201"], "option_id": option["option_id"]}
    _REBOOKINGS[idempotency_key] = created
    return 201, copy.deepcopy(created)


def create_human_case(reason: str, evidence: list) -> tuple[int, dict]:
    sample = _FIXTURES["write_tools_sample_responses"]["create_human_case"]
    return 201, {**sample["201"], "reason": reason, "evidence_count": len(evidence)}


def notify_passenger(message: dict) -> tuple[int, dict]:
    """No envía contenido no validado: sin policy_ref responde 422, como en el examen."""
    sample = _FIXTURES["write_tools_sample_responses"]["notify_passenger"]
    if not message.get("policy_ref"):
        return 422, sample["422"]
    return 202, sample["202"]


def _reset_write_state() -> None:
    """Solo para pruebas."""
    _REBOOKINGS.clear()
