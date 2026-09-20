package httpapi

import (
	"context"
	"net/http"
	"time"

	docs "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/api"
)

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
