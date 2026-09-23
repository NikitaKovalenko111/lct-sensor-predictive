package retry

import (
	"context"
	"log/slog"
	"time"
)

const (
	initialDelay = 250 * time.Millisecond
	maximumDelay = 5 * time.Second
)

func Do(ctx context.Context, logger *slog.Logger, operation string, fn func() error) error {
	delay := initialDelay
	for {
		if err := fn(); err != nil {
			logger.Error("operation failed; retrying", "operation", operation, "retry_in", delay, "error", err)
			timer := time.NewTimer(delay)
			select {
			case <-ctx.Done():
				timer.Stop()
				return ctx.Err()
			case <-timer.C:
			}
			if delay < maximumDelay {
				delay *= 2
				if delay > maximumDelay {
					delay = maximumDelay
				}
			}
			continue
		}
		return nil
	}
}
