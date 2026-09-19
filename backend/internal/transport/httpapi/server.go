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
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/channels"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/importjob"
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
	logger *slog.Logger,
) *Server {
	server := &Server{
		database: database, kafka: kafkaClient, publisher: publisher, telemetry: telemetryRepository,
		predictions: predictions, objects: objectRepository, channels: channelRepository,
		imports: importRepository, logger: logger,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health/live", server.live)
	mux.HandleFunc("GET /health/ready", server.ready)
	mux.HandleFunc("GET /api/openapi.yaml", server.openAPI)
	mux.HandleFunc("POST /api/v1/sensor-events", server.publishSensorEvent)
	mux.HandleFunc("GET /api/v1/sensor-events", server.listSensorEvents)
	mux.HandleFunc("GET /api/v1/predictions", server.listPredictions)
	mux.HandleFunc("GET /api/v1/objects", server.listObjects)
	mux.HandleFunc("GET /api/v1/objects/{object_id}", server.getObject)
	mux.HandleFunc("GET /api/v1/channels", server.listChannels)
	mux.HandleFunc("GET /api/v1/map/objects.geojson", server.objectsGeoJSON)
	mux.HandleFunc("GET /api/v1/imports", server.listImports)
	mux.HandleFunc("GET /api/v1/imports/{import_id}", server.getImport)
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

func (s *Server) listSensorEvents(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.telemetry.List(r.Context(), telemetry.ListFilter{
		ObjectID:  parseInt64(query.Get("object_id")),
		ChannelID: query.Get("channel_id"),
		AlarmOnly: query.Get("alarm_only") == "true",
		Limit:     int(parseInt64(query.Get("limit"))),
		Offset:    int(parseInt64(query.Get("offset"))),
	})
	if err != nil {
		s.logger.Error("list sensor events", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list sensor events")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
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

func (s *Server) listObjects(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.objects.List(r.Context(), objects.ListFilter{
		ParentID:   parseInt64(query.Get("parent_id")),
		ObjectType: query.Get("object_type"),
		Search:     query.Get("search"),
		Limit:      int(parseInt64(query.Get("limit"))),
		Offset:     int(parseInt64(query.Get("offset"))),
	})
	if err != nil {
		s.logger.Error("list objects", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list objects")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) getObject(w http.ResponseWriter, r *http.Request) {
	objectID := parseInt64(r.PathValue("object_id"))
	if objectID <= 0 {
		writeError(w, http.StatusBadRequest, "invalid object_id")
		return
	}
	item, err := s.objects.Get(r.Context(), objectID)
	if errors.Is(err, objects.ErrNotFound) {
		writeError(w, http.StatusNotFound, "object not found")
		return
	}
	if err != nil {
		s.logger.Error("get object", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to get object")
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (s *Server) listChannels(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.channels.ListByObject(
		r.Context(),
		parseInt64(query.Get("object_id")),
		int(parseInt64(query.Get("limit"))),
		int(parseInt64(query.Get("offset"))),
	)
	if err != nil {
		s.logger.Error("list channels", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list channels")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) objectsGeoJSON(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.objects.List(r.Context(), objects.ListFilter{
		ObjectType: query.Get("object_type"),
		Limit:      int(parseInt64(query.Get("limit"))),
		Offset:     int(parseInt64(query.Get("offset"))),
	})
	if err != nil {
		s.logger.Error("list map objects", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to build GeoJSON")
		return
	}
	features := make([]map[string]any, 0, len(items))
	for _, item := range items {
		features = append(features, map[string]any{
			"type":     "Feature",
			"id":       item.ObjectID,
			"geometry": item.Geometry,
			"properties": map[string]any{
				"object_id":       item.ObjectID,
				"parent_id":       item.ParentID,
				"object_type":     item.ObjectType,
				"dispatcher_name": item.DispatcherName,
				"synthetic":       true,
			},
		})
	}
	w.Header().Set("Content-Type", "application/geo+json; charset=utf-8")
	writeJSON(w, http.StatusOK, map[string]any{"type": "FeatureCollection", "features": features})
}

func (s *Server) listImports(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.imports.List(
		r.Context(),
		int(parseInt64(query.Get("limit"))),
		int(parseInt64(query.Get("offset"))),
	)
	if err != nil {
		s.logger.Error("list imports", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list imports")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) getImport(w http.ResponseWriter, r *http.Request) {
	item, err := s.imports.Get(r.Context(), r.PathValue("import_id"))
	if errors.Is(err, importjob.ErrNotFound) {
		writeError(w, http.StatusNotFound, "import job not found")
		return
	}
	if err != nil {
		s.logger.Error("get import", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to get import job")
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func parseInt64(value string) int64 {
	parsed, _ := strconv.ParseInt(value, 10, 64)
	return parsed
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	if w.Header().Get("Content-Type") == "" {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
	}
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
