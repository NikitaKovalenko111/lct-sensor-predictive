package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/config"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/database"
	kafkaplatform "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/kafka"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/prediction"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := config.Load()
	if err != nil {
		logger.Error("load config", "error", err)
		os.Exit(1)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	db, err := database.Open(ctx, cfg.DatabaseURL)
	if err != nil {
		logger.Error("connect database", "error", err)
		os.Exit(1)
	}
	defer db.Close()

	predictionConsumer, err := kafkaplatform.NewConsumer(cfg.KafkaBrokers, cfg.ConsumerGroup, cfg.PredictionsTopic)
	if err != nil {
		logger.Error("create kafka consumer", "error", err)
		os.Exit(1)
	}
	defer predictionConsumer.Close()
	telemetryConsumer, err := kafkaplatform.NewConsumer(cfg.KafkaBrokers, cfg.TelemetryConsumerGroup, cfg.SensorEventsTopic)
	if err != nil {
		logger.Error("create telemetry consumer", "error", err)
		os.Exit(1)
	}
	defer telemetryConsumer.Close()

	workerErr := make(chan error, 2)
	go func() {
		workerErr <- prediction.NewConsumer(predictionConsumer, prediction.NewRepository(db), logger).Run(ctx)
	}()
	go func() {
		workerErr <- telemetry.NewConsumer(telemetryConsumer, telemetry.NewRepository(db), logger).Run(ctx)
	}()
	logger.Info("worker started", "predictions_topic", cfg.PredictionsTopic, "telemetry_topic", cfg.SensorEventsTopic)
	select {
	case <-ctx.Done():
		return
	case err := <-workerErr:
		if err != nil {
			logger.Error("worker failed", "error", err)
			os.Exit(1)
		}
	}
}
