ALTER TABLE sensor_events
    ADD COLUMN kafka_published_at TIMESTAMPTZ;

CREATE INDEX idx_sensor_events_unpublished
    ON sensor_events (occurred_at)
    WHERE kafka_published_at IS NULL;
