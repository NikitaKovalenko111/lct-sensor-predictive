package httpapi

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/auth"
	httpmiddleware "github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/transport/httpapi/middleware"
)

func (s *Server) registerAuthRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v1/auth/login", s.login)
	mux.HandleFunc("GET /api/v1/auth/me", s.security.RequireRoles(
		s.me, auth.RoleAdmin, auth.RoleDispatcher, auth.RoleAnalyst, auth.RoleManager,
	))
	mux.HandleFunc("GET /api/v1/users", s.security.RequireRoles(s.listUsers, auth.RoleAdmin))
	mux.HandleFunc("POST /api/v1/users", s.security.RequireRoles(
		s.security.AuditMutation("user.create", "user", s.createUser), auth.RoleAdmin,
	))
	mux.HandleFunc("GET /api/v1/audit-logs", s.security.RequireRoles(s.listAuditLogs, auth.RoleAdmin))
}

func (s *Server) listUsers(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.authRepository.ListUsers(
		r.Context(), int(parseInt64(query.Get("limit"))), int(parseInt64(query.Get("offset"))),
	)
	if err != nil {
		s.logger.Error("list users", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list users")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) createUser(w http.ResponseWriter, r *http.Request) {
	var request struct {
		Username string `json:"username"`
		Password string `json:"password"`
		Role     string `json:"role"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	user, err := s.authRepository.CreateUser(r.Context(), request.Username, request.Password, request.Role)
	if errors.Is(err, auth.ErrUsernameExists) {
		writeError(w, http.StatusConflict, "username already exists")
		return
	}
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, user)
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	var request struct {
		Username string `json:"username"`
		Password string `json:"password"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	request.Username = strings.TrimSpace(request.Username)
	user, err := s.identityProvider.Authenticate(r.Context(), auth.Credentials{
		Username: request.Username,
		Password: request.Password,
	})
	if errors.Is(err, auth.ErrInvalidCredentials) || errors.Is(err, auth.ErrInactiveUser) {
		s.writeLoginAudit("", request.Username, "auth.login.failed", r)
		writeError(w, http.StatusUnauthorized, "invalid username or password")
		return
	}
	if err != nil {
		s.logger.Error("authenticate user", "error", err)
		writeError(w, http.StatusInternalServerError, "authentication failed")
		return
	}
	token, expiresAt, err := s.tokens.Issue(user)
	if err != nil {
		s.logger.Error("issue access token", "error", err)
		writeError(w, http.StatusInternalServerError, "authentication failed")
		return
	}
	s.writeLoginAudit(user.UserID, user.Username, "auth.login.succeeded", r)
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token": token,
		"token_type":   "Bearer",
		"expires_at":   expiresAt,
		"user":         user,
	})
}

func (s *Server) me(w http.ResponseWriter, r *http.Request) {
	claims, _ := auth.ClaimsFromContext(r.Context())
	writeJSON(w, http.StatusOK, map[string]string{
		"user_id":  claims.Subject,
		"username": claims.Username,
		"role":     claims.Role,
	})
}

func (s *Server) listAuditLogs(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	items, err := s.authRepository.ListAudit(r.Context(), auth.AuditFilter{
		Username: query.Get("username"),
		Action:   query.Get("action"),
		Limit:    int(parseInt64(query.Get("limit"))),
		Offset:   int(parseInt64(query.Get("offset"))),
	})
	if err != nil {
		s.logger.Error("list audit logs", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to list audit logs")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) writeLoginAudit(userID, username, action string, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := s.authRepository.WriteAudit(ctx, auth.AuditEntry{
		UserID: userID, Username: strings.ToLower(strings.TrimSpace(username)), Action: action,
		Resource: "session", Method: r.Method, Path: r.URL.Path,
		RemoteIP: httpmiddleware.RequestIP(r), Details: map[string]any{},
	}); err != nil {
		s.logger.Error("write login audit", "action", action, "error", err)
	}
}
