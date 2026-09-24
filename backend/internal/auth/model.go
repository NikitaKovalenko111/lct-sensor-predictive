package auth

import (
	"context"
	"errors"
	"time"
)

type claimsContextKey struct{}

const (
	RoleAdmin      = "admin"
	RoleDispatcher = "dispatcher"
	RoleAnalyst    = "analyst"
	RoleManager    = "manager"
)

var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrInactiveUser       = errors.New("user is inactive")
	ErrInvalidToken       = errors.New("invalid access token")
	ErrUsernameExists     = errors.New("username already exists")
	ErrUserNotFound       = errors.New("user not found")
)

type User struct {
	UserID      string     `json:"user_id"`
	Username    string     `json:"username"`
	Role        string     `json:"role"`
	Active      bool       `json:"active"`
	CreatedAt   time.Time  `json:"created_at"`
	LastLoginAt *time.Time `json:"last_login_at,omitempty"`
}

type Credentials struct {
	Username string
	Password string
}

// IdentityProvider is the boundary for local authentication now and an LDAP/AD
// adapter later. Transport code must depend on this interface, not LDAP details.
type IdentityProvider interface {
	Authenticate(ctx context.Context, credentials Credentials) (User, error)
}

type AuditEntry struct {
	AuditID    int64          `json:"audit_id"`
	UserID     string         `json:"user_id,omitempty"`
	Username   string         `json:"username"`
	Action     string         `json:"action"`
	Resource   string         `json:"resource_type"`
	ResourceID string         `json:"resource_id,omitempty"`
	Method     string         `json:"method"`
	Path       string         `json:"path"`
	RemoteIP   string         `json:"remote_ip,omitempty"`
	Details    map[string]any `json:"details"`
	CreatedAt  time.Time      `json:"created_at"`
}

type AuditFilter struct {
	Username string
	Action   string
	Limit    int
	Offset   int
}

func ValidRole(role string) bool {
	switch role {
	case RoleAdmin, RoleDispatcher, RoleAnalyst, RoleManager:
		return true
	default:
		return false
	}
}

func WithClaims(ctx context.Context, claims Claims) context.Context {
	return context.WithValue(ctx, claimsContextKey{}, claims)
}

func ClaimsFromContext(ctx context.Context) (Claims, bool) {
	claims, ok := ctx.Value(claimsContextKey{}).(Claims)
	return claims, ok
}
