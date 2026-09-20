package httpapi

import (
	"errors"
	"net/http"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
)

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
