package retry

import (
	"context"
	"errors"
	"log/slog"
	"time"
)

type permanentError struct{ error }

func (e permanentError) Unwrap() error { return e.error }

func Permanent(err error) error {
	if err == nil {
		return nil
	}
	return permanentError{error: err}
}

func IsPermanent(err error) bool {
	var target permanentError
	return errors.As(err, &target)
}

const (
	initialDelay = 250 * time.Millisecond
	maximumDelay = 5 * time.Second
)

func Do(ctx context.Context, logger *slog.Logger, operation string, fn func() error) error {
	delay := initialDelay
	for {
		if err := fn(); err != nil {
			if IsPermanent(err) {
				return errors.Unwrap(err)
			}
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
