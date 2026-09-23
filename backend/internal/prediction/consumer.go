package prediction

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/deadletter"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/incidents"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/platform/retry"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Consumer struct {
	client     *kgo.Client
	repository *Repository
	incidents  *incidents.Repository
	deadLetter *deadletter.Publisher
	logger     *slog.Logger
}

func NewConsumer(client *kgo.Client, repository *Repository, incidentRepository *incidents.Repository, deadLetter *deadletter.Publisher, logger *slog.Logger) *Consumer {
	return &Consumer{client: client, repository: repository, incidents: incidentRepository, deadLetter: deadLetter, logger: logger}
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
				cause := errors.New("decode prediction: " + err.Error())
				if err := retry.Do(ctx, c.logger, "publish prediction dead letter", func() error {
					return c.deadLetter.Publish(ctx, record, cause)
				}); err != nil {
					handlerErr = err
					return
				}
				c.logger.Warn("prediction sent to dead-letter topic", "error", cause, "offset", record.Offset)
				return
			}
			if message.SchemaVersion == 0 {
				message.SchemaVersion = contracts.SchemaVersion
			}
			if err := message.Validate(); err != nil {
				if publishErr := retry.Do(ctx, c.logger, "publish prediction dead letter", func() error {
					return c.deadLetter.Publish(ctx, record, err)
				}); publishErr != nil {
					handlerErr = publishErr
					return
				}
				c.logger.Warn("invalid prediction sent to dead-letter topic", "error", err, "offset", record.Offset)
				return
			}
			var predictionID string
			var incident *incidents.Incident
			if err := retry.Do(ctx, c.logger, "persist prediction and incident", func() error {
				var err error
				predictionID, err = c.repository.Upsert(ctx, message)
				if err != nil {
					return err
				}
				incident, err = c.incidents.CreateFromPrediction(ctx, predictionID)
				return err
			}); err != nil {
				handlerErr = err
				return
			}
			if incident != nil {
				c.logger.Info("incident created", "incident_id", incident.IncidentID, "prediction_id", predictionID)
			}
		})
		if handlerErr != nil {
			if ctx.Err() != nil {
				return nil
			}
			c.logger.Error("prediction batch failed", "error", handlerErr)
			continue
		}
		if err := retry.Do(ctx, c.logger, "commit prediction offsets", func() error {
			return c.client.CommitRecords(ctx, fetches.Records()...)
		}); err != nil && ctx.Err() != nil {
			return nil
		}
	}
}
