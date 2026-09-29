package main

import (
	"testing"
	"time"
)

func TestSimulatedEventsCoversEveryObject(t *testing.T) {
	registry := map[int64][]simulationChannel{
		20: {{channelID: "temperature-20", sensorType: "Датчик температуры"}},
		21: {{channelID: "motion-21", sensorType: "Датчик движения"}},
	}
	timestamp := time.Date(2026, 9, 26, 12, 0, 0, 0, time.UTC)

	events, _ := simulatedEvents(registry, timestamp)
	if len(events) != len(registry) {
		t.Fatalf("got %d events, want %d", len(events), len(registry))
	}
	seen := make(map[int64]bool)
	for _, event := range events {
		seen[event.ObjectID] = true
		if !event.Timestamp.Equal(timestamp) {
			t.Fatalf("unexpected timestamp %s", event.Timestamp)
		}
	}
	for objectID := range registry {
		if !seen[objectID] {
			t.Fatalf("object %d has no event", objectID)
		}
	}
}

func TestSimulatedEventsCanRunWithoutAlarms(t *testing.T) {
	registry := map[int64][]simulationChannel{
		20: {{channelID: "temperature-20", sensorType: "temperature"}},
		21: {{channelID: "motion-21", sensorType: "motion"}},
	}

	events, alarms := simulatedEvents(registry, time.Now(), 0)
	if alarms != 0 {
		t.Fatalf("got %d alarms, want 0", alarms)
	}
	for _, event := range events {
		if event.IsAlarm {
			t.Fatalf("unexpected alarm for object %d", event.ObjectID)
		}
	}
}

func TestNextSimulationBatchCoversRegistryRoundRobin(t *testing.T) {
	registry := map[int64][]simulationChannel{
		10: {{channelID: "10"}},
		20: {{channelID: "20"}},
		30: {{channelID: "30"}},
		40: {{channelID: "40"}},
	}
	cursor := 0
	seen := make(map[int64]bool)
	for range 2 {
		for objectID := range nextSimulationBatch(registry, 2, &cursor) {
			seen[objectID] = true
		}
	}
	if len(seen) != len(registry) {
		t.Fatalf("covered %d objects, want %d", len(seen), len(registry))
	}
}

func TestSimulatedValueMatchesModelVocabulary(t *testing.T) {
	if value := simulatedValue("КД Дверь", true); value != "Не замкнут" {
		t.Fatalf("unexpected door alarm value %q", value)
	}
	if value := simulatedValue("Датчик движения", true); value != "Обнаружено движение" {
		t.Fatalf("unexpected motion alarm value %q", value)
	}
	if value := simulatedValue("Состояние насоса", true); value != "Неисправен" {
		t.Fatalf("unexpected failure value %q", value)
	}
}
