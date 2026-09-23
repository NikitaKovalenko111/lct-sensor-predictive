package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/auth"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/channels"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/config"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/importjob"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/incidents"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/database"
	kafkaplatform "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/kafka"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/prediction"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/transport/httpapi"
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
	authRepository := auth.NewRepository(db)
	if err := authRepository.EnsureBootstrapAdmin(
		ctx, cfg.BootstrapAdminUsername, cfg.BootstrapAdminPassword,
	); err != nil {
		logger.Error("create bootstrap admin", "error", err)
		os.Exit(1)
	}
	identityProvider, err := auth.NewLocalProvider(authRepository)
	if err != nil {
		logger.Error("create identity provider", "error", err)
		os.Exit(1)
	}
	tokenManager, err := auth.NewTokenManager(cfg.JWTSecret, cfg.JWTIssuer, cfg.JWTAccessTTL)
	if err != nil {
		logger.Error("create token manager", "error", err)
		os.Exit(1)
	}

	kafkaClient, err := kafkaplatform.NewProducer(cfg.KafkaBrokers)
	if err != nil {
		logger.Error("create kafka client", "error", err)
		os.Exit(1)
	}
	defer kafkaClient.Close()
	objectRepository := objects.NewRepository(db)

	server := httpapi.New(
		cfg.HTTPAddr,
		cfg.CORSAllowedOrigins,
		db,
		kafkaClient,
		telemetry.NewPublisher(kafkaClient, cfg.SensorEventsTopic),
		telemetry.NewRepository(db),
		prediction.NewRepository(db),
		objectRepository,
		channels.NewRepository(db, objectRepository),
		importjob.NewRepository(db),
		incidents.NewRepository(db),
		identityProvider,
		tokenManager,
		authRepository,
		logger,
	)

	serverErr := make(chan error, 1)
	go func() {
		logger.Info("api started", "address", cfg.HTTPAddr)
		serverErr <- server.ListenAndServe()
	}()

	select {
	case err := <-serverErr:
		if err != nil {
			logger.Error("api stopped", "error", err)
			os.Exit(1)
		}
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			logger.Error("graceful shutdown", "error", err)
		}
		// Give structured log handlers a chance to flush in container runtimes.
		time.Sleep(10 * time.Millisecond)
	}
}
