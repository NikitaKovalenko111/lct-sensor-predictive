package contracts

import (
	"encoding/json"
	"testing"
	"time"
)

func TestSensorEventMatchesPythonContract(t *testing.T) {
	payload := []byte(`{
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
