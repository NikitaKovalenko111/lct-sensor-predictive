package importer

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"path/filepath"
	"time"

	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/channels"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/contracts"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/importjob"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/objects"
	"github.com/NikitaKovalenko111/lct-sensor-predictive/backend/internal/telemetry"
)

const defaultBatchSize = 500

type Service struct {
	objects   *objects.Repository
	channels  *channels.Repository
	jobs      *importjob.Repository
	publisher *telemetry.Publisher
	events    *telemetry.Repository
	logger    *slog.Logger
	batchSize int
}

func NewService(
	objectRepository *objects.Repository,
	channelRepository *channels.Repository,
	jobRepository *importjob.Repository,
	publisher *telemetry.Publisher,
	eventRepository *telemetry.Repository,
	logger *slog.Logger,
	batchSize int,
) *Service {
	if batchSize <= 0 {
		batchSize = defaultBatchSize
	}
	return &Service{
		objects: objectRepository, channels: channelRepository, jobs: jobRepository,
		publisher: publisher, events: eventRepository, logger: logger, batchSize: batchSize,
	}
}

type Result struct {
	ImportID  string
	Processed int64
	Failed    int64
}

func (s *Service) ImportObjects(ctx context.Context, path string) (result Result, returnErr error) {
	jobID, err := s.jobs.Start(ctx, "objects", filepath.Base(path), path)
	if err != nil {
		return Result{}, err
	}
	result.ImportID = jobID
	defer s.finishJob(ctx, &result, &returnErr)

	table, err := openCSV(path)
	if err != nil {
		return result, err
	}
	defer table.Close()
	if err := table.RequireHeaders(
		[]string{"ид_объект", "object_id"},
		[]string{"диспетчерское_название_объекта", "dispatcher_name"},
	); err != nil {
		return result, err
	}

	batch := make([]objects.Object, 0, s.batchSize)
	parents := make([]objects.Object, 0)
	for {
		record, err := table.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return result, fmt.Errorf("read objects row %d: %w", table.row+1, err)
		}
		item, err := parseObject(table, record)
		if err != nil {
			result.Failed++
			s.logRejectedRow("objects", table.row, err)
			continue
		}
		batch = append(batch, item)
		parents = append(parents, item)
		if len(batch) >= s.batchSize {
			if err := s.objects.UpsertBatch(ctx, batch); err != nil {
				return result, err
			}
			result.Processed += int64(len(batch))
			batch = batch[:0]
			s.reportProgress(ctx, result)
		}
	}
	if err := s.objects.UpsertBatch(ctx, batch); err != nil {
		return result, err
	}
	result.Processed += int64(len(batch))
	if err := s.objects.SetParents(ctx, parents); err != nil {
		return result, err
	}
	return result, nil
}

func (s *Service) ImportChannels(ctx context.Context, path string) (result Result, returnErr error) {
	jobID, err := s.jobs.Start(ctx, "channels", filepath.Base(path), path)
	if err != nil {
		return Result{}, err
	}
	result.ImportID = jobID
	defer s.finishJob(ctx, &result, &returnErr)

	table, err := openCSV(path)
	if err != nil {
		return result, err
	}
	defer table.Close()
	if err := table.RequireHeaders(
		[]string{"ид_канала_данных", "channel_id"},
		[]string{"ид_объект", "object_id"},
		[]string{"тип_датчика", "sensor_type"},
	); err != nil {
		return result, err
	}

	batch := make([]channels.Channel, 0, s.batchSize)
	for {
		record, err := table.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return result, fmt.Errorf("read channels row %d: %w", table.row+1, err)
		}
		item, err := parseChannel(table, record)
		if err != nil {
			result.Failed++
			s.logRejectedRow("channels", table.row, err)
			continue
		}
		batch = append(batch, item)
		if len(batch) >= s.batchSize {
			if err := s.channels.UpsertBatch(ctx, batch); err != nil {
				return result, err
			}
			result.Processed += int64(len(batch))
			batch = batch[:0]
			s.reportProgress(ctx, result)
		}
	}
	if err := s.channels.UpsertBatch(ctx, batch); err != nil {
		return result, err
	}
	result.Processed += int64(len(batch))
	return result, nil
}

func (s *Service) ImportEvents(ctx context.Context, path string, lookback time.Duration) (result Result, returnErr error) {
	jobID, err := s.jobs.Start(ctx, "events", filepath.Base(path), path)
	if err != nil {
		return Result{}, err
	}
	result.ImportID = jobID
	defer s.finishJob(ctx, &result, &returnErr)

	if lookback < 0 {
		return result, fmt.Errorf("events lookback must not be negative")
	}
	var cutoff time.Time
	if lookback > 0 {
		latest, err := latestEventTimestamp(path)
		if err != nil {
			return result, err
		}
		cutoff = latest.Add(-lookback)
		s.logger.Info("filter historical events", "latest", latest, "cutoff", cutoff, "lookback", lookback)
	}

	lookup, err := s.channels.EventLookup(ctx)
	if err != nil {
		return result, err
	}
	if len(lookup) == 0 {
		return result, fmt.Errorf("channel registry is empty; import channels before events")
	}
	table, err := openCSV(path)
	if err != nil {
		return result, err
	}
	defer table.Close()
	if err := table.RequireHeaders(
		[]string{"ид_события", "event_id"},
		[]string{"ид_канала_данных", "channel_id"},
		[]string{"дата", "date"},
		[]string{"время", "time"},
		[]string{"тревожное", "is_alarm"},
		[]string{"значение_датчика", "value"},
	); err != nil {
		return result, err
	}

	batch := make([]contracts.SensorEvent, 0, s.batchSize)
	for {
		record, err := table.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return result, fmt.Errorf("read events row %d: %w", table.row+1, err)
		}
		event, err := parseEvent(table, record, lookup)
		if err != nil {
			result.Failed++
			s.logRejectedRow("events", table.row, err)
			continue
		}
		if !cutoff.IsZero() && event.Timestamp.Before(cutoff) {
			continue
		}
		batch = append(batch, event)
		if len(batch) >= s.batchSize {
			if err := s.persistAndPublishEvents(ctx, batch); err != nil {
				return result, err
			}
			result.Processed += int64(len(batch))
			batch = batch[:0]
			s.reportProgress(ctx, result)
		}
	}
	if err := s.persistAndPublishEvents(ctx, batch); err != nil {
		return result, err
	}
	result.Processed += int64(len(batch))
	return result, nil
}

func (s *Service) persistAndPublishEvents(ctx context.Context, events []contracts.SensorEvent) error {
	inserted, err := s.events.UpsertBatch(ctx, events)
	if err != nil {
		return err
	}
	return s.publisher.PublishBatch(ctx, inserted)
}

func latestEventTimestamp(path string) (time.Time, error) {
	table, err := openCSV(path)
	if err != nil {
		return time.Time{}, err
	}
	defer table.Close()
	if err := table.RequireHeaders(
		[]string{"дата", "date"},
		[]string{"время", "time"},
	); err != nil {
		return time.Time{}, err
	}

	var latest time.Time
	for {
		record, err := table.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return time.Time{}, fmt.Errorf("read events row %d: %w", table.row+1, err)
		}
		timestamp, err := parseTimestamp(
			table.Value(record, "дата", "date"),
			table.Value(record, "время", "time"),
		)
		if err == nil && timestamp.After(latest) {
			latest = timestamp
		}
	}
	if latest.IsZero() {
		return time.Time{}, fmt.Errorf("events CSV has no valid timestamps")
	}
	return latest, nil
}

func parseObject(table *csvTable, record []string) (objects.Object, error) {
	objectID, err := parseInt64(table.Value(record, "ид_объект", "object_id"))
	if err != nil || objectID <= 0 {
		return objects.Object{}, fmt.Errorf("invalid object id")
	}
	level := 0
	if value := table.Value(record, "иерархия_уровень", "hierarchy_level"); value != "" {
		if level, err = parseInt(value); err != nil {
			return objects.Object{}, fmt.Errorf("invalid hierarchy level: %w", err)
		}
	}
	var parentID *int64
	if value := table.Value(record, "родитель", "parent_id"); value != "" {
		parsed, err := parseInt64(value)
		if err == nil && parsed > 0 && parsed != objectID {
			parentID = &parsed
		}
	}
	name := table.Value(record, "диспетчерское_название_объекта", "dispatcher_name")
	if name == "" {
		name = fmt.Sprintf("Object %d", objectID)
	}
	return objects.Object{
		ObjectID: objectID, ParentID: parentID, HierarchyLevel: level,
		ObjectType:     table.Value(record, "вид_объекта", "object_type"),
		DispatcherName: name, Geometry: objects.SyntheticGeometry(objectID),
	}, nil
}

func parseChannel(table *csvTable, record []string) (channels.Channel, error) {
	objectID, err := parseInt64(table.Value(record, "ид_объект", "object_id"))
	if err != nil || objectID <= 0 {
		return channels.Channel{}, fmt.Errorf("invalid object id")
	}
	item := channels.Channel{
		ChannelID:            table.Value(record, "ид_канала_данных", "channel_id"),
		ObjectID:             objectID,
		SensorType:           table.Value(record, "тип_датчика", "sensor_type"),
		EngineeringSystem:    table.Value(record, "тип_инж_системы", "engineering_system"),
		EngineeringSystemTag: table.Value(record, "тег_инженерной_системы", "engineering_system_tag"),
		SensorName:           table.Value(record, "название_датчика", "sensor_name"),
	}
	if err := item.Validate(); err != nil {
		return channels.Channel{}, err
	}
	return item, nil
}

func parseEvent(table *csvTable, record []string, lookup map[string]channels.EventMetadata) (contracts.SensorEvent, error) {
	channelID := table.Value(record, "ид_канала_данных", "channel_id")
	metadata, exists := lookup[channelID]
	if !exists {
		return contracts.SensorEvent{}, fmt.Errorf("unknown channel_id %q", channelID)
	}
	timestamp, err := parseTimestamp(
		table.Value(record, "дата", "date"),
		table.Value(record, "время", "time"),
	)
	if err != nil {
		return contracts.SensorEvent{}, err
	}
	isAlarm, err := parseBool(table.Value(record, "тревожное", "is_alarm"))
	if err != nil {
		return contracts.SensorEvent{}, err
	}
	event := contracts.SensorEvent{
		SchemaVersion:     contracts.SchemaVersion,
		EventID:           table.Value(record, "ид_события", "event_id"),
		ObjectID:          metadata.ObjectID,
		ChannelID:         channelID,
		SensorType:        metadata.SensorType,
		EngineeringSystem: metadata.EngineeringSystem,
		Value:             table.Value(record, "значение_датчика", "value"),
		IsAlarm:           isAlarm,
		Timestamp:         timestamp,
	}
	if err := event.Validate(); err != nil {
		return contracts.SensorEvent{}, err
	}
	return event, nil
}

func (s *Service) reportProgress(ctx context.Context, result Result) {
	if err := s.jobs.Progress(ctx, result.ImportID, result.Processed, result.Failed); err != nil {
		s.logger.Warn("update import progress", "import_id", result.ImportID, "error", err)
	}
	s.logger.Info("import progress", "import_id", result.ImportID, "processed", result.Processed, "failed", result.Failed)
}

func (s *Service) finishJob(ctx context.Context, result *Result, returnErr *error) {
	if *returnErr != nil {
		if err := s.jobs.Fail(context.WithoutCancel(ctx), result.ImportID, result.Processed, result.Failed, *returnErr); err != nil {
			s.logger.Error("mark import failed", "import_id", result.ImportID, "error", err)
		}
		return
	}
	if err := s.jobs.Complete(context.WithoutCancel(ctx), result.ImportID, result.Processed, result.Failed); err != nil {
		*returnErr = err
	}
}

func (s *Service) logRejectedRow(kind string, row int64, err error) {
	// Avoid producing millions of log lines for known dirty historical data.
	if row <= 20 || row%10_000 == 0 {
		s.logger.Warn("CSV row rejected", "kind", kind, "row", row, "error", err)
	}
}
