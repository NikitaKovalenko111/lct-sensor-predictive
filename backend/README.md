# Sensor Predictive Backend

Go backend for the hackathon MVP. It accepts sensor events, publishes them to Kafka,
stores telemetry and model predictions in PostgreSQL, creates dispatcher incidents for
high-risk predictions, and exposes an HTTP API documented with OpenAPI.

## Quick start with the mock model

Copy `.env.example` to `.env` and replace `JWT_SECRET` and
`BOOTSTRAP_ADMIN_PASSWORD` before the first startup. The password must contain at least
12 characters.

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
              PostgreSQL + incidents
                         |
                         v
                  REST API + SSE
```

Kafka messages are keyed by `object_id`. Backend consumers use separate consumer
groups, so telemetry persistence and the model both receive every sensor event.
Messages that cannot be decoded or fail contract validation are copied to
`sensor.events.dlq.v1` or `predictions.dlq.v1` with their source offset, original
payload and validation error. Temporary database, Kafka publication and offset-commit
failures are retried with bounded exponential backoff until shutdown.

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

The current Python service contract, environment variables, timestamp compatibility,
and launch procedure are documented in [`docs/model-integration.md`](docs/model-integration.md).

Authentication, roles, bootstrap setup, and audit behavior are documented in
[`docs/security.md`](docs/security.md).

`ObjectFeatures` is treated as a model-side/intermediate structure. The Go backend
does not calculate it; selected values can be returned in `features_used` for display.

## Commands

- `cmd/api` — HTTP API, health checks and Kafka producer.
- `cmd/worker` — Kafka consumers that persist telemetry and predictions.
- `cmd/mock-model` — replaceable development stand-in for Python models.
- `cmd/simulator` — synthetic near-real-time sensor events.
- `cmd/importer` — streaming CSV import for objects, channels and historical events.

## Internal packages

- `internal/config` — environment configuration.
- `internal/contracts` — versioned Kafka DTOs shared with Python.
- `internal/objects` — infrastructure hierarchy and synthetic GeoJSON geometry.
- `internal/channels` — sensor registry and channel-to-object lookup.
- `internal/importer` — streaming CSV parsing and batch import orchestration.
- `internal/importjob` — import status and progress persistence.
- `internal/platform/database` — PostgreSQL connection infrastructure.
- `internal/platform/kafka` — Kafka producer/consumer construction.
- `internal/telemetry` — sensor-event publishing and persistence.
- `internal/prediction` — prediction consumption, validation and queries.
- `internal/incidents` — dispatcher incidents, decisions, work-order drafts and SSE notifications.
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

## Import historical data

Import files in dependency order: objects, channels, then events. The importer accepts
comma-, semicolon- and tab-separated UTF-8 CSV files and recognizes both the original
Russian headers and normalized English aliases.

```bash
go run ./cmd/importer \
  --objects /data/objects.csv \
  --channels /data/channels.csv \
  --events /data/ext-journal-2026.csv \
  --batch-size 500
```

For Docker, mount the dataset read-only and enable the tools profile:

```bash
docker compose --profile tools run --rm \
  -v /absolute/path/to/data:/data:ro \
  importer \
  --objects /data/objects.csv \
  --channels /data/channels.csv \
  --events /data/ext-journal-2026.csv
```

Large event files are never loaded fully into memory. Events are enriched through the
channel registry and published to Kafka in batches. Progress is available at
`GET /api/v1/imports` and `GET /api/v1/imports/{import_id}`.

## Object map

The source dataset has no usable real coordinates. During object import the backend
generates deterministic schematic `MultiLineString` geometry. Every GeoJSON feature is
explicitly marked with `synthetic: true`.

```text
GET /api/v1/objects
GET /api/v1/objects/{object_id}
GET /api/v1/channels?object_id=...
GET /api/v1/map/objects.geojson
```

## Dispatcher incidents and notifications

A prediction creates an incident when the real model sets `is_alert=true`. Legacy
producers without this field use `high` or `critical`. A unique constraint on
`prediction_id` prevents Kafka retries from creating duplicates.

```text
GET   /api/v1/incidents
GET   /api/v1/incidents/{incident_id}
PATCH /api/v1/incidents/{incident_id}/assignment
POST  /api/v1/incidents/{incident_id}/decisions
POST  /api/v1/incidents/{incident_id}/resolve
POST  /api/v1/incidents/{incident_id}/work-order-draft
GET   /api/v1/incidents/stream
```

The stream endpoint uses Server-Sent Events. PostgreSQL `LISTEN/NOTIFY` carries
incident changes from the worker/API processes to each connected HTTP client.
