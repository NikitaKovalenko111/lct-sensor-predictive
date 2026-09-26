package importer

import (
	"bufio"
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"time"
)

type csvTable struct {
	file    *os.File
	reader  *csv.Reader
	headers map[string]int
	row     int64
}

func openCSV(path string) (*csvTable, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open CSV %q: %w", path, err)
	}
	buffered := bufio.NewReaderSize(file, 256*1024)
	firstLine, err := buffered.ReadString('\n')
	if err != nil && err != io.EOF {
		file.Close()
		return nil, fmt.Errorf("read CSV header: %w", err)
	}
	if strings.TrimSpace(firstLine) == "" {
		file.Close()
		return nil, fmt.Errorf("CSV %q has an empty header", path)
	}

	reader := csv.NewReader(io.MultiReader(strings.NewReader(firstLine), buffered))
	reader.Comma = detectDelimiter(firstLine)
	reader.FieldsPerRecord = -1
	reader.ReuseRecord = false
	reader.TrimLeadingSpace = true
	reader.LazyQuotes = true
	header, err := reader.Read()
	if err != nil {
		file.Close()
		return nil, fmt.Errorf("parse CSV header: %w", err)
	}
	headers := make(map[string]int, len(header))
	for index, name := range header {
		headers[normalizeHeader(name)] = index
	}
	return &csvTable{file: file, reader: reader, headers: headers, row: 1}, nil
}

func (t *csvTable) Close() error {
	return t.file.Close()
}

func (t *csvTable) Next() ([]string, error) {
	record, err := t.reader.Read()
	if err != nil {
		return nil, err
	}
	t.row++
	return record, nil
}

func (t *csvTable) Value(record []string, aliases ...string) string {
	for _, alias := range aliases {
		index, exists := t.headers[normalizeHeader(alias)]
		if exists && index < len(record) {
			return strings.TrimSpace(record[index])
		}
	}
	return ""
}

func (t *csvTable) RequireHeaders(groups ...[]string) error {
	for _, aliases := range groups {
		found := false
		for _, alias := range aliases {
			if _, exists := t.headers[normalizeHeader(alias)]; exists {
				found = true
				break
			}
		}
		if !found {
			return fmt.Errorf("CSV is missing required column %q", aliases[0])
		}
	}
	return nil
}

func detectDelimiter(line string) rune {
	candidates := []rune{',', ';', '\t'}
	best := candidates[0]
	bestCount := -1
	for _, candidate := range candidates {
		if count := strings.Count(line, string(candidate)); count > bestCount {
			best = candidate
			bestCount = count
		}
	}
	return best
}

func normalizeHeader(value string) string {
	value = strings.TrimPrefix(value, "\ufeff")
	value = strings.ToLower(strings.TrimSpace(value))
	value = strings.ReplaceAll(value, " ", "_")
	return value
}

func parseInt64(value string) (int64, error) {
	value = strings.ReplaceAll(strings.TrimSpace(value), " ", "")
	value = strings.ReplaceAll(value, "\u00a0", "")
	return strconv.ParseInt(value, 10, 64)
}

func parseInt(value string) (int, error) {
	parsed, err := parseInt64(value)
	return int(parsed), err
}

func parseBool(value string) (bool, error) {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "true", "t", "1", "yes", "y", "да":
		return true, nil
	case "false", "f", "0", "no", "n", "нет":
		return false, nil
	default:
		return false, fmt.Errorf("unsupported boolean %q", value)
	}
}

func parseTimestamp(dateValue, timeValue string) (time.Time, error) {
	location, err := time.LoadLocation("Europe/Moscow")
	if err != nil {
		location = time.FixedZone("MSK", 3*60*60)
	}
	joined := strings.TrimSpace(dateValue + " " + timeValue)
	layouts := []string{
		"2006-01-02 15:04:05.999999999",
		"2006-01-02 15:04:05",
		"2006-01-02 15:04",
		"02.01.2006 15:04:05.999999999",
		"02.01.2006 15:04:05",
		"02.01.2006 15:04",
	}
	for _, layout := range layouts {
		if parsed, err := time.ParseInLocation(layout, joined, location); err == nil {
			return parsed.UTC(), nil
		}
	}
	return time.Time{}, fmt.Errorf("unsupported date/time %q", joined)
}
