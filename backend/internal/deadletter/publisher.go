package deadletter

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"time"

	"github.com/twmb/franz-go/pkg/kgo"
)

type Publisher struct {
	client *kgo.Client
	topic  string
}

type Message struct {
	SourceTopic     string    `json:"source_topic"`
	SourcePartition int32     `json:"source_partition"`
	SourceOffset    int64     `json:"source_offset"`
	KeyBase64       string    `json:"key_base64,omitempty"`
	ValueBase64     string    `json:"value_base64"`
	Error           string    `json:"error"`
	FailedAt        time.Time `json:"failed_at"`
}

func NewPublisher(client *kgo.Client, topic string) *Publisher {
	return &Publisher{client: client, topic: topic}
}

func (p *Publisher) Publish(ctx context.Context, source *kgo.Record, cause error) error {
	message := Message{
		SourceTopic: source.Topic, SourcePartition: source.Partition, SourceOffset: source.Offset,
		KeyBase64:   base64.StdEncoding.EncodeToString(source.Key),
		ValueBase64: base64.StdEncoding.EncodeToString(source.Value),
		Error:       cause.Error(), FailedAt: time.Now().UTC(),
	}
	payload, err := json.Marshal(message)
	if err != nil {
		return fmt.Errorf("encode dead-letter message: %w", err)
	}
	result := &kgo.Record{Topic: p.topic, Key: source.Key, Value: payload}
	if err := p.client.ProduceSync(ctx, result).FirstErr(); err != nil {
		return fmt.Errorf("publish to dead-letter topic %s: %w", p.topic, err)
	}
	return nil
}
