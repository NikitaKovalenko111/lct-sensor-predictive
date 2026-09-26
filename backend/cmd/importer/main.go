package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/channels"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/config"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/importer"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/importjob"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/database"
	kafkaplatform "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/kafka"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
)

func main() {
	objectsPath := flag.String("objects", "", "path to the objects registry CSV")
	channelsPath := flag.String("channels", "", "path to the sensor channels registry CSV")
	eventsPath := flag.String("events", "", "path to the sensor events CSV")
	eventsLookback := flag.Duration("events-lookback", 0, "import only this period before the latest event in the dataset (for example 1080h)")
	batchSize := flag.Int("batch-size", 500, "number of records per database/Kafka batch")
	flag.Parse()

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if *objectsPath == "" && *channelsPath == "" && *eventsPath == "" {
		logger.Error("at least one of --objects, --channels or --events is required")
		os.Exit(2)
	}
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
	kafkaClient, err := kafkaplatform.NewProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Error("create kafka producer", "error", err)
		os.Exit(1)
	}
	defer kafkaClient.Close()

	objectRepository := objects.NewRepository(db)
	eventRepository := telemetry.NewRepository(db)
	service := importer.NewService(
		objectRepository,
		channels.NewRepository(db, objectRepository),
		importjob.NewRepository(db),
		telemetry.NewPublisher(kafkaClient, cfg.SensorEventsTopic),
		eventRepository,
		logger,
		*batchSize,
	)

	if *objectsPath != "" {
		result, err := service.ImportObjects(ctx, *objectsPath)
		if err != nil {
			logger.Error("objects import failed", "import_id", result.ImportID, "error", err)
			os.Exit(1)
		}
		logger.Info("objects import completed", "import_id", result.ImportID, "processed", result.Processed, "failed", result.Failed)
	}
	if *channelsPath != "" {
		result, err := service.ImportChannels(ctx, *channelsPath)
		if err != nil {
			logger.Error("channels import failed", "import_id", result.ImportID, "error", err)
			os.Exit(1)
		}
		logger.Info("channels import completed", "import_id", result.ImportID, "processed", result.Processed, "failed", result.Failed)
	}
	if *eventsPath != "" {
		result, err := service.ImportEvents(ctx, *eventsPath, *eventsLookback)
		if err != nil {
			logger.Error("events import failed", "import_id", result.ImportID, "error", err)
			os.Exit(1)
		}
		logger.Info("events import completed", "import_id", result.ImportID, "processed", result.Processed, "failed", result.Failed)
	}
}
