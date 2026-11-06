# Disruption Companion — Backend vertical slice

## Run

```sh
docker compose up --build -d
docker compose exec backend pytest -q
```

Swagger: http://localhost:8000/docs

## Example

```sh
curl -X POST http://localhost:8000/api/decisions/analyze -H 'Content-Type: application/json' -d '{"booking_id":"ABC123"}'
```

## OpenSpec

Install OpenSpec CLI separately, run `openspec init` if needed, then review `openspec/changes/disruption-decision-engine/` and validate using `openspec validate disruption-decision-engine`. OpenSpec files in this starter are authored artifacts, not evidence that the CLI has been executed.

## Scope and limitations

Implements a conservative first slice, NOT the full exam: policy verification, alternative options, human case creation, notification, idempotent rebooking and authorization remain TODO. The mock fixture is illustrative. Do not send passenger personal contact details to the frontend. The API contract and implementation must evolve together.
