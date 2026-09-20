package httpapi

import (
	"net/http"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/prediction"
)

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
