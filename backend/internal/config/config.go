package config

import (
	"fmt"
	"os"
	"strings"
	"time"
)

type Config struct {
	HTTPAddr               string
	DatabaseURL            string
	KafkaBrokers           []string
	SensorEventsTopic      string
	PredictionsTopic       string
	ConsumerGroup          string
	TelemetryConsumerGroup string
	ShutdownTimeout        time.Duration
}

func Load() (Config, error) {
	timeout, err := time.ParseDuration(env("SHUTDOWN_TIMEOUT", "10s"))
	if err != nil {
		return Config{}, fmt.Errorf("parse SHUTDOWN_TIMEOUT: %w", err)
	}

	return Config{
		HTTPAddr:               env("HTTP_ADDR", ":8080"),
		DatabaseURL:            env("DATABASE_URL", "postgres://app:app@localhost:5432/sensor_predictive?sslmode=disable"),
		KafkaBrokers:           splitCSV(env("KAFKA_BROKERS", "localhost:29092")),
		SensorEventsTopic:      env("KAFKA_SENSOR_EVENTS_TOPIC", "sensor.events.v1"),
		PredictionsTopic:       env("KAFKA_PREDICTIONS_TOPIC", "predictions.v1"),
		ConsumerGroup:          env("KAFKA_CONSUMER_GROUP", "backend.predictions.v1"),
		TelemetryConsumerGroup: env("KAFKA_TELEMETRY_CONSUMER_GROUP", "backend.telemetry.v1"),
		ShutdownTimeout:        timeout,
	}, nil
}

func env(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func splitCSV(value string) []string {
	parts := strings.Split(value, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		if value := strings.TrimSpace(part); value != "" {
			result = append(result, value)
		}
	}
	return result
}
