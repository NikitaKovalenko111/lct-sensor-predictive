package middleware

import (
	"context"
	"log/slog"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/auth"
)

type Security struct {
	tokens     *auth.TokenManager
	audit      *auth.Repository
	logger     *slog.Logger
	auditLimit time.Duration
}

func NewSecurity(tokens *auth.TokenManager, audit *auth.Repository, logger *slog.Logger) *Security {
	return &Security{tokens: tokens, audit: audit, logger: logger, auditLimit: 2 * time.Second}
}

func (m *Security) RequireRoles(next http.HandlerFunc, roles ...string) http.HandlerFunc {
	allowed := make(map[string]struct{}, len(roles))
	for _, role := range roles {
		allowed[role] = struct{}{}
	}
	return func(w http.ResponseWriter, r *http.Request) {
		const prefix = "Bearer "
		header := r.Header.Get("Authorization")
		if !strings.HasPrefix(header, prefix) {
			writeError(w, http.StatusUnauthorized, "bearer token is required")
			return
		}
		claims, err := m.tokens.Verify(strings.TrimSpace(strings.TrimPrefix(header, prefix)))
		if err != nil {
			writeError(w, http.StatusUnauthorized, "invalid or expired access token")
			return
		}
		if _, ok := allowed[claims.Role]; !ok {
			writeError(w, http.StatusForbidden, "insufficient permissions")
			return
		}
		next(w, r.WithContext(auth.WithClaims(r.Context(), claims)))
	}
}

func (m *Security) AuditMutation(action, resource string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		recorder := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next(recorder, r)
		if recorder.status >= http.StatusBadRequest {
			return
		}
		claims, ok := auth.ClaimsFromContext(r.Context())
		if !ok {
			return
		}
		resourceID := firstNonEmpty(
			r.PathValue("incident_id"), r.PathValue("object_id"), r.PathValue("import_id"), r.PathValue("user_id"),
		)
		ctx, cancel := context.WithTimeout(context.Background(), m.auditLimit)
		defer cancel()
		if err := m.audit.WriteAudit(ctx, auth.AuditEntry{
			UserID: claims.Subject, Username: claims.Username, Action: action,
			Resource: resource, ResourceID: resourceID, Method: r.Method,
			Path: r.URL.Path, RemoteIP: RequestIP(r),
			Details: map[string]any{"status_code": recorder.status},
		}); err != nil {
			m.logger.Error("write audit log", "action", action, "error", err)
		}
	}
}

type statusRecorder struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

func (r *statusRecorder) WriteHeader(status int) {
	if r.wroteHeader {
		return
	}
	r.wroteHeader = true
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}

func RequestIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err == nil {
		return host
	}
	return r.RemoteAddr
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
