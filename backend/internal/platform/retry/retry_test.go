package retry

import (
	"context"
	"errors"
	"log/slog"
	"testing"
)

func TestDoDoesNotRetryPermanentError(t *testing.T) {
	want := errors.New("invalid message")
	attempts := 0
	err := Do(context.Background(), slog.Default(), "test", func() error {
		attempts++
		return Permanent(want)
	})
	if !errors.Is(err, want) {
		t.Fatalf("unexpected error: %v", err)
	}
	if attempts != 1 {
		t.Fatalf("unexpected attempt count: got %d, want 1", attempts)
	}
}
