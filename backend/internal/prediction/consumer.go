package prediction

import (
	"context"
	"encoding/json"
	"errors"
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
				c.logger.Error("kafka fetch failed", "topic", fetchErr.Topic, "partition", fetchErr.Partition, "error", fetchErr.Err)
			}
			continue
		}

		var handlerErr error
		fetches.EachRecord(func(record *kgo.Record) {
			if handlerErr != nil {
				return
			}
			var message contracts.Prediction
			if err := json.Unmarshal(record.Value, &message); err != nil {
				handlerErr = errors.New("decode prediction: " + err.Error())
				return
			}
			if message.SchemaVersion == 0 {
				message.SchemaVersion = contracts.SchemaVersion
			}
			if err := c.repository.Upsert(ctx, message); err != nil {
				handlerErr = err
			}
		})
		if handlerErr != nil {
			c.logger.Error("prediction batch failed", "error", handlerErr)
			continue
		}
		if err := c.client.CommitRecords(ctx, fetches.Records()...); err != nil {
			c.logger.Error("commit kafka offsets", "error", err)
		}
	}
}
