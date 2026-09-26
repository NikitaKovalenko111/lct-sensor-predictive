package objects

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("object not found")

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) UpsertBatch(ctx context.Context, items []Object) error {
	if len(items) == 0 {
		return nil
	}
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin object batch: %w", err)
	}
	defer tx.Rollback(ctx)

	batch := &pgx.Batch{}
	for _, item := range items {
		if err := item.Validate(); err != nil {
			return err
		}
		if len(item.Geometry) == 0 {
			item.Geometry = SyntheticGeometry(item.ObjectID)
		}
		batch.Queue(`
			INSERT INTO objects (
				object_id, parent_id, hierarchy_level, object_type, dispatcher_name, geometry
			) VALUES ($1, NULL, $2, $3, $4, $5)
			ON CONFLICT (object_id) DO UPDATE SET
				hierarchy_level = EXCLUDED.hierarchy_level,
				object_type = EXCLUDED.object_type,
				dispatcher_name = EXCLUDED.dispatcher_name,
				geometry = EXCLUDED.geometry,
				updated_at = now()
		`, item.ObjectID, item.HierarchyLevel, item.ObjectType, item.DispatcherName, item.Geometry)
	}
	results := tx.SendBatch(ctx, batch)
	for range items {
		if _, err := results.Exec(); err != nil {
			_ = results.Close()
			return fmt.Errorf("upsert object batch: %w", err)
		}
	}
	if err := results.Close(); err != nil {
		return fmt.Errorf("close object batch: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit object batch: %w", err)
	}
	return nil
}

func (r *Repository) SetParents(ctx context.Context, items []Object) error {
	batch := &pgx.Batch{}
	count := 0
	for _, item := range items {
		if item.ParentID == nil || *item.ParentID <= 0 || *item.ParentID == item.ObjectID {
			continue
		}
		batch.Queue(`
			UPDATE objects child
			SET parent_id = parent.object_id, updated_at = now()
			FROM objects parent
			WHERE child.object_id = $1 AND parent.object_id = $2
		`, item.ObjectID, *item.ParentID)
		count++
	}
	if count == 0 {
		return nil
	}
	results := r.pool.SendBatch(ctx, batch)
	for range count {
		if _, err := results.Exec(); err != nil {
			_ = results.Close()
			return fmt.Errorf("set object parent: %w", err)
		}
	}
	return results.Close()
}

func (r *Repository) EnsurePlaceholder(ctx context.Context, objectID int64) error {
	_, err := r.pool.Exec(ctx, `
		INSERT INTO objects (object_id, object_type, dispatcher_name, geometry)
		VALUES ($1, 'unknown', $2, $3)
		ON CONFLICT (object_id) DO NOTHING
	`, objectID, fmt.Sprintf("Object %d", objectID), SyntheticGeometry(objectID))
	if err != nil {
		return fmt.Errorf("ensure placeholder object: %w", err)
	}
	return nil
}

func (r *Repository) Get(ctx context.Context, objectID int64) (Object, error) {
	var item Object
	var geometry []byte
	err := r.pool.QueryRow(ctx, `
		SELECT object_id, parent_id, COALESCE(hierarchy_level, 0),
		       COALESCE(object_type, ''), dispatcher_name, COALESCE(geometry, '{}'::jsonb)
		FROM objects WHERE object_id = $1
	`, objectID).Scan(
		&item.ObjectID, &item.ParentID, &item.HierarchyLevel,
		&item.ObjectType, &item.DispatcherName, &geometry,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return Object{}, ErrNotFound
	}
	if err != nil {
		return Object{}, fmt.Errorf("get object: %w", err)
	}
	item.Geometry = json.RawMessage(geometry)
	return item, nil
}

func (r *Repository) List(ctx context.Context, filter ListFilter) ([]Object, error) {
	if filter.Limit <= 0 || filter.Limit > 500 {
		filter.Limit = 100
	}
	rows, err := r.pool.Query(ctx, `
		SELECT object_id, parent_id, COALESCE(hierarchy_level, 0),
		       COALESCE(object_type, ''), dispatcher_name, COALESCE(geometry, '{}'::jsonb)
		FROM objects
		WHERE ($1::bigint = 0 OR parent_id = $1)
		  AND ($2 = '' OR object_type = $2)
		  AND ($3 = '' OR dispatcher_name ILIKE '%' || $3 || '%')
		ORDER BY object_id
		LIMIT $4 OFFSET $5
	`, filter.ParentID, filter.ObjectType, filter.Search, filter.Limit, filter.Offset)
	if err != nil {
		return nil, fmt.Errorf("list objects: %w", err)
	}
	defer rows.Close()

	result := make([]Object, 0)
	for rows.Next() {
		var item Object
		var geometry []byte
		if err := rows.Scan(
			&item.ObjectID, &item.ParentID, &item.HierarchyLevel,
			&item.ObjectType, &item.DispatcherName, &geometry,
		); err != nil {
			return nil, fmt.Errorf("scan object: %w", err)
		}
		item.Geometry = json.RawMessage(geometry)
		result = append(result, item)
	}
	return result, rows.Err()
}
