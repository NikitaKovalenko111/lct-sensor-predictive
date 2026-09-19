package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	docs "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/api"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
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
	predictions *prediction.Repository
	logger      *slog.Logger
}

func New(
	addr string,
	database *pgxpool.Pool,
	kafkaClient *kgo.Client,
	publisher *telemetry.Publisher,
	predictions *prediction.Repository,
	logger *slog.Logger,
) *Server {
	server := &Server{
		database: database, kafka: kafkaClient, publisher: publisher,
		predictions: predictions, logger: logger,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health/live", server.live)
	mux.HandleFunc("GET /health/ready", server.ready)
	mux.HandleFunc("GET /api/openapi.yaml", server.openAPI)
	mux.HandleFunc("POST /api/v1/sensor-events", server.publishSensorEvent)
	mux.HandleFunc("GET /api/v1/predictions", server.listPredictions)
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

func (s *Server) live(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if err := s.database.Ping(ctx); err != nil {
		writeError(w, http.StatusServiceUnavailable, "postgres is unavailable")
		return
	}
	if err := s.kafka.Ping(ctx); err != nil {
		writeError(w, http.StatusServiceUnavailable, "kafka is unavailable")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *Server) openAPI(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/yaml; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(docs.OpenAPISpec)
}

func (s *Server) publishSensorEvent(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	var event contracts.SensorEvent
	if err := decoder.Decode(&event); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if err := s.publisher.Publish(r.Context(), event); err != nil {
		s.logger.Error("publish sensor event", "error", err)
		writeError(w, http.StatusServiceUnavailable, err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"event_id": event.EventID, "status": "accepted"})
}

func (s *Server) listPredictions(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	filter := prediction.ListFilter{
		ObjectID:       parseInt64(query.Get("object_id")),
		PredictionType: query.Get("prediction_type"),
		RiskLevel:      query.Get("risk_level"),
		Limit:          int(parseInt64(query.Get("limit"))),
		Offset:         int(parseInt64(query.Get("offset"))),
	}
	items, err := s.predictions.List(r.Context(), filter)
	if err != nil {
		s.logger.Error("list predictions", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list predictions")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func parseInt64(value string) int64 {
	parsed, _ := strconv.ParseInt(value, 10, 64)
	return parsed
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func recoverPanic(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recovered := recover(); recovered != nil {
				logger.Error("http panic", "panic", recovered)
				writeError(w, http.StatusInternalServerError, "internal server error")
			}
		}()
		next.ServeHTTP(w, r)
	})
}

func requestLog(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		next.ServeHTTP(w, r)
		logger.Info("http request", "method", r.Method, "path", r.URL.Path, "duration", time.Since(started))
	})
}
