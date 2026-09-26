package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/config"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	kafkaplatform "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/kafka"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
)

func main() {
	interval := flag.Duration("interval", 5*time.Second, "interval between sensor events")
	objectID := flag.Int64("object-id", 1001, "object identifier")
	flag.Parse()

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := config.Load()
	if err != nil {
		logger.Error("load config", "error", err)
		os.Exit(1)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	client, err := kafkaplatform.NewProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Error("create kafka producer", "error", err)
		os.Exit(1)
	}
	defer client.Close()
	publisher := telemetry.NewPublisher(client, cfg.SensorEventsTopic)

	ticker := time.NewTicker(*interval)
	defer ticker.Stop()
	logger.Info("simulator started", "interval", interval.String(), "object_id", *objectID)
	for {
		select {
		case <-ctx.Done():
			return
		case timestamp := <-ticker.C:
			alarm := rand.IntN(10) < 2
			event := contracts.SensorEvent{
				SchemaVersion:     contracts.SchemaVersion,
				EventID:           fmt.Sprintf("sim-%d", timestamp.UnixNano()),
				ObjectID:          *objectID,
				ChannelID:         "sim-temperature-1",
				SensorType:        "temperature",
				EngineeringSystem: "fire_safety",
				Value:             fmt.Sprintf("%.1f", 20+rand.Float64()*50),
				IsAlarm:           alarm,
				Timestamp:         timestamp.UTC(),
			}
			if err := publisher.Publish(ctx, event); err != nil {
				logger.Error("publish simulated event", "error", err)
				continue
			}
			logger.Info("simulated event published", "event_id", event.EventID, "alarm", alarm)
		}
	}
}
