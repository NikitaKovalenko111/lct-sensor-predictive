package auth

import (
	"testing"
	"time"
)

func TestTokenRoundTrip(t *testing.T) {
	manager, err := NewTokenManager("test-secret-that-is-at-least-32-characters", "test", time.Hour)
	if err != nil {
		t.Fatalf("NewTokenManager: %v", err)
	}
	now := time.Date(2026, time.September, 22, 12, 0, 0, 0, time.UTC)
	manager.now = func() time.Time { return now }
	token, expires, err := manager.Issue(User{UserID: "user-1", Username: "admin", Role: RoleAdmin})
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}
	claims, err := manager.Verify(token)
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if claims.Subject != "user-1" || claims.Role != RoleAdmin {
		t.Fatalf("unexpected claims: %+v", claims)
	}
	if !expires.Equal(now.Add(time.Hour)) {
		t.Fatalf("unexpected expiry: %s", expires)
	}
}

func TestTokenRejectsTamperingAndExpiration(t *testing.T) {
	manager, err := NewTokenManager("test-secret-that-is-at-least-32-characters", "test", time.Minute)
	if err != nil {
		t.Fatalf("NewTokenManager: %v", err)
	}
	now := time.Date(2026, time.September, 22, 12, 0, 0, 0, time.UTC)
	manager.now = func() time.Time { return now }
	token, _, err := manager.Issue(User{UserID: "user-1", Username: "admin", Role: RoleAdmin})
	if err != nil {
		t.Fatalf("Issue: %v", err)
	}
	if _, err := manager.Verify(token + "x"); err == nil {
		t.Fatal("expected tampered token to fail")
	}
	manager.now = func() time.Time { return now.Add(2 * time.Minute) }
	if _, err := manager.Verify(token); err == nil {
		t.Fatal("expected expired token to fail")
	}
}
