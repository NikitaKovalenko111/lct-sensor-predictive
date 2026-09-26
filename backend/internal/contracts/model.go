package contracts

import (
	"encoding/json"
	"fmt"
	"time"
)

const SchemaVersion = 1

const (
	PredictionTypeFireRisk  = "fire_risk"
	PredictionTypeNSDEvent  = "nsd_event"
	PredictionTypeNSDRisk   = "nsd_risk"
	PredictionTypeEquipment = "equipment_failure"
)

type SensorEvent struct {
	SchemaVersion     int       `json:"schema_version"`
	EventID           string    `json:"event_id"`
	ObjectID          int64     `json:"object_id"`
	ChannelID         string    `json:"channel_id"`
	SensorType        string    `json:"sensor_type"`
	EngineeringSystem string    `json:"engineering_system"`
	Value             string    `json:"value"`
	IsAlarm           bool      `json:"is_alarm"`
	Timestamp         time.Time `json:"timestamp"`
}

func (e SensorEvent) Validate() error {
	if e.EventID == "" {
		return fmt.Errorf("event_id is required")
	}
	if e.ObjectID <= 0 {
		return fmt.Errorf("object_id must be positive")
	}
	if e.ChannelID == "" {
		return fmt.Errorf("channel_id is required")
	}
	if e.SensorType == "" {
		return fmt.Errorf("sensor_type is required")
	}
	if e.Timestamp.IsZero() {
		return fmt.Errorf("timestamp is required")
	}
	return nil
}

type Prediction struct {
	SchemaVersion  int             `json:"schema_version"`
	PredictionID   string          `json:"prediction_id,omitempty"`
	ObjectID       int64           `json:"object_id"`
	PredictionType string          `json:"prediction_type"`
	RiskScore      float64         `json:"risk_score"`
	RiskLevel      string          `json:"risk_level"`
	IsAlert        *bool           `json:"is_alert,omitempty"`
	PredictedAt    time.Time       `json:"predicted_at"`
	FeaturesUsed   json.RawMessage `json:"features_used"`
	ModelVersion   string          `json:"model_version"`
}

// UnmarshalJSON accepts both RFC 3339 and the naive UTC timestamp emitted by the
// current Python model through json.dumps(default=str).
func (p *Prediction) UnmarshalJSON(data []byte) error {
	type predictionAlias Prediction
	var wire struct {
		predictionAlias
		PredictedAt string `json:"predicted_at"`
	}
	if err := json.Unmarshal(data, &wire); err != nil {
		return err
	}
	predictedAt, err := parseModelTime(wire.PredictedAt)
	if err != nil {
		return fmt.Errorf("parse predicted_at: %w", err)
	}
	*p = Prediction(wire.predictionAlias)
	p.PredictedAt = predictedAt
	return nil
}

func parseModelTime(value string) (time.Time, error) {
	for _, layout := range []string{
		time.RFC3339Nano,
		"2006-01-02 15:04:05.999999999",
		"2006-01-02 15:04:05",
	} {
		if parsed, err := time.ParseInLocation(layout, value, time.UTC); err == nil {
			return parsed.UTC(), nil
		}
	}
	return time.Time{}, fmt.Errorf("unsupported timestamp %q", value)
}

func (p Prediction) Validate() error {
	if p.ObjectID <= 0 {
		return fmt.Errorf("object_id must be positive")
	}
	if p.PredictionType == "" {
		return fmt.Errorf("prediction_type is required")
	}
	switch p.PredictionType {
	case PredictionTypeFireRisk, PredictionTypeNSDEvent, PredictionTypeNSDRisk, PredictionTypeEquipment:
	default:
		return fmt.Errorf("invalid prediction_type %q", p.PredictionType)
	}
	if p.RiskScore < 0 || p.RiskScore > 1 {
		return fmt.Errorf("risk_score must be between 0 and 1")
	}
	switch p.RiskLevel {
	case "low", "medium", "high", "critical":
	default:
		return fmt.Errorf("invalid risk_level %q", p.RiskLevel)
	}
	if p.PredictedAt.IsZero() {
		return fmt.Errorf("predicted_at is required")
	}
	if p.ModelVersion == "" {
		return fmt.Errorf("model_version is required")
	}
	return nil
}

type ObjectFeatures struct {
	SchemaVersion int       `json:"schema_version"`
	ObjectID      int64     `json:"object_id"`
	Timestamp     time.Time `json:"timestamp"`

	Alarms1h  int     `json:"alarms_1h"`
	Alarms3h  int     `json:"alarms_3h"`
	Alarms6h  int     `json:"alarms_6h"`
	Alarms24h int     `json:"alarms_24h"`
	TempMax6h float64 `json:"temp_max_6h"`
	Motion24h int     `json:"motion_24h"`

	DoorOpenings24h    int `json:"door_openings_24h"`
	MotionBefore30m    int `json:"motion_before_30min"`
	NSDPrevious7d      int `json:"nsd_prev_7d"`
	FailuresPrevious7d int `json:"failures_prev_7d"`
}
