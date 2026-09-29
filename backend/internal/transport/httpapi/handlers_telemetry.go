package httpapi

import (
	"net/http"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/auth"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
)

func (s *Server) registerTelemetryRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/sensor-events", s.security.RequireRoles(
		s.security.AuditMutation("sensor_event.publish", "sensor_event", s.publishSensorEvent), auth.RoleAdmin,
	))
	mux.HandleFunc("GET /api/v1/sensor-events", s.security.RequireRoles(
		s.listSensorEvents, auth.RoleAdmin, auth.RoleDispatcher, auth.RoleAnalyst, auth.RoleManager,
	))
}

func (s *Server) publishSensorEvent(w http.ResponseWriter, r *http.Request) {
	var event contracts.SensorEvent
	if !decodeJSON(w, r, &event) {
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
	limit, offset, ok := parsePagination(w, r)
	if !ok {
		return
	}
	items, err := s.telemetry.List(r.Context(), telemetry.ListFilter{
		ObjectID:  parseInt64(query.Get("object_id")),
		ChannelID: query.Get("channel_id"),
		AlarmOnly: query.Get("alarm_only") == "true",
		Limit:     limit,
		Offset:    offset,
	})
	if err != nil {
		s.logger.Error("list sensor events", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list sensor events")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
