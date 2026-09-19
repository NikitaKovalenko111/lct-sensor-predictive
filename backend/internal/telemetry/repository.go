package telemetry

import (
	"context"
	"fmt"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	pool *pgxpool.Pool
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
			value, is_alarm, occurred_at, schema_version
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		ON CONFLICT (event_id) DO NOTHING
	`, event.EventID, event.ObjectID, event.ChannelID, event.SensorType,
		event.EngineeringSystem, event.Value, event.IsAlarm, event.Timestamp, event.SchemaVersion)
	if err != nil {
		return fmt.Errorf("upsert sensor event: %w", err)
	}
	return nil
}
