# Python model integration

This document describes the model service as inspected on the `model` branch on
23 September 2026. The Python module was not modified while preparing this integration.

## Actual processing model

The service consumes every raw sensor event and keeps its own deduplicated projection
in PostgreSQL schema `ml`. It retains approximately 45 days of events for feature
calculation.

It produces three prediction types:

- `nsd_event` after a door, hatch, or glass trigger. Processing waits for a ten-minute
  event-time window, or flushes after 15 seconds without new input;
- `fire_risk` periodically for every object touched since the previous cycle;
- `nsd_risk` in the same periodic cycle.

This module does not produce `equipment_failure`; that prediction must come from
Samir's separate service using the same output topic and contract.

One Python service hosts all three currently available models and uses one Kafka
consumer group. The equipment-failure model will be integrated later.

## Kafka and database settings

Backend topics are authoritative. Override the Python defaults with:

```dotenv
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
KAFKA_INPUT_TOPIC=sensor.events.v1
KAFKA_OUTPUT_TOPIC=predictions.v1
KAFKA_CONSUMER_GROUP=model-service.v1
DATABASE_URL=postgresql://app:app@localhost:5432/sensor_predictive
PREDICTION_INTERVAL=3600
```

The model consumer group must differ from `backend.telemetry.v1`: separate groups let
both consumers receive every sensor event. The backend prediction consumer remains
`backend.predictions.v1`.

When the model runs in the same Compose network, use `kafka:9092` and
`postgres:5432` instead of host addresses.

## Running the current service

Start Kafka, PostgreSQL, migrations, API, and worker from `backend`:

```bash
docker compose up -d --build postgres kafka kafka-init migrate api worker
```

Then, from `model/service` on a checkout containing the model artifacts, set the
environment above and run:

```bash
python -m app.main
```

Use module mode because the current source uses relative imports. The model branch's
Dockerfile currently starts `python main.py`, although the entry point is
`app/main.py`; override its command with `python -m app.main` when containerizing it.

Do not run `mock-model` together with the real model unless duplicate independent
predictions are desired.

The `.joblib` model artifacts will be copied into the Python service image. After the
model branch is merged, the Python and Go services will be built and started from one
repository and one Compose project.

## On-demand prediction

Kafka remains the transport for scheduled and event-triggered predictions. When the
frontend explicitly requests a fresh prediction, it calls the Go endpoint:

```http
POST /api/v1/predictions/request
Content-Type: application/json

{
  "object_id": 1001,
  "prediction_types": ["fire_risk", "nsd_risk"]
}
```

Go synchronously forwards this body to `POST /predict` on `MODEL_SERVICE_URL`. An
omitted `prediction_types` means every prediction type supported on demand by the
model. The Python response contract is:

```json
{
  "predictions": [
    {
      "prediction_id": "42e662ce-fdac-4892-a75e-cc7fe195db1b",
      "object_id": 1001,
      "prediction_type": "fire_risk",
      "risk_score": 0.72,
      "risk_level": "high",
      "is_alert": true,
      "predicted_at": "2026-09-23T12:00:00Z",
      "features_used": {"alarms_1h": 2},
      "model_version": "v1.0"
    }
  ]
}
```

The Python endpoint must publish the same predictions to `predictions.v1`. The HTTP
response gives the frontend an immediate result; Kafka remains the sole path for
durable Go persistence and incident creation. The current Python service does not yet
expose `POST /predict`; until it is implemented, Go returns HTTP 503 for this request.

## Wire compatibility

The Python input schema ignores the backend's extra `schema_version` field and accepts
the remaining `SensorEvent` fields.

The current model emits a prediction similar to:

```json
{
  "object_id": 9999,
  "prediction_type": "nsd_event",
  "risk_score": 0.42,
  "risk_level": "medium",
  "is_alert": true,
  "predicted_at": "2026-09-23 12:34:56.123456",
  "features_used": {"motion_before_30min": 4},
  "model_version": "v1.0"
}
```

Backend compatibility rules:

- missing `schema_version` becomes version `1` in the Kafka consumer;
- missing `prediction_id` is generated in PostgreSQL;
- Python's naive timestamp is interpreted as UTC and stored as `TIMESTAMPTZ`;
- RFC 3339 timestamps remain supported;
- `is_alert=true` creates an incident even when the generic risk level is `medium`;
- producers without `is_alert` retain the legacy high/critical incident rule;
- duplicate messages are identified by
  `(object_id, prediction_type, predicted_at, model_version)`.
- malformed or contract-invalid predictions are preserved in
  `predictions.dlq.v1`; the envelope contains the original bytes as base64, source
  topic/partition/offset, failure time and error text.

`predicted_at` is the UTC time at which inference ran, not the start of the forecast
window. Go stores it as technical metadata and does not use it to schedule inference.
`is_alert` means the model-specific threshold was crossed and is authoritative for
incident creation.

The Python service will add a stable producer-generated UUID `prediction_id`. Until
that is available, the field remains optional and the backend retains natural-key
deduplication for compatibility. `model_version` is stored as diagnostic metadata and
does not control backend behavior.

## Agreed ownership and retention

The Python service continuously writes its own projection to schema `ml`, initializes
its tables at service startup, retains events for 45 days, and prunes older rows. The
Go backend stores the complete event history in its own tables without that retention
limit. Online inference owns `ml.events` and `ml.prediction_log`; future retraining is
a separate offline process.

## Deferred decisions

- Whether a new Python consumer group processes all retained history or only events
  arriving after deployment. Do not replay the full 15 GB until this is decided.
- Python health/error signaling and its behavior for invalid Kafka records.
- The exact input/output contract for the future equipment-failure model.
- A live end-to-end test with the real `.joblib` artifacts after the branches and
  Compose definitions are merged.

The current backend smoke test uses an exact captured message shape, not live
inference.
