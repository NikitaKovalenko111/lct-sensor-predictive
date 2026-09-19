package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/config"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/mockmodel"
	kafkaplatform "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/kafka"
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

	consumer, err := kafkaplatform.NewConsumer(cfg.KafkaBrokers, "mock-model.v1", cfg.SensorEventsTopic)
	if err != nil {
		logger.Error("create kafka consumer", "error", err)
		os.Exit(1)
	}
	defer consumer.Close()
	producer, err := kafkaplatform.NewProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Error("create kafka producer", "error", err)
		os.Exit(1)
	}
	defer producer.Close()

	logger.Info("mock model started", "input_topic", cfg.SensorEventsTopic, "output_topic", cfg.PredictionsTopic)
	if err := mockmodel.New(consumer, producer, cfg.PredictionsTopic, logger).Run(ctx); err != nil {
		logger.Error("mock model failed", "error", err)
		os.Exit(1)
	}
}
