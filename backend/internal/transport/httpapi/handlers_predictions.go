package httpapi

import (
	"errors"
	"net/http"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/auth"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/modelclient"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/prediction"
)

func (s *Server) registerPredictionRoutes(mux *http.ServeMux) {
	readRoles := []string{auth.RoleAdmin, auth.RoleDispatcher, auth.RoleAnalyst, auth.RoleManager}
	mux.HandleFunc("GET /api/v1/predictions", s.security.RequireRoles(
		s.listPredictions, readRoles...,
	))
	mux.HandleFunc("POST /api/v1/predictions/request", s.security.RequireRoles(
		s.security.AuditMutation("prediction.request", "prediction", s.requestPrediction), readRoles...,
	))
}

func (s *Server) requestPrediction(w http.ResponseWriter, r *http.Request) {
	var request modelclient.PredictionRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	if err := request.Validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if _, err := s.objects.Get(r.Context(), request.ObjectID); errors.Is(err, objects.ErrNotFound) {
		writeError(w, http.StatusNotFound, "object not found")
		return
	} else if err != nil {
		s.logger.Error("get object for on-demand prediction", "object_id", request.ObjectID, "error", err)
		writeError(w, http.StatusInternalServerError, "failed to validate object")
		return
	}
	response, err := s.model.Predict(r.Context(), request)
	if errors.Is(err, modelclient.ErrUnavailable) {
		s.logger.Error("request on-demand prediction", "object_id", request.ObjectID, "error", err)
		writeError(w, http.StatusServiceUnavailable, "model service is unavailable")
		return
	}
	if err != nil {
		s.logger.Error("process model response", "object_id", request.ObjectID, "error", err)
		writeError(w, http.StatusBadGateway, "model service returned an invalid response")
		return
	}
	writeJSON(w, http.StatusOK, response)
}

func (s *Server) listPredictions(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	limit, offset, ok := parsePagination(w, r)
	if !ok {
		return
	}
	filter := prediction.ListFilter{
		ObjectID:       parseInt64(query.Get("object_id")),
		PredictionType: query.Get("prediction_type"),
		RiskLevel:      query.Get("risk_level"),
		AlertOnly:      query.Get("alert_only") == "true",
		Limit:          limit,
		Offset:         offset,
	}
	items, err := s.predictions.List(r.Context(), filter)
	if err != nil {
		s.logger.Error("list predictions", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list predictions")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
