package telemetry

import (
	"context"
	"encoding/json"
	"log/slog"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Consumer struct {
	client     *kgo.Client
	repository *Repository
	logger     *slog.Logger
}

func NewConsumer(client *kgo.Client, repository *Repository, logger *slog.Logger) *Consumer {
	return &Consumer{client: client, repository: repository, logger: logger}
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
				batchErr = err
				return
			}
			if event.SchemaVersion == 0 {
				event.SchemaVersion = contracts.SchemaVersion
			}
			batchErr = c.repository.Upsert(ctx, event)
		})
		if batchErr != nil {
			c.logger.Error("telemetry batch failed", "error", batchErr)
			continue
		}
		if err := c.client.CommitRecords(ctx, fetches.Records()...); err != nil {
			c.logger.Error("commit telemetry offsets", "error", err)
		}
	}
}
