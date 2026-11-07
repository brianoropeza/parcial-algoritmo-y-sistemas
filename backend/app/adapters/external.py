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
