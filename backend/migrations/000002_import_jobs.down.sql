DROP INDEX IF EXISTS import_jobs_created_at_idx;

ALTER TABLE import_jobs
    DROP COLUMN IF EXISTS updated_at,
    DROP COLUMN IF EXISTS source_path,
    DROP COLUMN IF EXISTS import_kind;
