package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/auth"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/incidents"
)

func (s *Server) registerIncidentRoutes(mux *http.ServeMux) {
	readRoles := []string{auth.RoleAdmin, auth.RoleDispatcher, auth.RoleAnalyst, auth.RoleManager}
	writeRoles := []string{auth.RoleAdmin, auth.RoleDispatcher}
	mux.HandleFunc("GET /api/v1/incidents", s.security.RequireRoles(s.listIncidents, readRoles...))
	mux.HandleFunc("GET /api/v1/incidents/stream", s.security.RequireRoles(s.streamIncidents, readRoles...))
	mux.HandleFunc("GET /api/v1/incidents/{incident_id}", s.security.RequireRoles(s.getIncident, readRoles...))
	mux.HandleFunc("PATCH /api/v1/incidents/{incident_id}/assignment", s.security.RequireRoles(
		s.security.AuditMutation("incident.assign", "incident", s.assignIncident), writeRoles...,
	))
	mux.HandleFunc("POST /api/v1/incidents/{incident_id}/decisions", s.security.RequireRoles(
		s.security.AuditMutation("incident.decide", "incident", s.addIncidentDecision), writeRoles...,
	))
	mux.HandleFunc("POST /api/v1/incidents/{incident_id}/resolve", s.security.RequireRoles(
		s.security.AuditMutation("incident.resolve", "incident", s.resolveIncident), writeRoles...,
	))
	mux.HandleFunc("POST /api/v1/incidents/{incident_id}/work-order-draft", s.security.RequireRoles(
		s.security.AuditMutation("work_order.upsert_draft", "incident", s.createWorkOrderDraft), writeRoles...,
	))
}

func (s *Server) listIncidents(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.incidents.List(r.Context(), incidents.ListFilter{
		ObjectID:  parseInt64(query.Get("object_id")),
		Status:    query.Get("status"),
		RiskLevel: query.Get("risk_level"),
		Limit:     int(parseInt64(query.Get("limit"))),
		Offset:    int(parseInt64(query.Get("offset"))),
	})
	if err != nil {
		s.logger.Error("list incidents", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list incidents")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) getIncident(w http.ResponseWriter, r *http.Request) {
	item, err := s.incidents.Get(r.Context(), r.PathValue("incident_id"))
	if s.writeIncidentError(w, err) {
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (s *Server) assignIncident(w http.ResponseWriter, r *http.Request) {
	var request struct {
		AssignedTo string `json:"assigned_to"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	request.AssignedTo = strings.TrimSpace(request.AssignedTo)
	if request.AssignedTo == "" {
		writeError(w, http.StatusBadRequest, "assigned_to is required")
		return
	}
	item, err := s.incidents.Assign(r.Context(), r.PathValue("incident_id"), request.AssignedTo)
	if s.writeIncidentError(w, err) {
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (s *Server) addIncidentDecision(w http.ResponseWriter, r *http.Request) {
	var request struct {
		Decision string `json:"decision"`
		Actor    string `json:"actor"`
		Comment  string `json:"comment"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	request.Actor = strings.TrimSpace(request.Actor)
	if !incidents.ValidDecision(request.Decision) {
		writeError(w, http.StatusBadRequest, "invalid decision")
		return
	}
	if request.Actor == "" {
		writeError(w, http.StatusBadRequest, "actor is required")
		return
	}
	item, err := s.incidents.AddDecision(
		r.Context(), r.PathValue("incident_id"), request.Decision, request.Actor, request.Comment,
	)
	if s.writeIncidentError(w, err) {
		return
	}
	writeJSON(w, http.StatusCreated, item)
}

func (s *Server) resolveIncident(w http.ResponseWriter, r *http.Request) {
	item, err := s.incidents.Resolve(r.Context(), r.PathValue("incident_id"))
	if s.writeIncidentError(w, err) {
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (s *Server) createWorkOrderDraft(w http.ResponseWriter, r *http.Request) {
	var request struct {
		Title       string `json:"title"`
		Description string `json:"description"`
		Priority    string `json:"priority"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	detail, err := s.incidents.Get(r.Context(), r.PathValue("incident_id"))
	if s.writeIncidentError(w, err) {
		return
	}
	if strings.TrimSpace(request.Title) == "" {
		request.Title = "Заявка: " + detail.Title
	}
	if strings.TrimSpace(request.Description) == "" {
		request.Description = detail.Description
	}
	if request.Priority == "" {
		request.Priority = "high"
		if detail.RiskLevel == "critical" {
			request.Priority = "emergency"
		}
	}
	if request.Priority != "normal" && request.Priority != "high" && request.Priority != "emergency" {
		writeError(w, http.StatusBadRequest, "invalid priority")
		return
	}
	item, err := s.incidents.CreateWorkOrder(
		r.Context(), detail.IncidentID, request.Title, request.Description, request.Priority,
	)
	if s.writeIncidentError(w, err) {
		return
	}
	writeJSON(w, http.StatusCreated, item)
}

func (s *Server) streamIncidents(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming is unsupported")
		return
	}
	connection, err := s.incidents.Pool().Acquire(r.Context())
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "failed to subscribe to incidents")
		return
	}
	defer connection.Release()
	if _, err := connection.Exec(r.Context(), "LISTEN incident_events"); err != nil {
		writeError(w, http.StatusServiceUnavailable, "failed to subscribe to incidents")
		return
	}
	defer func() { _, _ = connection.Exec(context.Background(), "UNLISTEN incident_events") }()

	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	_ = http.NewResponseController(w).SetWriteDeadline(time.Time{})
	_, _ = fmt.Fprint(w, "event: ready\ndata: {}\n\n")
	flusher.Flush()

	for {
		waitContext, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		notification, err := connection.Conn().WaitForNotification(waitContext)
		cancel()
		if r.Context().Err() != nil {
			return
		}
		if errors.Is(err, context.DeadlineExceeded) {
			if _, err := fmt.Fprint(w, ": keep-alive\n\n"); err != nil {
				return
			}
			flusher.Flush()
			continue
		}
		if err != nil {
			s.logger.Error("wait for incident notification", "error", err)
			return
		}
		if _, err := fmt.Fprintf(w, "event: incident\ndata: %s\n\n", notification.Payload); err != nil {
			return
		}
		flusher.Flush()
	}
}

func decodeJSON(w http.ResponseWriter, r *http.Request, target any) bool {
	defer r.Body.Close()
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return false
	}
	return true
}

func (s *Server) writeIncidentError(w http.ResponseWriter, err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, incidents.ErrNotFound) {
		writeError(w, http.StatusNotFound, "incident not found or cannot be changed")
		return true
	}
	s.logger.Error("incident operation", "error", err)
	writeError(w, http.StatusInternalServerError, "incident operation failed")
	return true
}
