package middleware

import (
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/auth"
)

func TestRequireRoles(t *testing.T) {
	tokens, err := auth.NewTokenManager("test-secret-that-is-at-least-32-characters", "test", time.Hour)
	if err != nil {
		t.Fatalf("NewTokenManager: %v", err)
	}
	security := NewSecurity(tokens, nil, slog.New(slog.NewTextHandler(io.Discard, nil)))
	handler := security.RequireRoles(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}, auth.RoleDispatcher)

	dispatcherToken, _, err := tokens.Issue(auth.User{
		UserID: "dispatcher-id", Username: "dispatcher", Role: auth.RoleDispatcher,
	})
	if err != nil {
		t.Fatalf("Issue dispatcher token: %v", err)
	}
	request := httptest.NewRequest(http.MethodGet, "/", nil)
	request.Header.Set("Authorization", "Bearer "+dispatcherToken)
	response := httptest.NewRecorder()
	handler(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("dispatcher status: got %d, want %d", response.Code, http.StatusNoContent)
	}

	managerToken, _, err := tokens.Issue(auth.User{
		UserID: "manager-id", Username: "manager", Role: auth.RoleManager,
	})
	if err != nil {
		t.Fatalf("Issue manager token: %v", err)
	}
	request = httptest.NewRequest(http.MethodGet, "/", nil)
	request.Header.Set("Authorization", "Bearer "+managerToken)
	response = httptest.NewRecorder()
	handler(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("manager status: got %d, want %d", response.Code, http.StatusForbidden)
	}

	request = httptest.NewRequest(http.MethodGet, "/", nil)
	response = httptest.NewRecorder()
	handler(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous status: got %d, want %d", response.Code, http.StatusUnauthorized)
	}
}
