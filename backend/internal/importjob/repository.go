package importjob

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("import job not found")

type Job struct {
	ImportID      string     `json:"import_id"`
	ImportKind    string     `json:"import_kind"`
	FileName      string     `json:"file_name"`
	SourcePath    string     `json:"source_path,omitempty"`
	Status        string     `json:"status"`
	ProcessedRows int64      `json:"processed_rows"`
	FailedRows    int64      `json:"failed_rows"`
	ErrorMessage  string     `json:"error_message,omitempty"`
	StartedAt     *time.Time `json:"started_at,omitempty"`
	FinishedAt    *time.Time `json:"finished_at,omitempty"`
	CreatedAt     time.Time  `json:"created_at"`
	UpdatedAt     time.Time  `json:"updated_at"`
}

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) Start(ctx context.Context, kind, fileName, sourcePath string) (string, error) {
	var id string
	err := r.pool.QueryRow(ctx, `
		INSERT INTO import_jobs (import_kind, file_name, source_path, status, started_at)
		VALUES ($1, $2, $3, 'running', now())
		RETURNING import_id::text
	`, kind, fileName, sourcePath).Scan(&id)
	if err != nil {
		return "", fmt.Errorf("start import job: %w", err)
	}
	return id, nil
}

func (r *Repository) Progress(ctx context.Context, id string, processed, failed int64) error {
	_, err := r.pool.Exec(ctx, `
		UPDATE import_jobs
		SET processed_rows = $2, failed_rows = $3, updated_at = now()
		WHERE import_id = $1::uuid
	`, id, processed, failed)
	if err != nil {
		return fmt.Errorf("update import progress: %w", err)
	}
	return nil
}

func (r *Repository) Complete(ctx context.Context, id string, processed, failed int64) error {
	_, err := r.pool.Exec(ctx, `
		UPDATE import_jobs
		SET status = 'completed', processed_rows = $2, failed_rows = $3,
		    finished_at = now(), updated_at = now()
		WHERE import_id = $1::uuid
	`, id, processed, failed)
	if err != nil {
		return fmt.Errorf("complete import job: %w", err)
	}
	return nil
}

func (r *Repository) Fail(ctx context.Context, id string, processed, failed int64, cause error) error {
	_, err := r.pool.Exec(ctx, `
		UPDATE import_jobs
		SET status = 'failed', processed_rows = $2, failed_rows = $3,
		    error_message = $4, finished_at = now(), updated_at = now()
		WHERE import_id = $1::uuid
	`, id, processed, failed, cause.Error())
	if err != nil {
		return fmt.Errorf("fail import job: %w", err)
	}
	return nil
}

func (r *Repository) Get(ctx context.Context, id string) (Job, error) {
	row := r.pool.QueryRow(ctx, `
		SELECT import_id::text, import_kind, file_name, COALESCE(source_path, ''), status,
		       processed_rows, failed_rows, COALESCE(error_message, ''),
		       started_at, finished_at, created_at, updated_at
		FROM import_jobs WHERE import_id = $1::uuid
	`, id)
	job, err := scanJob(row)
	if errors.Is(err, pgx.ErrNoRows) {
		return Job{}, ErrNotFound
	}
	if err != nil {
		return Job{}, fmt.Errorf("get import job: %w", err)
	}
	return job, nil
}

func (r *Repository) List(ctx context.Context, limit, offset int) ([]Job, error) {
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	rows, err := r.pool.Query(ctx, `
		SELECT import_id::text, import_kind, file_name, COALESCE(source_path, ''), status,
		       processed_rows, failed_rows, COALESCE(error_message, ''),
		       started_at, finished_at, created_at, updated_at
		FROM import_jobs ORDER BY created_at DESC LIMIT $1 OFFSET $2
	`, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("list import jobs: %w", err)
	}
	defer rows.Close()

	result := make([]Job, 0)
	for rows.Next() {
		job, err := scanJob(rows)
		if err != nil {
			return nil, fmt.Errorf("scan import job: %w", err)
		}
		result = append(result, job)
	}
	return result, rows.Err()
}

type scanner interface {
	Scan(dest ...any) error
}

func scanJob(row scanner) (Job, error) {
	var job Job
	err := row.Scan(
		&job.ImportID, &job.ImportKind, &job.FileName, &job.SourcePath, &job.Status,
		&job.ProcessedRows, &job.FailedRows, &job.ErrorMessage,
		&job.StartedAt, &job.FinishedAt, &job.CreatedAt, &job.UpdatedAt,
	)
	return job, err
}
