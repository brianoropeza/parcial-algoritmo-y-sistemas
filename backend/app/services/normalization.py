"""Etapa 1 del pipeline (D-002): normalización de eventos por segmento.

Complejidad: O(n) para agrupar y O(n log n) en total por el ordenamiento
de cada grupo según recorded_at (n = número de eventos).
"""

from dataclasses import dataclass, field


@dataclass
class NormalizedEvents:
    by_segment: dict[str, list[dict]]
    ignored: list[dict] = field(default_factory=list)
    degraded_sources: list[str] = field(default_factory=list)


def normalize_events(events: list[dict], segment_ids: list[str], degraded_sources: list[str] | None = None) -> NormalizedEvents:
    """Agrupa los eventos por segmento de la reserva y los ordena por recorded_at.

    - Todo segmento de la reserva aparece en el resultado, aunque no tenga eventos.
    - Los eventos de segmentos ajenos a la reserva no se agrupan: quedan en
      `ignored` para que la traza pueda explicar por qué se descartaron.
    - No se elimina ningún evento de una fuente degradada: la decisión sobre su
      peso corresponde a la etapa de reconciliación (D-003).
    """
    by_segment: dict[str, list[dict]] = {sid: [] for sid in segment_ids}
    ignored: list[dict] = []
    for event in events:
        bucket = by_segment.get(event.get("segment_id"))
        if bucket is None:
            ignored.append(event)
        else:
            bucket.append(event)
    for bucket in by_segment.values():
        # Las marcas ISO 8601 en UTC con el mismo formato se ordenan correctamente como texto.
        bucket.sort(key=lambda e: e["recorded_at"])
    return NormalizedEvents(by_segment=by_segment, ignored=ignored, degraded_sources=list(degraded_sources or []))
