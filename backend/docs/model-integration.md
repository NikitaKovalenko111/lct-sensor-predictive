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

The next shared-contract revision should add a producer-generated `prediction_id`, a
source window/correlation identifier, explicit timezone-aware RFC 3339 timestamps,
`schema_version`, and the prediction horizon. Until then these fields must remain
optional for compatibility with the current model service.

## Required answers before enabling the real service

Do not enable the Python consumer for a full historical import until the ML team has
answered these questions:

1. Should the service consume the full 15 GB replay from `sensor.events.v1`, or only
   events arriving after deployment? Its current `auto_offset_reset="earliest"` can
   process the entire retained topic for a new consumer group.
2. Is one consumer group (`model-service.v1`) shared by all three models, or will fire,
   NSD event, NSD risk, and Samir's equipment-failure model run as separate consumers?
3. Is `is_alert` authoritative for dispatcher incidents for every prediction type, or
   should some types still use common risk-level thresholds?
4. Is the naive `predicted_at` value always UTC? The backend currently interprets it as
   UTC for compatibility.
5. What are the exact forecast horizon, source-window end time, and correlation ID for
   each prediction? These are required to explain and deduplicate periodic forecasts.
6. Will the model generate a stable UUID `prediction_id`, especially when retrying a
   calculation?
7. Where will all `.joblib` artifacts be mounted, and how will their version/checksum be
   reported as `model_version`?
8. Should schema `ml` live in the backend PostgreSQL database or in a separate model
   database, and who owns its migrations and retention policy?
9. What health/error signal should backend and monitoring receive when feature
   calculation or inference fails?
10. What exact input/output contract and consumer group will Samir's
    `equipment_failure` service use?
11. Will the model branch be merged into the deployment branch, included through a Git
    worktree, or built as an independently versioned image?

After these answers, run an end-to-end test with the real `.joblib` artifacts. The
current backend smoke test uses an exact captured message shape, not live inference.
