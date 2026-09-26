package incidents

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const notificationChannel = "incident_events"

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) CreateFromPrediction(ctx context.Context, predictionID string) (*Incident, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("begin incident transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	row := tx.QueryRow(ctx, `
		INSERT INTO incidents (
			prediction_id, object_id, incident_type, risk_score, risk_level, title, description
		)
		SELECT prediction_id, object_id, prediction_type, risk_score, risk_level,
		       CASE prediction_type
		           WHEN 'fire_risk' THEN 'Высокий риск пожара'
		           WHEN 'equipment_failure' THEN 'Риск отказа оборудования'
		           WHEN 'nsd_event' THEN 'Возможное несанкционированное действие'
		           ELSE 'Высокий риск несанкционированного действия'
		       END,
		       'Инцидент автоматически создан по прогнозу модели'
		FROM predictions
		WHERE prediction_id = $1::uuid
		  AND (is_alert IS TRUE OR (is_alert IS NULL AND risk_level IN ('high', 'critical')))
		ON CONFLICT (prediction_id) DO NOTHING
		RETURNING incident_id::text, prediction_id::text, object_id, incident_type,
		          risk_score, risk_level, status, title, description,
		          COALESCE(assigned_to, ''), created_at, updated_at, resolved_at
	`, predictionID)
	incident, err := scanIncident(row)
	if errors.Is(err, pgx.ErrNoRows) {
		if err := tx.Commit(ctx); err != nil {
			return nil, fmt.Errorf("commit empty incident transaction: %w", err)
		}
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("create incident: %w", err)
	}
	if err := notify(ctx, tx, "incident.created", incident.IncidentID); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("commit incident transaction: %w", err)
	}
	return &incident, nil
}

func (r *Repository) List(ctx context.Context, filter ListFilter) ([]Incident, error) {
	if filter.Limit <= 0 || filter.Limit > 200 {
		filter.Limit = 50
	}
	rows, err := r.pool.Query(ctx, `
		SELECT incident_id::text, prediction_id::text, object_id, incident_type,
		       risk_score, risk_level, status, title, description,
		       COALESCE(assigned_to, ''), created_at, updated_at, resolved_at
		FROM incidents
		WHERE ($1::bigint = 0 OR object_id = $1)
		  AND ($2 = '' OR status = $2)
		  AND ($3 = '' OR risk_level = $3)
		ORDER BY created_at DESC
		LIMIT $4 OFFSET $5
	`, filter.ObjectID, filter.Status, filter.RiskLevel, filter.Limit, filter.Offset)
	if err != nil {
		return nil, fmt.Errorf("query incidents: %w", err)
	}
	defer rows.Close()

	result := make([]Incident, 0)
	for rows.Next() {
		item, err := scanIncident(rows)
		if err != nil {
			return nil, fmt.Errorf("scan incident: %w", err)
		}
		result = append(result, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate incidents: %w", err)
	}
	return result, nil
}

func (r *Repository) Get(ctx context.Context, id string) (Detail, error) {
	incident, err := scanIncident(r.pool.QueryRow(ctx, `
		SELECT incident_id::text, prediction_id::text, object_id, incident_type,
		       risk_score, risk_level, status, title, description,
		       COALESCE(assigned_to, ''), created_at, updated_at, resolved_at
		FROM incidents WHERE incident_id = $1::uuid
	`, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return Detail{}, ErrNotFound
	}
	if err != nil {
		return Detail{}, fmt.Errorf("get incident: %w", err)
	}
	detail := Detail{Incident: incident, Decisions: make([]Decision, 0)}

	rows, err := r.pool.Query(ctx, `
		SELECT decision_id::text, incident_id::text, decision, actor, comment, created_at
		FROM incident_decisions WHERE incident_id = $1::uuid ORDER BY created_at DESC
	`, id)
	if err != nil {
		return Detail{}, fmt.Errorf("query incident decisions: %w", err)
	}
	for rows.Next() {
		var decision Decision
		if err := rows.Scan(&decision.DecisionID, &decision.IncidentID, &decision.Decision,
			&decision.Actor, &decision.Comment, &decision.CreatedAt); err != nil {
			rows.Close()
			return Detail{}, fmt.Errorf("scan incident decision: %w", err)
		}
		detail.Decisions = append(detail.Decisions, decision)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return Detail{}, fmt.Errorf("iterate incident decisions: %w", err)
	}
	rows.Close()

	var order WorkOrderDraft
	err = r.pool.QueryRow(ctx, `
		SELECT work_order_id::text, incident_id::text, title, description, priority,
		       status, created_at, updated_at
		FROM work_order_drafts WHERE incident_id = $1::uuid
	`, id).Scan(&order.WorkOrderID, &order.IncidentID, &order.Title, &order.Description,
		&order.Priority, &order.Status, &order.CreatedAt, &order.UpdatedAt)
	if err == nil {
		detail.WorkOrder = &order
	} else if !errors.Is(err, pgx.ErrNoRows) {
		return Detail{}, fmt.Errorf("get work order draft: %w", err)
	}
	return detail, nil
}

func (r *Repository) Assign(ctx context.Context, id, assignee string) (Incident, error) {
	incident, err := scanIncident(r.pool.QueryRow(ctx, `
		UPDATE incidents
		SET assigned_to = $2,
		    status = CASE WHEN status = 'new' THEN 'in_review' ELSE status END,
		    updated_at = now()
		WHERE incident_id = $1::uuid AND status NOT IN ('resolved', 'dismissed')
		RETURNING incident_id::text, prediction_id::text, object_id, incident_type,
		          risk_score, risk_level, status, title, description,
		          COALESCE(assigned_to, ''), created_at, updated_at, resolved_at
	`, id, assignee))
	if errors.Is(err, pgx.ErrNoRows) {
		return Incident{}, ErrNotFound
	}
	if err != nil {
		return Incident{}, fmt.Errorf("assign incident: %w", err)
	}
	if err := r.publish(ctx, "incident.updated", id); err != nil {
		return Incident{}, err
	}
	return incident, nil
}

func (r *Repository) AddDecision(ctx context.Context, id, decision, actor, comment string) (Decision, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return Decision{}, fmt.Errorf("begin decision transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var result Decision
	err = tx.QueryRow(ctx, `
		INSERT INTO incident_decisions (incident_id, decision, actor, comment)
		SELECT incident_id, $2, $3, $4 FROM incidents
		WHERE incident_id = $1::uuid AND status NOT IN ('resolved', 'dismissed')
		RETURNING decision_id::text, incident_id::text, decision, actor, comment, created_at
	`, id, decision, actor, comment).Scan(&result.DecisionID, &result.IncidentID,
		&result.Decision, &result.Actor, &result.Comment, &result.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return Decision{}, ErrNotFound
	}
	if err != nil {
		return Decision{}, fmt.Errorf("create incident decision: %w", err)
	}
	_, err = tx.Exec(ctx, `
		UPDATE incidents
		SET status = CASE WHEN $2 = 'false_alarm' THEN 'dismissed' ELSE 'in_review' END,
		    resolved_at = CASE WHEN $2 = 'false_alarm' THEN now() ELSE NULL END,
		    updated_at = now()
		WHERE incident_id = $1::uuid
	`, id, decision)
	if err != nil {
		return Decision{}, fmt.Errorf("update incident after decision: %w", err)
	}
	if err := notify(ctx, tx, "incident.updated", id); err != nil {
		return Decision{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return Decision{}, fmt.Errorf("commit decision transaction: %w", err)
	}
	return result, nil
}

func (r *Repository) Resolve(ctx context.Context, id string) (Incident, error) {
	incident, err := scanIncident(r.pool.QueryRow(ctx, `
		UPDATE incidents SET status = 'resolved', resolved_at = now(), updated_at = now()
		WHERE incident_id = $1::uuid AND status NOT IN ('resolved', 'dismissed')
		RETURNING incident_id::text, prediction_id::text, object_id, incident_type,
		          risk_score, risk_level, status, title, description,
		          COALESCE(assigned_to, ''), created_at, updated_at, resolved_at
	`, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return Incident{}, ErrNotFound
	}
	if err != nil {
		return Incident{}, fmt.Errorf("resolve incident: %w", err)
	}
	if err := r.publish(ctx, "incident.updated", id); err != nil {
		return Incident{}, err
	}
	return incident, nil
}

func (r *Repository) CreateWorkOrder(ctx context.Context, id, title, description, priority string) (WorkOrderDraft, error) {
	var result WorkOrderDraft
	err := r.pool.QueryRow(ctx, `
		INSERT INTO work_order_drafts (incident_id, title, description, priority)
		SELECT incident_id, $2, $3, $4 FROM incidents WHERE incident_id = $1::uuid
		ON CONFLICT (incident_id) DO UPDATE SET
			title = EXCLUDED.title, description = EXCLUDED.description,
			priority = EXCLUDED.priority, updated_at = now()
		RETURNING work_order_id::text, incident_id::text, title, description,
		          priority, status, created_at, updated_at
	`, id, title, description, priority).Scan(&result.WorkOrderID, &result.IncidentID,
		&result.Title, &result.Description, &result.Priority, &result.Status,
		&result.CreatedAt, &result.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return WorkOrderDraft{}, ErrNotFound
	}
	if err != nil {
		return WorkOrderDraft{}, fmt.Errorf("create work order draft: %w", err)
	}
	return result, nil
}

func (r *Repository) Pool() *pgxpool.Pool {
	return r.pool
}

func (r *Repository) publish(ctx context.Context, event, id string) error {
	if _, err := r.pool.Exec(ctx, `SELECT pg_notify($1, json_build_object('event', $2::text, 'incident_id', $3::text)::text)`, notificationChannel, event, id); err != nil {
		return fmt.Errorf("publish incident notification: %w", err)
	}
	return nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanIncident(row rowScanner) (Incident, error) {
	var item Incident
	err := row.Scan(&item.IncidentID, &item.PredictionID, &item.ObjectID, &item.IncidentType,
		&item.RiskScore, &item.RiskLevel, &item.Status, &item.Title, &item.Description,
		&item.AssignedTo, &item.CreatedAt, &item.UpdatedAt, &item.ResolvedAt)
	return item, err
}

func notify(ctx context.Context, tx pgx.Tx, event, id string) error {
	if _, err := tx.Exec(ctx, `SELECT pg_notify($1, json_build_object('event', $2::text, 'incident_id', $3::text)::text)`, notificationChannel, event, id); err != nil {
		return fmt.Errorf("queue incident notification: %w", err)
	}
	return nil
}
