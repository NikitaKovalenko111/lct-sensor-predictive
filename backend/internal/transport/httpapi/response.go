package httpapi

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/jackc/pgx/v5/pgtype"
)

func parseInt64(value string) int64 {
	parsed, _ := strconv.ParseInt(value, 10, 64)
	return parsed
}

func parsePagination(w http.ResponseWriter, r *http.Request) (int, int, bool) {
	values := r.URL.Query()
	parse := func(name string) (int, bool) {
		value := values.Get(name)
		if value == `` {
			return 0, true
		}
		parsed, err := strconv.Atoi(value)
		if err != nil || parsed < 0 {
			writeError(w, http.StatusBadRequest, name+` must be a non-negative integer`)
			return 0, false
		}
		return parsed, true
	}
	limit, ok := parse(`limit`)
	if !ok {
		return 0, 0, false
	}
	offset, ok := parse(`offset`)
	return limit, offset, ok
}

func requireUUIDPath(name string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var id pgtype.UUID
		if err := id.Scan(r.PathValue(name)); err != nil || !id.Valid {
			writeError(w, http.StatusBadRequest, name+" must be a valid UUID")
			return
		}
		next(w, r)
	}
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
