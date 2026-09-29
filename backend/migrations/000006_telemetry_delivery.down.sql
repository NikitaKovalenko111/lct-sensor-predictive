DROP INDEX IF EXISTS idx_sensor_events_unpublished;
ALTER TABLE sensor_events DROP COLUMN IF EXISTS kafka_published_at;
