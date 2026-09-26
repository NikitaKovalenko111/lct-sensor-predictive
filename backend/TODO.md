# TODO

## Kafka idempotency

- The ML service does not need to make duplicate handling a product concern, but the
  Go consumers must remain idempotent because Kafka provides at-least-once delivery
  and can redeliver records. Once the Python service emits a stable `prediction_id`,
  use it as the primary prediction deduplication key while retaining a compatibility
  path for older messages without that field.

## Model operations

- Supply the trained `.joblib` artifacts outside Git and run a live end-to-end test
  through the shared Compose profile `model`.
- Decide later whether a fresh model consumer group should replay the complete
  historical topic or start from new events only.
- Define production monitoring and retry policy for failed Python inference.
