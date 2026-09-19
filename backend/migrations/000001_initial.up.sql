CREATE TABLE objects (
    object_id BIGINT PRIMARY KEY,
    parent_id BIGINT REFERENCES objects(object_id),
    hierarchy_level INTEGER,
    object_type TEXT,
    dispatcher_name TEXT NOT NULL,
    geometry JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sensor_channels (
    channel_id TEXT PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES objects(object_id),
    sensor_type TEXT NOT NULL,
    engineering_system TEXT,
    engineering_system_tag TEXT,
    sensor_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sensor_events (
    event_id TEXT PRIMARY KEY,
    object_id BIGINT NOT NULL,
    channel_id TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    engineering_system TEXT,
    value TEXT NOT NULL,
    is_alarm BOOLEAN NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX sensor_events_object_time_idx ON sensor_events (object_id, occurred_at DESC);
CREATE INDEX sensor_events_channel_time_idx ON sensor_events (channel_id, occurred_at DESC);

CREATE TABLE predictions (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_id BIGINT NOT NULL,
    prediction_type TEXT NOT NULL CHECK (
        prediction_type IN ('fire_risk', 'nsd_event', 'nsd_risk', 'equipment_failure')
    ),
    risk_score DOUBLE PRECISION NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    predicted_at TIMESTAMPTZ NOT NULL,
    features_used JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (object_id, prediction_type, predicted_at, model_version)
);

CREATE INDEX predictions_object_time_idx ON predictions (object_id, predicted_at DESC);
CREATE INDEX predictions_risk_idx ON predictions (risk_level, predicted_at DESC);

CREATE TABLE import_jobs (
    import_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    processed_rows BIGINT NOT NULL DEFAULT 0,
    failed_rows BIGINT NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

