package objects

import (
	"encoding/json"
	"hash/fnv"
)

type geoJSONGeometry struct {
	Type        string        `json:"type"`
	Coordinates [][][]float64 `json:"coordinates"`
}

// SyntheticGeometry returns a deterministic schematic line. Coordinates are
// deliberately synthetic and must not be represented as real collector locations.
func SyntheticGeometry(objectID int64) json.RawMessage {
	hasher := fnv.New64a()
	_, _ = hasher.Write([]byte(stringID(objectID)))
	value := hasher.Sum64()

	startX := 37.45 + float64(value%3000)/10000
	startY := 55.62 + float64((value/3000)%2200)/10000
	length := 0.004 + float64((value/6600000)%80)/10000
	geometry := geoJSONGeometry{
		Type: "MultiLineString",
		Coordinates: [][][]float64{{
			{startX, startY},
			{startX + length, startY + length/3},
		}},
	}
	payload, _ := json.Marshal(geometry)
	return payload
}

func stringID(value int64) string {
	if value == 0 {
		return "0"
	}
	var buffer [20]byte
	position := len(buffer)
	for value > 0 {
		position--
		buffer[position] = byte('0' + value%10)
		value /= 10
	}
	return string(buffer[position:])
}
