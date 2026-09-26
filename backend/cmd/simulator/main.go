package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/channels"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/config"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/database"
	kafkaplatform "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/kafka"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
)

const registryPageSize = 500

type simulationChannel struct {
	channelID         string
	sensorType        string
	engineeringSystem string
}

func main() {
	interval := flag.Duration("interval", 5*time.Second, "interval between batches of sensor events")
	registryRefresh := flag.Duration("registry-refresh", time.Minute, "interval between object registry reloads")
	objectID := flag.Int64("object-id", 0, "optional object identifier; zero simulates every object")
	flag.Parse()

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

	objectRepository := objects.NewRepository(db)
	channelRepository := channels.NewRepository(db, objectRepository)
	registry, err := loadRegistry(ctx, objectRepository, channelRepository, *objectID)
	if err != nil {
		logger.Error("load simulation registry", "error", err)
		os.Exit(1)
	}
	if len(registry) == 0 {
		logger.Error("simulation registry is empty")
		os.Exit(1)
	}

	client, err := kafkaplatform.NewProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Error("create kafka producer", "error", err)
		os.Exit(1)
	}
	defer client.Close()
	publisher := telemetry.NewPublisher(client, cfg.SensorEventsTopic)

	publish := func(timestamp time.Time) {
		events, alarms := simulatedEvents(registry, timestamp)
		if err := publisher.PublishBatch(ctx, events); err != nil {
			logger.Error("publish simulated events", "error", err)
			return
		}
		logger.Info("simulated event batch published", "events", len(events), "alarms", alarms)
	}

	logger.Info("simulator started", "interval", interval.String(), "objects", len(registry))
	publish(time.Now())

	eventTicker := time.NewTicker(*interval)
	defer eventTicker.Stop()
	refreshTicker := time.NewTicker(*registryRefresh)
	defer refreshTicker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case timestamp := <-eventTicker.C:
			publish(timestamp)
		case <-refreshTicker.C:
			updated, err := loadRegistry(ctx, objectRepository, channelRepository, *objectID)
			if err != nil {
				logger.Error("refresh simulation registry", "error", err)
				continue
			}
			registry = updated
			logger.Info("simulation registry refreshed", "objects", len(registry))
		}
	}
}

func loadRegistry(
	ctx context.Context,
	objectRepository *objects.Repository,
	channelRepository *channels.Repository,
	objectID int64,
) (map[int64][]simulationChannel, error) {
	channelLookup, err := channelRepository.EventLookup(ctx)
	if err != nil {
		return nil, err
	}
	channelsByObject := make(map[int64][]simulationChannel)
	for channelID, metadata := range channelLookup {
		channelsByObject[metadata.ObjectID] = append(channelsByObject[metadata.ObjectID], simulationChannel{
			channelID: channelID, sensorType: metadata.SensorType,
			engineeringSystem: metadata.EngineeringSystem,
		})
	}

	result := make(map[int64][]simulationChannel)
	for offset := 0; ; offset += registryPageSize {
		items, err := objectRepository.List(ctx, objects.ListFilter{
			Limit: registryPageSize, Offset: offset,
		})
		if err != nil {
			return nil, err
		}
		for _, item := range items {
			if objectID != 0 && item.ObjectID != objectID {
				continue
			}
			objectChannels := channelsByObject[item.ObjectID]
			if len(objectChannels) == 0 {
				objectChannels = []simulationChannel{{
					channelID:  fmt.Sprintf("sim-temperature-%d", item.ObjectID),
					sensorType: "Датчик температуры", engineeringSystem: "Температурная подсистема",
				}}
			}
			result[item.ObjectID] = objectChannels
		}
		if len(items) < registryPageSize {
			break
		}
	}
	return result, nil
}

func simulatedEvents(registry map[int64][]simulationChannel, timestamp time.Time) ([]contracts.SensorEvent, int) {
	events := make([]contracts.SensorEvent, 0, len(registry))
	alarms := 0
	for objectID, objectChannels := range registry {
		channel := objectChannels[rand.IntN(len(objectChannels))]
		alarm := rand.IntN(10) < 2
		if alarm {
			alarms++
		}
		events = append(events, contracts.SensorEvent{
			SchemaVersion:     contracts.SchemaVersion,
			EventID:           fmt.Sprintf("sim-%d-%d", objectID, timestamp.UnixNano()),
			ObjectID:          objectID,
			ChannelID:         channel.channelID,
			SensorType:        channel.sensorType,
			EngineeringSystem: channel.engineeringSystem,
			Value:             simulatedValue(channel.sensorType, alarm),
			IsAlarm:           alarm,
			Timestamp:         timestamp.UTC(),
		})
	}
	return events, alarms
}

func simulatedValue(sensorType string, alarm bool) string {
	normalized := strings.ToLower(sensorType)
	switch {
	case strings.Contains(normalized, "температур"):
		if alarm {
			return fmt.Sprintf("%.1f", 55+rand.Float64()*20)
		}
		return fmt.Sprintf("%.1f", 18+rand.Float64()*12)
	case strings.Contains(normalized, "движен"):
		if alarm {
			return "Обнаружено движение"
		}
		return "Нет движения"
	case strings.Contains(normalized, "двер"), strings.Contains(normalized, "люк"), strings.Contains(normalized, "стекл"):
		if alarm {
			return "Не замкнут"
		}
		return "Замкнут"
	default:
		if alarm {
			return "Неисправен"
		}
		return "Норма"
	}
}
