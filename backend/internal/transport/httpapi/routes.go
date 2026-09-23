package httpapi

import "net/http"

func (s *Server) registerRoutes(mux *http.ServeMux) {
	s.registerSystemRoutes(mux)
	s.registerTelemetryRoutes(mux)
	s.registerPredictionRoutes(mux)
	s.registerIncidentRoutes(mux)
	s.registerObjectRoutes(mux)
	s.registerImportRoutes(mux)
}
