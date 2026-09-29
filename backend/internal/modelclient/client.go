package modelclient

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
)

const maxResponseBytes = 2 << 20

var ErrUnavailable = errors.New("model service is unavailable")

type PredictionRequest struct {
	ObjectID        int64    `json:"object_id"`
	PredictionTypes []string `json:"prediction_types,omitempty"`
}

func (r PredictionRequest) Validate() error {
	if r.ObjectID <= 0 {
		return fmt.Errorf("object_id must be positive")
	}
	seen := make(map[string]struct{}, len(r.PredictionTypes))
	for _, predictionType := range r.PredictionTypes {
		switch predictionType {
		case contracts.PredictionTypeFireRisk,
			contracts.PredictionTypeNSDEvent,
			contracts.PredictionTypeNSDRisk,
			contracts.PredictionTypeEquipment:
		default:
			return fmt.Errorf("invalid prediction_type %q", predictionType)
		}
		if _, exists := seen[predictionType]; exists {
			return fmt.Errorf("duplicate prediction_type %q", predictionType)
		}
		seen[predictionType] = struct{}{}
	}
	return nil
}

type PredictionResponse struct {
	Predictions []contracts.Prediction `json:"predictions"`
}

type Client struct {
	endpoint string
	http     *http.Client
}

func New(baseURL string, timeout time.Duration) (*Client, error) {
	parsed, err := url.Parse(strings.TrimRight(strings.TrimSpace(baseURL), "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("invalid model service URL %q", baseURL)
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return nil, fmt.Errorf("model service URL must use http or https")
	}
	if timeout <= 0 {
		return nil, fmt.Errorf("model request timeout must be positive")
	}
	return &Client{
		endpoint: parsed.String() + "/predict",
		http:     &http.Client{Timeout: timeout},
	}, nil
}

func (c *Client) Predict(ctx context.Context, request PredictionRequest) (PredictionResponse, error) {
	if err := request.Validate(); err != nil {
		return PredictionResponse{}, err
	}
	payload, err := json.Marshal(request)
	if err != nil {
		return PredictionResponse{}, fmt.Errorf("encode model request: %w", err)
	}
	httpRequest, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint, bytes.NewReader(payload))
	if err != nil {
		return PredictionResponse{}, fmt.Errorf("create model request: %w", err)
	}
	httpRequest.Header.Set("Content-Type", "application/json")
	httpResponse, err := c.http.Do(httpRequest)
	if err != nil {
		return PredictionResponse{}, fmt.Errorf("%w: %v", ErrUnavailable, err)
	}
	defer httpResponse.Body.Close()

	limited := io.LimitReader(httpResponse.Body, maxResponseBytes)
	if httpResponse.StatusCode < http.StatusOK || httpResponse.StatusCode >= http.StatusMultipleChoices {
		body, _ := io.ReadAll(limited)
		return PredictionResponse{}, fmt.Errorf(
			"%w: status %d: %s", ErrUnavailable, httpResponse.StatusCode, strings.TrimSpace(string(body)),
		)
	}
	var response PredictionResponse
	decoder := json.NewDecoder(limited)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&response); err != nil {
		return PredictionResponse{}, fmt.Errorf("decode model response: %w", err)
	}
	if len(response.Predictions) == 0 {
		return PredictionResponse{}, fmt.Errorf("model response contains no predictions")
	}
	for index := range response.Predictions {
		prediction := &response.Predictions[index]
		if prediction.ObjectID != request.ObjectID {
			return PredictionResponse{}, fmt.Errorf("model response object_id does not match request")
		}
		if err := prediction.Validate(); err != nil {
			return PredictionResponse{}, fmt.Errorf("validate model prediction: %w", err)
		}
	}
	return response, nil
}
