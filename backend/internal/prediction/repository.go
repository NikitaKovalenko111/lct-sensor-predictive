package prediction

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) Upsert(ctx context.Context, prediction contracts.Prediction) (string, error) {
	if err := prediction.Validate(); err != nil {
		return "", err
	}
	var predictionID string
	err := r.pool.QueryRow(ctx, `
		INSERT INTO predictions (
			prediction_id, object_id, prediction_type, risk_score, risk_level,
			predicted_at, features_used, model_version, schema_version
		) VALUES (
			COALESCE(NULLIF($1, '')::uuid, gen_random_uuid()), $2, $3, $4, $5,
			$6, $7, $8, $9
		)
		ON CONFLICT (object_id, prediction_type, predicted_at, model_version) DO UPDATE SET
			risk_score = EXCLUDED.risk_score,
			risk_level = EXCLUDED.risk_level,
			features_used = EXCLUDED.features_used,
			updated_at = now()
		RETURNING prediction_id::text
	`, prediction.PredictionID, prediction.ObjectID, prediction.PredictionType,
		prediction.RiskScore, prediction.RiskLevel, prediction.PredictedAt,
		prediction.FeaturesUsed, prediction.ModelVersion, prediction.SchemaVersion).Scan(&predictionID)
	if err != nil {
		return "", fmt.Errorf("upsert prediction: %w", err)
	}
	return predictionID, nil
}

type ListFilter struct {
	ObjectID       int64
	PredictionType string
	RiskLevel      string
	Limit          int
	Offset         int
}

type StoredPrediction struct {
	PredictionID   string          `json:"prediction_id"`
	ObjectID       int64           `json:"object_id"`
	PredictionType string          `json:"prediction_type"`
	RiskScore      float64         `json:"risk_score"`
	RiskLevel      string          `json:"risk_level"`
	PredictedAt    time.Time       `json:"predicted_at"`
	FeaturesUsed   json.RawMessage `json:"features_used"`
	ModelVersion   string          `json:"model_version"`
}

func (r *Repository) List(ctx context.Context, filter ListFilter) ([]StoredPrediction, error) {
	if filter.Limit <= 0 || filter.Limit > 200 {
		filter.Limit = 50
	}
	rows, err := r.pool.Query(ctx, `
		SELECT prediction_id::text, object_id, prediction_type, risk_score, risk_level,
		       predicted_at, features_used, model_version
		FROM predictions
		WHERE ($1::bigint = 0 OR object_id = $1)
		  AND ($2 = '' OR prediction_type = $2)
		  AND ($3 = '' OR risk_level = $3)
		ORDER BY predicted_at DESC
		LIMIT $4 OFFSET $5
	`, filter.ObjectID, filter.PredictionType, filter.RiskLevel, filter.Limit, filter.Offset)
	if err != nil {
		return nil, fmt.Errorf("query predictions: %w", err)
	}
	defer rows.Close()

	result := make([]StoredPrediction, 0)
	for rows.Next() {
		var item StoredPrediction
		if err := rows.Scan(
			&item.PredictionID, &item.ObjectID, &item.PredictionType,
			&item.RiskScore, &item.RiskLevel, &item.PredictedAt,
			&item.FeaturesUsed, &item.ModelVersion,
		); err != nil {
			return nil, fmt.Errorf("scan prediction: %w", err)
		}
		result = append(result, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate predictions: %w", err)
	}
	return result, nil
}
