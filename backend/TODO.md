# TODO

## Kafka idempotency

- The ML service does not need to make duplicate handling a product concern, but the
  Go consumers must remain idempotent because Kafka provides at-least-once delivery
  and can redeliver records. Once the Python service emits a stable `prediction_id`,
  use it as the primary prediction deduplication key while retaining a compatibility
  path for older messages without that field.

## Model integration

- Implement `POST /predict` in the Python service using the contract documented in
  `docs/model-integration.md`. The endpoint must return the calculated predictions and
  publish the same predictions to `predictions.v1` for persistence and incident
  processing.
- Add the Python service and its model artifacts to the shared Compose file after the
  model branch is merged.
- Decide later whether a fresh model consumer group should replay the complete
  historical topic or start from new events only.
- Define Python-service health/error behavior and the equipment-failure model contract.
