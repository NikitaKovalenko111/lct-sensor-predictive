# Sensor Predictive Backend

Go backend for the hackathon MVP. It accepts sensor events, publishes them to Kafka,
stores telemetry and model predictions in PostgreSQL, and exposes an HTTP API documented
with OpenAPI.

## Quick start with the mock model

```bash
docker compose --profile mock --profile demo up --build
```

After startup:

- API: <http://localhost:8080>
- OpenAPI file: <http://localhost:8080/api/openapi.yaml>
- Swagger UI: <http://localhost:8081>
- PostgreSQL: `localhost:5432`
- Kafka from the host: `localhost:29092`

The `demo` profile publishes one synthetic temperature event every five seconds.
The `mock` profile consumes these events and publishes predictions using the same
contract expected from the Python model.

## Data flow

```text
POST /api/v1/sensor-events or simulator
                  |
                  v
          sensor.events.v1
             /         \
            v           v
   telemetry worker   Python model / mock-model
            |           |
            v           v
       PostgreSQL   predictions.v1
                         |
                         v
                 prediction worker
                         |
                         v
                    PostgreSQL
```

Kafka messages are keyed by `object_id`. Backend consumers use separate consumer
groups, so telemetry persistence and the model both receive every sensor event.

## Model contract

The source of truth for JSON fields is `internal/contracts/model.go`.

- Input topic: `sensor.events.v1`
- Output topic: `predictions.v1`
- JSON timestamp format: RFC 3339, preferably UTC
- Kafka key: decimal `object_id`
- Delivery semantics: at least once; consumers must be idempotent
- Current schema version: `1`

The original Python `Prediction` contract has no `prediction_id`. Therefore backend
deduplication currently uses `(object_id, prediction_type, predicted_at, model_version)`.
Adding a UUID `prediction_id` is recommended but optional for compatibility.

`ObjectFeatures` is treated as a model-side/intermediate structure. The Go backend
does not calculate it; selected values can be returned in `features_used` for display.

## Commands

- `cmd/api` — HTTP API, health checks and Kafka producer.
- `cmd/worker` — Kafka consumers that persist telemetry and predictions.
- `cmd/mock-model` — replaceable development stand-in for Python models.
- `cmd/simulator` — synthetic near-real-time sensor events.
- `cmd/importer` — reserved for the streaming CSV/XLSX import command.

## Internal packages

- `internal/config` — environment configuration.
- `internal/contracts` — versioned Kafka DTOs shared with Python.
- `internal/platform/database` — PostgreSQL connection infrastructure.
- `internal/platform/kafka` — Kafka producer/consumer construction.
- `internal/telemetry` — sensor-event publishing and persistence.
- `internal/prediction` — prediction consumption, validation and queries.
- `internal/mockmodel` — deterministic mock implementation of the Python model contract.
- `internal/transport/httpapi` — REST routes and middleware.

## Local development without containers

Copy `.env.example` values into your shell, start PostgreSQL and Kafka, apply files
from `migrations`, then run:

```bash
go run ./cmd/api
go run ./cmd/worker
go run ./cmd/mock-model
```
