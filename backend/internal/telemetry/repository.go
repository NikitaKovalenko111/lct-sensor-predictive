package telemetry

import (
	"context"
	"fmt"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	pool *pgxpool.Pool
}

type ListFilter struct {
	ObjectID  int64
	ChannelID string
	AlarmOnly bool
	Limit     int
	Offset    int
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) Upsert(ctx context.Context, event contracts.SensorEvent) error {
	if err := event.Validate(); err != nil {
		return err
	}
	_, err := r.pool.Exec(ctx, `
		INSERT INTO sensor_events (
			event_id, object_id, channel_id, sensor_type, engineering_system,
			value, is_alarm, occurred_at, schema_version, kafka_published_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
		ON CONFLICT (event_id) DO UPDATE SET kafka_published_at = COALESCE(sensor_events.kafka_published_at, now())
	`, event.EventID, event.ObjectID, event.ChannelID, event.SensorType,
		event.EngineeringSystem, event.Value, event.IsAlarm, event.Timestamp, event.SchemaVersion)
	if err != nil {
		return fmt.Errorf("upsert sensor event: %w", err)
	}
	return nil
}

func (r *Repository) UpsertBatch(ctx context.Context, events []contracts.SensorEvent) ([]contracts.SensorEvent, error) {
	if len(events) == 0 {
		return nil, nil
	}
	batch := &pgx.Batch{}
	for _, event := range events {
		if err := event.Validate(); err != nil {
			return nil, err
		}
		batch.Queue(`
			INSERT INTO sensor_events (
				event_id, object_id, channel_id, sensor_type, engineering_system,
				value, is_alarm, occurred_at, schema_version
			) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
			ON CONFLICT (event_id) DO UPDATE SET event_id = EXCLUDED.event_id
			WHERE sensor_events.kafka_published_at IS NULL
		`, event.EventID, event.ObjectID, event.ChannelID, event.SensorType,
			event.EngineeringSystem, event.Value, event.IsAlarm, event.Timestamp, event.SchemaVersion)
	}
	results := r.pool.SendBatch(ctx, batch)
	inserted := make([]contracts.SensorEvent, 0, len(events))
	for index := range events {
		tag, err := results.Exec()
		if err != nil {
			_ = results.Close()
			return nil, fmt.Errorf("upsert sensor event batch: %w", err)
		}
		if tag.RowsAffected() > 0 {
			inserted = append(inserted, events[index])
		}
	}
	if err := results.Close(); err != nil {
		return nil, fmt.Errorf("close sensor event batch: %w", err)
	}
	return inserted, nil
}

func (r *Repository) MarkPublishedBatch(ctx context.Context, events []contracts.SensorEvent) error {
	if len(events) == 0 {
		return nil
	}
	ids := make([]string, 0, len(events))
	for _, event := range events {
		ids = append(ids, event.EventID)
	}
	if _, err := r.pool.Exec(ctx, `
		UPDATE sensor_events SET kafka_published_at = now()
		WHERE event_id = ANY($1::uuid[])
	`, ids); err != nil {
		return fmt.Errorf("mark sensor events published: %w", err)
	}
	return nil
}

func (r *Repository) List(ctx context.Context, filter ListFilter) ([]contracts.SensorEvent, error) {
	if filter.Limit <= 0 || filter.Limit > 500 {
		filter.Limit = 100
	}
	rows, err := r.pool.Query(ctx, `
		SELECT schema_version, event_id, object_id, channel_id, sensor_type,
		       COALESCE(engineering_system, ''), value, is_alarm, occurred_at
		FROM sensor_events
		WHERE ($1::bigint = 0 OR object_id = $1)
		  AND ($2 = '' OR channel_id = $2)
		  AND ($3::boolean = false OR is_alarm = true)
		ORDER BY occurred_at DESC
		LIMIT $4 OFFSET $5
	`, filter.ObjectID, filter.ChannelID, filter.AlarmOnly, filter.Limit, filter.Offset)
	if err != nil {
		return nil, fmt.Errorf("list sensor events: %w", err)
	}
	defer rows.Close()

	result := make([]contracts.SensorEvent, 0)
	for rows.Next() {
		var event contracts.SensorEvent
		if err := rows.Scan(
			&event.SchemaVersion, &event.EventID, &event.ObjectID, &event.ChannelID,
			&event.SensorType, &event.EngineeringSystem, &event.Value, &event.IsAlarm,
			&event.Timestamp,
		); err != nil {
			return nil, fmt.Errorf("scan sensor event: %w", err)
		}
		result = append(result, event)
	}
	return result, rows.Err()
}
