# Disruption Companion — Engineering README

Examen final 2026-B · Análisis de Algoritmos y Sistemas · UDES · Backend: Brian Oropeza · Frontend: Diego Triana

## 1. Problema y resultado esperado
Nubara Airlines necesita explicar a un pasajero qué pasó con su itinerario modificado, qué le corresponde según la política y cuándo interviene una persona, sin comunicar información no validada ni ejecutar acciones de alto impacto sin control. Resultado: un backend FastAPI con un motor de decisiones determinista que combina reserva, eventos operacionales, alternativas y políticas versionadas.

**Caso base ABC123 (resultado verificado por pruebas):** S1 (NB500) está retrasado 160 min según OPS_CORE. El `ON_TIME` de LEGACY_MIRROR se descarta porque la fuente está degradada y su dato es más antiguo. La llegada estimada a LIM es 20:35, después de la salida de S2 (19:05), así que la conexión se pierde. Aplican R3 (`REBOOK_NO_FEE`) y R5 (menor en el grupo, que exige aprobación humana). No aplican R1 ni R2 (160 < 180/240), por lo que no hay voucher de comida. O1 (NB2412, 16-09 08:15) es la única alternativa candidata; O2 se descarta (1 asiento para 2 pasajeros y diferencia de tarifa) y O3 también (política de reembolso no consultada y confianza LOW). Nivel de automatización: **HUMAN**. El sistema explica y muestra O1, pero la reubicación requiere un caso humano aprobado.

## 2. Supuestos y alcance
- Los datos simulados son la transcripción literal del examen (`backend/app/data/exam_fixtures_abc123.json`). Los campos faltantes (`change_penalty_amount`) se informan y no se rellenan.
- La llegada estimada es `scheduled_arrival + delay_minutes` en hora local (supuesto: la duración del vuelo no cambia).
- Implementado: los 7 contratos del examen como mocks, las 5 etapas del motor, los endpoints `trips`, `events`, `options`, `analyze`, `rebook` (idempotente) y `escalate`, y la validación del mensaje al pasajero.
- Fuera de alcance: frontend (lo hace el compañero), persistencia real, autenticación y verificación real de `approved_case_id`.

## 3. Decisiones principales y alternativas descartadas
El detalle completo está en `docs/DECISIONS.md` (D-001 a D-009).
| Decisión | Elegida | Descartada |
|---|---|---|
| Algoritmo (D-002) | Pipeline determinista en 5 etapas | Tabla única de reglas; agente con IA |
| Conflicto de fuentes (D-003) | Jerarquía de confianza; la fuente degradada nunca prevalece; conflicto entre fuentes confiables → humano | "El dato más reciente gana" |
| Datos personales (D-006) | La API devuelve solo id, nombre y tipo | Exponer la reserva completa |
| Regla humana R5 (D-007) | Bloquea toda acción de alto impacto del caso | Bloquear solo el manejo prioritario |
| Alternativas (D-009) | Filtro por asientos, tarifa, política y confianza; orden lexicográfico | Mostrar todas las alternativas tal como llegan |

## 4. Algoritmo y complejidad
| Etapa | Archivo | Complejidad |
|---|---|---|
| 1 Normalizar eventos por segmento | `services/normalization.py` | O(n log n) |
| 2 Reconciliar fuentes | `services/engine.py · reconcile_segment` | O(n) |
| 3 Impacto en conexiones | `connection_impact` | O(s) |
| 4 Evaluar política (parser seguro, sin `eval`) | `evaluate_policy` | O(r) |
| 5 Filtrar y ordenar alternativas | `filter_options` | O(m log m) |
Cada etapa agrega pasos a `decision_trace`, que se devuelve en `/api/decisions/analyze`.

## 5. Determinista, IA y humano
| Paso | Clasificación | Riesgo | Control / fallback |
|---|---|---|---|
| Reconciliar eventos, conexión, reglas y alternativas | Determinista | Datos contradictorios | Jerarquía de fuentes; conflicto no resuelto → humano |
| Mensaje al pasajero | Determinista (plantilla) | Comunicar algo no validado | Solo hechos del motor; `notify_passenger` rechaza mensajes sin `policy_ref` (422) |
| Reubicación | Humano o confirmación del pasajero | Costo e incumplimiento de política | Opción candidata, aprobación humana (D-007) e idempotencia |
| Compensación / reembolso | Humano | Alto costo | Nunca automático |
No se usa IA en tiempo de ejecución. Las reglas son verificables y la IA agregaría latencia, costo y falta de reproducibilidad sin beneficio para este alcance. Un uso futuro posible sería redactar el texto del mensaje a partir de los campos ya validados, sin acceso a datos personales.

## 6. Cómo ejecutar y validar
```powershell
# Sin Docker
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend; ..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000   # http://localhost:8000/docs
# Con Docker (pendiente de verificar: WSL 2 en instalación)
docker compose up --build -d; docker compose exec backend pytest -q
```
Validación: **27 pruebas automatizadas pasan** (caso base, fuente degradada, conflicto entre fuentes confiables, conexión perdida, reglas, filtro de alternativas, aprobación humana, idempotencia, escalamiento, 404, notificación sin `policy_ref`, datos personales).

## 7. Riesgos, limitaciones y próximos pasos
- `approved_case_id` no se verifica contra un sistema real de aprobaciones. Próximo paso: un registro de casos aprobados.
- Idempotencia en memoria; se pierde al reiniciar. Próximo paso: persistencia.
- No se maneja todavía `503 UPSTREAM_TIMEOUT`; la estrategia propuesta es reintentar con la misma clave.
- No se verifica el TTL de las alternativas (120 s).
- La correspondencia aeropuerto → país está fija en el código para la condición `international`.
- Docker no se ha verificado en el equipo de desarrollo.
