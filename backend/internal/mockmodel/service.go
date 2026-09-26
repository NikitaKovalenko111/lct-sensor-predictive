package mockmodel

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/twmb/franz-go/pkg/kgo"
)

type Service struct {
	consumer    *kgo.Client
	producer    *kgo.Client
	outputTopic string
	logger      *slog.Logger
}

func New(consumer, producer *kgo.Client, outputTopic string, logger *slog.Logger) *Service {
	return &Service{consumer: consumer, producer: producer, outputTopic: outputTopic, logger: logger}
}

func (s *Service) Run(ctx context.Context) error {
	for {
		fetches := s.consumer.PollFetches(ctx)
		if ctx.Err() != nil {
			return nil
		}
		if errs := fetches.Errors(); len(errs) > 0 {
			for _, fetchErr := range errs {
				s.logger.Error("mock model fetch failed", "error", fetchErr.Err)
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
				batchErr = fmt.Errorf("decode sensor event: %w", err)
				return
			}
			prediction := makePrediction(event)
			payload, err := json.Marshal(prediction)
			if err != nil {
				batchErr = fmt.Errorf("encode prediction: %w", err)
				return
			}
			result := &kgo.Record{
				Topic: s.outputTopic,
				Key:   []byte(strconv.FormatInt(event.ObjectID, 10)),
				Value: payload,
			}
			if err := s.producer.ProduceSync(ctx, result).FirstErr(); err != nil {
				batchErr = fmt.Errorf("publish mock prediction: %w", err)
			}
		})
		if batchErr != nil {
			s.logger.Error("mock model batch failed", "error", batchErr)
			continue
		}
		if err := s.consumer.CommitRecords(ctx, fetches.Records()...); err != nil {
			s.logger.Error("commit mock model offsets", "error", err)
		}
	}
}

func makePrediction(event contracts.SensorEvent) contracts.Prediction {
	digest := sha256.Sum256([]byte(event.EventID))
	baseScore := float64(int(digest[0])) / 255.0 * 0.35
	if event.IsAlarm {
		baseScore += 0.5
	}
	if baseScore > 1 {
		baseScore = 1
	}

	predictionType := contracts.PredictionTypeNSDRisk
	sensorType := strings.ToLower(event.SensorType)
	if strings.Contains(sensorType, "smoke") || strings.Contains(sensorType, "temperature") || strings.Contains(sensorType, "дым") || strings.Contains(sensorType, "температур") {
		predictionType = contracts.PredictionTypeFireRisk
	} else if strings.Contains(sensorType, "movement") || strings.Contains(sensorType, "contact") || strings.Contains(sensorType, "движ") || strings.Contains(sensorType, "контакт") {
		predictionType = contracts.PredictionTypeNSDEvent
	}

	features, _ := json.Marshal(map[string]any{
		"mock":        true,
		"event_id":    event.EventID,
		"sensor_type": event.SensorType,
		"is_alarm":    event.IsAlarm,
	})
	return contracts.Prediction{
		SchemaVersion:  contracts.SchemaVersion,
		ObjectID:       event.ObjectID,
		PredictionType: predictionType,
		RiskScore:      baseScore,
		RiskLevel:      riskLevel(baseScore),
		PredictedAt:    time.Now().UTC(),
		FeaturesUsed:   features,
		ModelVersion:   "mock-v1.0",
	}
}

func riskLevel(score float64) string {
	switch {
	case score >= 0.85:
		return "critical"
	case score >= 0.65:
		return "high"
	case score >= 0.35:
		return "medium"
	default:
		return "low"
	}
}
