package kafka

import (
	"context"
	"fmt"

	"github.com/twmb/franz-go/pkg/kgo"
)

func NewProducer(brokers []string) (*kgo.Client, error) {
	client, err := kgo.NewClient(
		kgo.SeedBrokers(brokers...),
		kgo.RequiredAcks(kgo.AllISRAcks()),
		kgo.ProducerBatchCompression(kgo.SnappyCompression()),
	)
	if err != nil {
		return nil, fmt.Errorf("create kafka producer: %w", err)
	}
	return client, nil
}

func NewConsumer(brokers []string, group string, topics ...string) (*kgo.Client, error) {
	client, err := kgo.NewClient(
		kgo.SeedBrokers(brokers...),
		kgo.ConsumerGroup(group),
		kgo.ConsumeTopics(topics...),
		kgo.DisableAutoCommit(),
	)
	if err != nil {
		return nil, fmt.Errorf("create kafka consumer: %w", err)
	}
	return client, nil
}

func Ping(ctx context.Context, client *kgo.Client) error {
	if err := client.Ping(ctx); err != nil {
		return fmt.Errorf("ping kafka: %w", err)
	}
	return nil
}
