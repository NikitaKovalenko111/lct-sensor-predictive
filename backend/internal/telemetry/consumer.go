package telemetry

import (
	"context"
	"encoding/json"
	"log/slog"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/deadletter"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/retry"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Consumer struct {
	client     *kgo.Client
	repository *Repository
	deadLetter *deadletter.Publisher
	logger     *slog.Logger
}

func NewConsumer(client *kgo.Client, repository *Repository, deadLetter *deadletter.Publisher, logger *slog.Logger) *Consumer {
	return &Consumer{client: client, repository: repository, deadLetter: deadLetter, logger: logger}
}

func (c *Consumer) Run(ctx context.Context) error {
	for {
		fetches := c.client.PollFetches(ctx)
		if ctx.Err() != nil {
			return nil
		}
		if errs := fetches.Errors(); len(errs) > 0 {
			for _, fetchErr := range errs {
				c.logger.Error("telemetry fetch failed", "error", fetchErr.Err)
			}
			continue
		}

		var batchErr error
		fetches.EachRecord(func(record *kgo.Record) {
			if batchErr != nil {
				return
			}
			var event contracts.SensorEvent
			if err := json.Unmarshal(record.Value, &event); err != nil {
				if publishErr := retry.Do(ctx, c.logger, "publish telemetry dead letter", func() error {
					return c.deadLetter.Publish(ctx, record, err)
				}); publishErr != nil {
					batchErr = publishErr
					return
				}
				c.logger.Warn("telemetry sent to dead-letter topic", "error", err, "offset", record.Offset)
				return
			}
			if err := event.Validate(); err != nil {
				if publishErr := retry.Do(ctx, c.logger, "publish telemetry dead letter", func() error {
					return c.deadLetter.Publish(ctx, record, err)
				}); publishErr != nil {
					batchErr = publishErr
					return
				}
				c.logger.Warn("invalid telemetry sent to dead-letter topic", "error", err, "offset", record.Offset)
				return
			}
			batchErr = retry.Do(ctx, c.logger, "persist telemetry", func() error {
				return c.repository.Upsert(ctx, event)
			})
		})
		if batchErr != nil {
			if ctx.Err() != nil {
				return nil
			}
			c.logger.Error("telemetry batch failed", "error", batchErr)
			continue
		}
		if err := retry.Do(ctx, c.logger, "commit telemetry offsets", func() error {
			return c.client.CommitRecords(ctx, fetches.Records()...)
		}); err != nil && ctx.Err() != nil {
			return nil
		}
	}
}
