package incidents

import (
	"errors"
	"time"
)

var ErrNotFound = errors.New("incident not found")

const (
	StatusNew       = "new"
	StatusInReview  = "in_review"
	StatusResolved  = "resolved"
	StatusDismissed = "dismissed"

	DecisionConfirmed    = "confirmed"
	DecisionFalseAlarm   = "false_alarm"
	DecisionMonitor      = "monitor"
	DecisionDispatchCrew = "dispatch_crew"
)

type Incident struct {
	IncidentID   string     `json:"incident_id"`
	PredictionID string     `json:"prediction_id"`
	ObjectID     int64      `json:"object_id"`
	IncidentType string     `json:"incident_type"`
	RiskScore    float64    `json:"risk_score"`
	RiskLevel    string     `json:"risk_level"`
	Status       string     `json:"status"`
	Title        string     `json:"title"`
	Description  string     `json:"description"`
	AssignedTo   string     `json:"assigned_to,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
	UpdatedAt    time.Time  `json:"updated_at"`
	ResolvedAt   *time.Time `json:"resolved_at,omitempty"`
}

type Decision struct {
	DecisionID string    `json:"decision_id"`
	IncidentID string    `json:"incident_id"`
	Decision   string    `json:"decision"`
	Actor      string    `json:"actor"`
	Comment    string    `json:"comment"`
	CreatedAt  time.Time `json:"created_at"`
}

type WorkOrderDraft struct {
	WorkOrderID string    `json:"work_order_id"`
	IncidentID  string    `json:"incident_id"`
	Title       string    `json:"title"`
	Description string    `json:"description"`
	Priority    string    `json:"priority"`
	Status      string    `json:"status"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type Detail struct {
	Incident
	Decisions []Decision      `json:"decisions"`
	WorkOrder *WorkOrderDraft `json:"work_order,omitempty"`
}

type ListFilter struct {
	ObjectID  int64
	Status    string
	RiskLevel string
	Limit     int
	Offset    int
}

func ValidDecision(value string) bool {
	switch value {
	case DecisionConfirmed, DecisionFalseAlarm, DecisionMonitor, DecisionDispatchCrew:
		return true
	default:
		return false
	}
}
