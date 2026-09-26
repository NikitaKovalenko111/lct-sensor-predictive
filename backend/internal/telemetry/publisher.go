package telemetry

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Publisher struct {
	client *kgo.Client
	topic  string
}

func NewPublisher(client *kgo.Client, topic string) *Publisher {
	return &Publisher{client: client, topic: topic}
}

func (p *Publisher) Publish(ctx context.Context, event contracts.SensorEvent) error {
	return p.PublishBatch(ctx, []contracts.SensorEvent{event})
}

func (p *Publisher) PublishBatch(ctx context.Context, events []contracts.SensorEvent) error {
	if len(events) == 0 {
		return nil
	}
	records := make([]*kgo.Record, 0, len(events))
	for _, event := range events {
		if event.SchemaVersion == 0 {
			event.SchemaVersion = contracts.SchemaVersion
		}
		if err := event.Validate(); err != nil {
			return fmt.Errorf("validate sensor event: %w", err)
		}
		payload, err := json.Marshal(event)
		if err != nil {
			return fmt.Errorf("marshal sensor event: %w", err)
		}

		records = append(records, &kgo.Record{
			Topic: p.topic,
			Key:   []byte(strconv.FormatInt(event.ObjectID, 10)),
			Value: payload,
		})
	}
	if err := p.client.ProduceSync(ctx, records...).FirstErr(); err != nil {
		return fmt.Errorf("publish sensor event batch: %w", err)
	}
	return nil
}
