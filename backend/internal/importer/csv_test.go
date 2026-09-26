package importer

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestOpenCSVDetectsSemicolonAndBOM(t *testing.T) {
	path := filepath.Join(t.TempDir(), "objects.csv")
	content := "\ufeffид_объект;диспетчерское_название_объекта\n42;Тестовый объект\n"
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	table, err := openCSV(path)
	if err != nil {
		t.Fatal(err)
	}
	defer table.Close()
	if err := table.RequireHeaders(
		[]string{"ид_объект", "object_id"},
		[]string{"диспетчерское_название_объекта", "dispatcher_name"},
	); err != nil {
		t.Fatal(err)
	}
	record, err := table.Next()
	if err != nil {
		t.Fatal(err)
	}
	if value := table.Value(record, "ид_объект"); value != "42" {
		t.Fatalf("unexpected object ID %q", value)
	}
}

func TestParseTimestampUsesMoscowTime(t *testing.T) {
	parsed, err := parseTimestamp("19.10.2026", "12:15:00")
	if err != nil {
		t.Fatal(err)
	}
	want := time.Date(2026, 10, 19, 9, 15, 0, 0, time.UTC)
	if !parsed.Equal(want) {
		t.Fatalf("got %s, want %s", parsed, want)
	}
}

func TestParseBoolSupportsDatasetValues(t *testing.T) {
	for _, value := range []string{"t", "true", "1", "да"} {
		parsed, err := parseBool(value)
		if err != nil || !parsed {
			t.Fatalf("expected %q to be true, got %v, %v", value, parsed, err)
		}
	}
	for _, value := range []string{"f", "false", "0", "нет"} {
		parsed, err := parseBool(value)
		if err != nil || parsed {
			t.Fatalf("expected %q to be false, got %v, %v", value, parsed, err)
		}
	}
}
