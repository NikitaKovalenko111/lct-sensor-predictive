package objects

import (
	"encoding/json"
	"fmt"
)

type Object struct {
	ObjectID       int64           `json:"object_id"`
	ParentID       *int64          `json:"parent_id,omitempty"`
	HierarchyLevel int             `json:"hierarchy_level"`
	ObjectType     string          `json:"object_type"`
	DispatcherName string          `json:"dispatcher_name"`
	Geometry       json.RawMessage `json:"geometry,omitempty"`
}

func (o Object) Validate() error {
	if o.ObjectID <= 0 {
		return fmt.Errorf("object_id must be positive")
	}
	if o.DispatcherName == "" {
		return fmt.Errorf("dispatcher_name is required")
	}
	return nil
}

type ListFilter struct {
	ParentID   int64
	ObjectType string
	Search     string
	Limit      int
	Offset     int
}
