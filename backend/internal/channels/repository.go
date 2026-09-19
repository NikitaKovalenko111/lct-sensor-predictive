package channels

import (
	"context"
	"fmt"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	pool    *pgxpool.Pool
	objects *objects.Repository
}

func NewRepository(pool *pgxpool.Pool, objectRepository *objects.Repository) *Repository {
	return &Repository{pool: pool, objects: objectRepository}
}

func (r *Repository) UpsertBatch(ctx context.Context, items []Channel) error {
	if len(items) == 0 {
		return nil
	}
	seenObjects := make(map[int64]struct{})
	for _, item := range items {
		if err := item.Validate(); err != nil {
			return err
		}
		if _, exists := seenObjects[item.ObjectID]; !exists {
			if err := r.objects.EnsurePlaceholder(ctx, item.ObjectID); err != nil {
				return err
			}
			seenObjects[item.ObjectID] = struct{}{}
		}
	}

	batch := &pgx.Batch{}
	for _, item := range items {
		batch.Queue(`
			INSERT INTO sensor_channels (
				channel_id, object_id, sensor_type, engineering_system,
				engineering_system_tag, sensor_name
			) VALUES ($1, $2, $3, $4, $5, $6)
			ON CONFLICT (channel_id) DO UPDATE SET
				object_id = EXCLUDED.object_id,
				sensor_type = EXCLUDED.sensor_type,
				engineering_system = EXCLUDED.engineering_system,
				engineering_system_tag = EXCLUDED.engineering_system_tag,
				sensor_name = EXCLUDED.sensor_name,
				updated_at = now()
		`, item.ChannelID, item.ObjectID, item.SensorType, item.EngineeringSystem,
			item.EngineeringSystemTag, item.SensorName)
	}
	results := r.pool.SendBatch(ctx, batch)
	for range items {
		if _, err := results.Exec(); err != nil {
			_ = results.Close()
			return fmt.Errorf("upsert channel batch: %w", err)
		}
	}
	return results.Close()
}

func (r *Repository) EventLookup(ctx context.Context) (map[string]EventMetadata, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT channel_id, object_id, sensor_type, COALESCE(engineering_system, '')
		FROM sensor_channels
	`)
	if err != nil {
		return nil, fmt.Errorf("query channel lookup: %w", err)
	}
	defer rows.Close()

	result := make(map[string]EventMetadata)
	for rows.Next() {
		var channelID string
		var metadata EventMetadata
		if err := rows.Scan(&channelID, &metadata.ObjectID, &metadata.SensorType, &metadata.EngineeringSystem); err != nil {
			return nil, fmt.Errorf("scan channel lookup: %w", err)
		}
		result[channelID] = metadata
	}
	return result, rows.Err()
}

func (r *Repository) ListByObject(ctx context.Context, objectID int64, limit, offset int) ([]Channel, error) {
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	rows, err := r.pool.Query(ctx, `
		SELECT channel_id, object_id, sensor_type, COALESCE(engineering_system, ''),
		       COALESCE(engineering_system_tag, ''), COALESCE(sensor_name, '')
		FROM sensor_channels
		WHERE ($1::bigint = 0 OR object_id = $1)
		ORDER BY channel_id
		LIMIT $2 OFFSET $3
	`, objectID, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("list channels: %w", err)
	}
	defer rows.Close()

	result := make([]Channel, 0)
	for rows.Next() {
		var item Channel
		if err := rows.Scan(
			&item.ChannelID, &item.ObjectID, &item.SensorType, &item.EngineeringSystem,
			&item.EngineeringSystemTag, &item.SensorName,
		); err != nil {
			return nil, fmt.Errorf("scan channel: %w", err)
		}
		result = append(result, item)
	}
	return result, rows.Err()
}
