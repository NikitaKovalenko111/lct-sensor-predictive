package channels

import "fmt"

type Channel struct {
	ChannelID            string `json:"channel_id"`
	ObjectID             int64  `json:"object_id"`
	SensorType           string `json:"sensor_type"`
	EngineeringSystem    string `json:"engineering_system"`
	EngineeringSystemTag string `json:"engineering_system_tag"`
	SensorName           string `json:"sensor_name"`
}

func (c Channel) Validate() error {
	if c.ChannelID == "" {
		return fmt.Errorf("channel_id is required")
	}
	if c.ObjectID <= 0 {
		return fmt.Errorf("object_id must be positive")
	}
	if c.SensorType == "" {
		return fmt.Errorf("sensor_type is required")
	}
	return nil
}

type EventMetadata struct {
	ObjectID          int64
	SensorType        string
	EngineeringSystem string
}
