package httpapi

import "net/http"

func (s *Server) registerRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /health/live", s.live)
	mux.HandleFunc("GET /health/ready", s.ready)
	mux.HandleFunc("GET /api/openapi.yaml", s.openAPI)

	mux.HandleFunc("POST /api/v1/sensor-events", s.publishSensorEvent)
	mux.HandleFunc("GET /api/v1/sensor-events", s.listSensorEvents)
	mux.HandleFunc("GET /api/v1/predictions", s.listPredictions)

	mux.HandleFunc("GET /api/v1/objects", s.listObjects)
	mux.HandleFunc("GET /api/v1/objects/{object_id}", s.getObject)
	mux.HandleFunc("GET /api/v1/channels", s.listChannels)
	mux.HandleFunc("GET /api/v1/map/objects.geojson", s.objectsGeoJSON)

	mux.HandleFunc("GET /api/v1/imports", s.listImports)
	mux.HandleFunc("GET /api/v1/imports/{import_id}", s.getImport)
}
