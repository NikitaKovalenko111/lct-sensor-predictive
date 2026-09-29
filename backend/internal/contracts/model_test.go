package contracts

import (
	"encoding/json"
	"testing"
	"time"
)

func TestSensorEventMatchesPythonContract(t *testing.T) {
	payload := []byte(`{
		"schema_version":1,
		"event_id":"evt-1",
		"object_id":42,
		"channel_id":"temperature-1",
		"sensor_type":"temperature",
		"engineering_system":"fire_safety",
		"value":"37.5",
		"is_alarm":true,
		"timestamp":"2026-09-19T12:00:00Z"
	}`)
	var event SensorEvent
	if err := json.Unmarshal(payload, &event); err != nil {
		t.Fatalf("decode SensorEvent: %v", err)
	}
	if err := event.Validate(); err != nil {
		t.Fatalf("validate SensorEvent: %v", err)
	}
}

func TestPredictionValidation(t *testing.T) {
	prediction := Prediction{
		SchemaVersion:  SchemaVersion,
		ObjectID:       42,
		PredictionType: PredictionTypeFireRisk,
		RiskScore:      0.75,
		RiskLevel:      "high",
		PredictedAt:    time.Now().UTC(),
		FeaturesUsed:   json.RawMessage(`{"alarms_1h":3}`),
		ModelVersion:   "v1.0",
	}
	if err := prediction.Validate(); err != nil {
		t.Fatalf("validate Prediction: %v", err)
	}

	prediction.RiskScore = 1.1
	if err := prediction.Validate(); err == nil {
		t.Fatal("expected out-of-range risk score to fail")
	}
}

func TestPredictionMatchesCurrentPythonServiceContract(t *testing.T) {
	payload := []byte(`{
		"schema_version":1,
		"object_id":9999,
		"prediction_type":"nsd_event",
		"risk_score":0.42,
		"risk_level":"medium",
		"is_alert":true,
		"predicted_at":"2026-09-23 12:34:56.123456",
		"features_used":{"motion_before_30min":4},
		"model_version":"v1.0"
	}`)
	var prediction Prediction
	if err := json.Unmarshal(payload, &prediction); err != nil {
		t.Fatalf("decode Python Prediction: %v", err)
	}
	if err := prediction.Validate(); err != nil {
		t.Fatalf("validate Python Prediction: %v", err)
	}
	if prediction.SchemaVersion != SchemaVersion {
		t.Fatalf("unexpected schema version: got %d", prediction.SchemaVersion)
	}
	if prediction.IsAlert == nil || !*prediction.IsAlert {
		t.Fatal("expected is_alert=true")
	}
	want := time.Date(2026, time.September, 23, 12, 34, 56, 123456000, time.UTC)
	if !prediction.PredictedAt.Equal(want) {
		t.Fatalf("unexpected predicted_at: got %s, want %s", prediction.PredictedAt, want)
	}
}

func TestPredictionAcceptsRFC3339Timestamp(t *testing.T) {
	payload := []byte(`{
		"schema_version":1,
		"object_id":42,
		"prediction_type":"fire_risk",
		"risk_score":0.8,
		"risk_level":"critical",
		"predicted_at":"2026-09-23T12:34:56.123456Z",
		"features_used":{},
		"model_version":"v1.0"
	}`)
	var prediction Prediction
	if err := json.Unmarshal(payload, &prediction); err != nil {
		t.Fatalf("decode RFC3339 Prediction: %v", err)
	}
	if prediction.IsAlert != nil {
		t.Fatal("expected omitted is_alert to remain nil")
	}
}

func TestPredictionRejectsUnsupportedSchemaVersion(t *testing.T) {
	prediction := Prediction{
		SchemaVersion:  SchemaVersion + 1,
		ObjectID:       42,
		PredictionType: PredictionTypeFireRisk,
		RiskScore:      0.5,
		RiskLevel:      "medium",
		PredictedAt:    time.Now().UTC(),
		FeaturesUsed:   json.RawMessage(`{}`),
		ModelVersion:   "v1.0",
	}
	if err := prediction.Validate(); err == nil {
		t.Fatal("expected unsupported schema version to fail")
	}
}

func TestPredictionRejectsUnsupportedTimestamp(t *testing.T) {
	payload := []byte(`{"predicted_at":"23.09.2026 12:34"}`)
	var prediction Prediction
	if err := json.Unmarshal(payload, &prediction); err == nil {
		t.Fatal("expected unsupported timestamp to fail")
	}
}
