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
	SensorEventsDLQTopic   string
	PredictionsDLQTopic    string
	ConsumerGroup          string
	TelemetryConsumerGroup string
	ShutdownTimeout        time.Duration
	JWTSecret              string
	JWTIssuer              string
	JWTAccessTTL           time.Duration
	BootstrapAdminUsername string
	BootstrapAdminPassword string
	CORSAllowedOrigins     []string
	ModelServiceURL        string
	ModelRequestTimeout    time.Duration
}

func Load() (Config, error) {
	timeout, err := time.ParseDuration(env("SHUTDOWN_TIMEOUT", "10s"))
	if err != nil {
		return Config{}, fmt.Errorf("parse SHUTDOWN_TIMEOUT: %w", err)
	}
	accessTTL, err := time.ParseDuration(env("JWT_ACCESS_TTL", "1h"))
	if err != nil {
		return Config{}, fmt.Errorf("parse JWT_ACCESS_TTL: %w", err)
	}
	modelRequestTimeout, err := time.ParseDuration(env("MODEL_REQUEST_TIMEOUT", "10s"))
	if err != nil {
		return Config{}, fmt.Errorf("parse MODEL_REQUEST_TIMEOUT: %w", err)
	}

	return Config{
		HTTPAddr:               env("HTTP_ADDR", ":8080"),
		DatabaseURL:            env("DATABASE_URL", "postgres://app:app@localhost:5432/sensor_predictive?sslmode=disable"),
		KafkaBrokers:           splitCSV(env("KAFKA_BROKERS", "localhost:29092")),
		SensorEventsTopic:      env("KAFKA_SENSOR_EVENTS_TOPIC", "sensor.events.v1"),
		PredictionsTopic:       env("KAFKA_PREDICTIONS_TOPIC", "predictions.v1"),
		SensorEventsDLQTopic:   env("KAFKA_SENSOR_EVENTS_DLQ_TOPIC", "sensor.events.dlq.v1"),
		PredictionsDLQTopic:    env("KAFKA_PREDICTIONS_DLQ_TOPIC", "predictions.dlq.v1"),
		ConsumerGroup:          env("KAFKA_CONSUMER_GROUP", "backend.predictions.v1"),
		TelemetryConsumerGroup: env("KAFKA_TELEMETRY_CONSUMER_GROUP", "backend.telemetry.v1"),
		ShutdownTimeout:        timeout,
		JWTSecret:              env("JWT_SECRET", "local-development-secret-change-before-deploy"),
		JWTIssuer:              env("JWT_ISSUER", "sensor-predictive-backend"),
		JWTAccessTTL:           accessTTL,
		BootstrapAdminUsername: env("BOOTSTRAP_ADMIN_USERNAME", "admin"),
		BootstrapAdminPassword: strings.TrimSpace(os.Getenv("BOOTSTRAP_ADMIN_PASSWORD")),
		CORSAllowedOrigins:     splitCSV(env("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")),
		ModelServiceURL:        env("MODEL_SERVICE_URL", "http://model-service:8000"),
		ModelRequestTimeout:    modelRequestTimeout,
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
