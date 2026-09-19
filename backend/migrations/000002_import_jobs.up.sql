ALTER TABLE import_jobs
    ADD COLUMN import_kind TEXT NOT NULL DEFAULT 'events'
        CHECK (import_kind IN ('objects', 'channels', 'events')),
    ADD COLUMN source_path TEXT,
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX import_jobs_created_at_idx ON import_jobs (created_at DESC);
