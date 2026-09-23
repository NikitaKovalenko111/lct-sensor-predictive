package httpapi

import (
	"errors"
	"net/http"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/importjob"
)

func (s *Server) registerImportRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/imports", s.listImports)
	mux.HandleFunc("GET /api/v1/imports/{import_id}", s.getImport)
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
