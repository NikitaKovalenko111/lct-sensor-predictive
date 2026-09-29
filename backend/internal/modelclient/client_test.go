package modelclient

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPredict(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/predict" {
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
		var request PredictionRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if request.ObjectID != 1001 || len(request.PredictionTypes) != 1 || request.PredictionTypes[0] != "fire_risk" {
			t.Fatalf("unexpected request body: %+v", request)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"predictions":[{"schema_version":1,"prediction_id":"42e662ce-fdac-4892-a75e-cc7fe195db1b","object_id":1001,"prediction_type":"fire_risk","risk_score":0.72,"risk_level":"high","is_alert":true,"predicted_at":"2026-09-23T12:00:00Z","features_used":{"alarms_1h":2},"model_version":"v1.0"}]}`))
	}))
	defer server.Close()

	client, err := New(server.URL, time.Second)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	response, err := client.Predict(context.Background(), PredictionRequest{
		ObjectID: 1001, PredictionTypes: []string{"fire_risk"},
	})
	if err != nil {
		t.Fatalf("Predict: %v", err)
	}
	if len(response.Predictions) != 1 || response.Predictions[0].SchemaVersion != 1 {
		t.Fatalf("unexpected response: %+v", response)
	}
}

func TestPredictionRequestRejectsDuplicateTypes(t *testing.T) {
	request := PredictionRequest{
		ObjectID:        1001,
		PredictionTypes: []string{"fire_risk", "fire_risk"},
	}
	if err := request.Validate(); err == nil {
		t.Fatal("expected duplicate prediction type error")
	}
}

func TestPredictRejectsAnotherObject(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"predictions":[{"object_id":2002,"prediction_type":"nsd_risk","risk_score":0.2,"risk_level":"low","is_alert":false,"predicted_at":"2026-09-23 12:00:00","features_used":{},"model_version":"v1.0"}]}`))
	}))
	defer server.Close()

	client, err := New(server.URL, time.Second)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	if _, err := client.Predict(context.Background(), PredictionRequest{ObjectID: 1001}); err == nil {
		t.Fatal("expected object mismatch error")
	}
}
