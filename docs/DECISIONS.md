# Registro de decisiones — Disruption Companion

Registro de decisiones de ingeniería del backend. Las entradas no se borran: si una decisión cambia, se marca como "Reemplazada por D-00X" y se agrega una nueva.

Estados posibles: Propuesta · Aprobada · Rechazada · Reemplazada.

| ID | Decisión | Estado |
|---|---|---|
| D-001 | Registro de decisiones en dos capas | Aprobada |
| D-002 | Algoritmo: pipeline determinista por etapas | Aprobada |
| D-003 | Jerarquía de confianza de fuentes operacionales | Aprobada |
| D-004 | Regla de conexión perdida | Aprobada |
| D-005 | Niveles de automatización | Aprobada |
| D-006 | Exposición mínima de datos personales | Aprobada |
| D-007 | Alcance de las reglas con aprobación humana (R5) | Aprobada |
| D-008 | Cálculo de la llegada estimada | Aprobada |
| D-009 | Filtro y orden de alternativas | Aprobada |

---

## D-001 — Registro de decisiones en dos capas

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** El examen exige trazabilidad de las fuentes y de las decisiones, y los entregables (Engineering README y AI Usage & Decision Note) piden documentar decisiones, alternativas descartadas y uso de IA.
- **Opciones evaluadas:**
  - Solo registro de ingeniería (documento).
  - Solo traza del sistema en tiempo de ejecución.
  - Ambas capas.
- **Decisión:** Ambas capas.
  1. **Ingeniería:** este archivo (`docs/DECISIONS.md`), una entrada por decisión.
  2. **Sistema:** cada análisis produce una traza (`decision_trace`) con las entradas consideradas, las reglas aplicadas, la evidencia usada y descartada, y el resultado. Además se guarda un registro de auditoría local.
- **Consecuencias:**
  - El contrato OpenAPI de `Decision` deberá ampliarse con `decision_trace`. El cambio es aditivo y se coordinará con el frontend antes de aplicarlo.
  - Cada decisión del motor queda explicable con evidencia.
- **Uso de IA:** La propuesta fue generada con Claude. La aprobó Brian.

---

## D-002 — Algoritmo: pipeline determinista por etapas

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** El análisis actual (`analyze`) devuelve siempre `DISRUPTION_REVIEW_REQUIRED`, porque la clasificación está fija en el código. Se necesita un motor que decida a partir de la reserva, los eventos, las alternativas y las políticas.
- **Opciones evaluadas:**
  - **A. Tabla de decisión única (primera regla que se cumple).** Es simple, pero mezcla la reconciliación de fuentes con la clasificación y resuelve mal los conflictos.
  - **B. Pipeline determinista por etapas.** Cada etapa se puede probar por separado y deja traza.
  - **C. Agente con IA y herramientas.** No es reproducible, tiene mayor latencia y costo, y el enunciado desaconseja usar IA en problemas deterministas.
- **Decisión:** Opción B, con estas etapas:

  | # | Etapa | Descripción | Complejidad |
  |---|---|---|---|
  | 1 | Normalizar eventos | Agrupar los eventos por segmento | O(n) |
  | 2 | Reconciliar fuentes | Aplicar la jerarquía de confianza (D-003) y detectar contradicciones | O(n) |
  | 3 | Calcular impacto | Calcular la llegada estimada y verificar las conexiones (D-004) | O(s) |
  | 4 | Clasificar | Aplicar la tabla de decisión: `INFORMAR`, `OFRECER_OPCIONES` o `ESCALAR_HUMANO` (D-005) | O(r) |
  | 5 | Evaluar alternativas | Filtrar por restricciones y ordenar lexicográficamente | O(m log m) |

  Variables: n = eventos, s = segmentos, r = reglas, m = alternativas. Cada etapa agrega su paso a `decision_trace`.
- **Consecuencias:**
  - La lógica sale de `main.py` y se organiza en servicios separados por responsabilidad.
  - La etapa 5 queda bloqueada hasta tener los datos exactos de alternativas y políticas del examen.
  - Si se usa IA más adelante, será solo para redactar mensajes a partir de datos ya validados. Eso requerirá una decisión aparte.
- **Uso de IA:** Las opciones y el análisis fueron propuestos con Claude. Brian eligió B.

---

## D-003 — Jerarquía de confianza de fuentes operacionales

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** En S1, OPS_CORE informa un retraso de 160 minutos, AIRPORT_FEED un cambio de puerta y LEGACY_MIRROR (degradada) el estado `ON_TIME`. El sistema no debe dar prioridad automática a una fuente degradada ni elegir simplemente el dato más reciente.
- **Decisión:**
  - **Orden de confianza:** OPS_CORE > AIRPORT_FEED > LEGACY_MIRROR.
  - **Fuente degradada:** no puede prevalecer. Se conserva como evidencia y se informa como descartada en la traza.
  - **Contradicción entre fuentes no degradadas:** si dos fuentes no degradadas se contradicen sobre el estado del mismo segmento, el caso se escala a un humano.
  - **Prioridad de los datos del examen:** si el examen define niveles de confiabilidad por evento, se usan esos valores en lugar de este orden. Esta decisión se actualizará cuando se verifiquen los datos.
- **Verificación con el examen (2026-11-06):** El examen no trae un nivel de confiabilidad por evento. La degradación de una fuente se informa en `get_operational_events._meta.sources_degraded` (`["LEGACY_MIRROR"]`). El orden de esta decisión se mantiene. Además, el evento de LEGACY_MIRROR (E-1012, 09:30Z) es más antiguo que el de OPS_CORE (E-1001, 10:48Z).
- **Consecuencias:** Para ABC123, el retraso de OPS_CORE prevalece y el `ON_TIME` de LEGACY_MIRROR queda registrado como contradicción con una fuente degradada.
- **Uso de IA:** La propuesta fue hecha con Claude. La aprobó Brian.

---

## D-004 — Regla de conexión perdida

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** Se necesita una regla verificable para decidir si una modificación es relevante.
- **Decisión:** Una conexión se considera perdida si la llegada estimada del segmento anterior es posterior a la salida programada del siguiente. Si el examen define un tiempo mínimo de conexión, la regla se convierte en `llegada_estimada + tiempo_mínimo > salida_siguiente`.
- **Consecuencias:** Para ABC123, S1 llega a las 17:55 + 160 min = 20:35, y S2 sale a las 19:05. La conexión se pierde, por lo que la modificación es relevante.
- **Uso de IA:** La propuesta fue hecha con Claude. El cálculo debe verificarse con pruebas automatizadas. La aprobó Brian.

---

## D-005 — Niveles de automatización

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** Cambiar reservas o emitir compensaciones son acciones de alto impacto (restricción 3 del examen).
- **Decisión:**

  | Nivel | Qué hace el sistema | Cuándo aplica |
  |---|---|---|
  | Automático | Clasifica, explica y notifica con datos validados | Las fuentes confiables coinciden, los datos están completos y la política está identificada |
  | Automático con confirmación | Presenta alternativas candidatas; la reubicación se solicita solo si el pasajero elige una y la política la permite | Hay alternativas válidas, no hay costo adicional ni conflicto entre fuentes |
  | Humano | Crea un caso con la evidencia y no ejecuta acciones | Hay contradicción entre fuentes confiables, faltan datos que afectan la decisión, hay compensaciones, o el caso lo exige la política (por ejemplo, por viajar un menor) |

  Toda reubicación requiere una clave de idempotencia.
- **Consecuencias:** Para ABC123, el sistema detecta e informa el retraso y la conexión perdida de forma automática. Si la reubicación puede ofrecerse automáticamente o debe pasar a revisión humana depende de las políticas del examen, que aún están pendientes de verificar.
- **Uso de IA:** La propuesta fue hecha con Claude. La aprobó Brian.

---

## D-006 — Exposición mínima de datos personales

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** `get_trip_context` del examen devuelve email, teléfono, documento y `loyalty_tier` de María, y la edad de Tomás. Restricción 4 del examen: proteger datos personales con mínimo privilegio.
- **Decisión:**
  - El mock conserva literalmente los datos del examen, para respetar el contrato.
  - La API devuelve por pasajero solo `passenger_id`, `name` y `type`.
  - La API nunca devuelve email, teléfono, `document_id`, `loyalty_tier` ni edad. La condición de menor se deduce de `type: CHILD`.
  - Estos datos tampoco se envían a ningún modelo de IA.
- **Consecuencias:** `GET /api/trips/{booking_id}` cambia su forma: las fechas y horas de los segmentos quedan separadas, como en el examen, y se agregan `missing_fields` y `completeness`. El contrato se documentó como `TripPublic`. Hay que avisar al frontend.
- **Uso de IA:** La propuesta fue hecha con Claude. La aprobó Brian. La verifica la prueba `test_trip_endpoint_exposes_minimum_personal_data`.

---

## D-007 — Alcance de las reglas con aprobación humana (R5)

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** En ABC123 aplican R3 (`missed_connection` → `REBOOK_NO_FEE`, sin aprobación humana) y R5 (`group_includes_minor` → `PRIORITY_HANDLING`, con aprobación humana). La alternativa O1 implica pasar la noche en Lima con un menor, y ninguna regla de la política cubre el hotel.
- **Opciones evaluadas:**
  - **A.** La aprobación humana aplica solo al manejo prioritario. El pasajero podría solicitar O1 por sí mismo.
  - **B.** Si alguna regla aplicable exige aprobación humana, toda acción de alto impacto del caso pasa por una persona.
- **Decisión:** Opción B. El sistema explica, muestra las alternativas candidatas y crea el caso humano con la evidencia. La reubicación queda pendiente de aprobación.
- **Consecuencias:** Es más conservadora: en este caso un operador interviene, con un SLA de 45 minutos según el examen. Evita prometer hotel o comida que la política no cubre.
- **Uso de IA:** Claude propuso las opciones. Brian eligió B.

---

## D-008 — Cálculo de la llegada estimada

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** El evento de retraso trae `new_departure` y `delay_minutes`, pero no la nueva hora de llegada. Las horas son locales (SCL y LIM están en zonas horarias distintas).
- **Decisión:** `llegada_estimada = scheduled_arrival + delay_minutes`, en la hora local del aeropuerto de llegada. Se compara con la salida del siguiente segmento, que está en el mismo aeropuerto y la misma zona horaria.
- **Supuesto documentado:** la duración del vuelo no cambia.
- **Consecuencias:** Para S1: 17:55 + 160 min = 20:35 en LIM, después de las 19:05 → conexión perdida (D-004).
- **Uso de IA:** La propuesta fue hecha con Claude. La aprobó Brian.

---

## D-009 — Filtro y orden de alternativas

- **Estado:** Aprobada
- **Fecha:** 2026-11-06 · **Aprobó:** Brian (backend)
- **Contexto:** `get_eligible_options` entrega alternativas candidatas, no decisiones. Tienen un `ttl_seconds` de 120.
- **Decisión:** Una alternativa se descarta si:
  1. tiene menos asientos (`seats_available`) que pasajeros;
  2. tiene `fare_difference > 0` cuando el derecho aplicable es `REBOOK_NO_FEE`;
  3. su `policy_ref` no corresponde a una política consultada y vigente;
  4. su `confidence` es `LOW`.

  Las restantes se ordenan por confianza (HIGH > MEDIUM), luego por diferencia de tarifa y luego por hora de llegada. Si pasó el TTL, las alternativas se vuelven a consultar antes de cualquier reubicación.
- **Consecuencias para ABC123:**
  - **O1:** candidata.
  - **O2:** descartada por las condiciones 1 y 2.
  - **O3:** descartada por las condiciones 3 y 4. Además, la tarifa no es reembolsable.
- **Uso de IA:** La propuesta fue hecha con Claude. La aprobó Brian.

---

## Pendientes que generarán nuevas decisiones

- Ampliación del contrato OpenAPI (`decision_trace`, `options`, `escalate`), a coordinar con el frontend.
- Manejo de `503 UPSTREAM_TIMEOUT` (resultado indeterminado) en `create_rebooking_request`: reintentar con la misma clave de idempotencia.
- Contenido mínimo validado de `notify_passenger` (el examen rechaza mensajes sin `policy_ref`).
