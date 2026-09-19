package objects

import (
	"encoding/json"
	"testing"
)

func TestSyntheticGeometryIsDeterministicGeoJSON(t *testing.T) {
	first := SyntheticGeometry(42)
	second := SyntheticGeometry(42)
	if string(first) != string(second) {
		t.Fatal("synthetic geometry is not deterministic")
	}
	var geometry map[string]any
	if err := json.Unmarshal(first, &geometry); err != nil {
		t.Fatalf("invalid GeoJSON: %v", err)
	}
	if geometry["type"] != "MultiLineString" {
		t.Fatalf("unexpected geometry type %v", geometry["type"])
	}
}
