package httpapi

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/channels"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/importjob"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/incidents"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/prediction"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Server struct {
	httpServer  *http.Server
	database    *pgxpool.Pool
	kafka       *kgo.Client
	publisher   *telemetry.Publisher
	telemetry   *telemetry.Repository
	predictions *prediction.Repository
	objects     *objects.Repository
	channels    *channels.Repository
	imports     *importjob.Repository
	incidents   *incidents.Repository
	logger      *slog.Logger
}

func New(
	addr string,
	database *pgxpool.Pool,
	kafkaClient *kgo.Client,
	publisher *telemetry.Publisher,
	telemetryRepository *telemetry.Repository,
	predictions *prediction.Repository,
	objectRepository *objects.Repository,
	channelRepository *channels.Repository,
	importRepository *importjob.Repository,
	incidentRepository *incidents.Repository,
	logger *slog.Logger,
) *Server {
	server := &Server{
		database: database, kafka: kafkaClient, publisher: publisher, telemetry: telemetryRepository,
		predictions: predictions, objects: objectRepository, channels: channelRepository,
		imports: importRepository, incidents: incidentRepository, logger: logger,
	}
	mux := http.NewServeMux()
	server.registerRoutes(mux)
	server.httpServer = &http.Server{
		Addr:              addr,
		Handler:           requestLog(logger, recoverPanic(logger, cors(mux))),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	return server
}

func (s *Server) ListenAndServe() error {
	err := s.httpServer.ListenAndServe()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.httpServer.Shutdown(ctx)
}
