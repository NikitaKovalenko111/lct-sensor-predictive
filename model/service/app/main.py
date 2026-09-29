import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select, func, update
from .config import settings, NSD_TRIGGER_TYPES, OPEN_VALUE
from .db import init_db, SessionLocal, SensorEventDB, PredictionLogDB, prune_old_events
from .feature_engine import FeatureEngine
from .predictor import Predictor
from .kafka_io import create_consumer, create_producer, publish_dead_letter, publish_prediction
from .schemas import PredictionRequest, PredictionResponse, SensorEvent, Prediction
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("model-service")

CASCADE_WINDOW = timedelta(minutes=10)   # окно каскада из обучения
IDLE_FLUSH_SEC = 15                      # flush отложенных триггеров при простое потока
ON_DEMAND_TYPES = ("fire_risk", "nsd_risk", "equipment_failure")

class ModelService:
    def __init__(self):
        self.fe = FeatureEngine()
        self.pr = Predictor()
        self.pending = []                 # (event_id, object_id, trigger_ts, sensor_type)
        self.touched = set()              # объекты для планового прогноза
        self.latest_ts = None             # event-time последнего события
        self.last_ingest_wall = datetime.utcnow()
        self.last_periodic = datetime.utcnow()
        self.last_prune = datetime.utcnow()
        self.producer = None
        self.ready = asyncio.Event()

    # ---------------- ingest ----------------
    def ingest(self, raw: dict):
        ev = SensorEvent(**raw)
        ts = ev.timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        is_nsd_trigger = (
            ev.is_alarm and ev.value == OPEN_VALUE
            and ev.sensor_type in NSD_TRIGGER_TYPES
        )
        queue_trigger = False
        queue_periodic = False
        with SessionLocal() as s:
            stored = s.scalar(select(SensorEventDB).where(
                SensorEventDB.event_id == ev.event_id))
            if stored is None:
                s.add(SensorEventDB(
                    event_id=ev.event_id, object_id=ev.object_id,
                    channel_id=ev.channel_id, sensor_type=ev.sensor_type,
                    engineering_system=ev.engineering_system, value=ev.value,
                    is_alarm=ev.is_alarm,
                    timestamp=ts,
                    nsd_due_at=ts + CASCADE_WINDOW if is_nsd_trigger else None,
                ))
                queue_trigger = is_nsd_trigger
                queue_periodic = True
            else:
                if is_nsd_trigger and stored.nsd_due_at is None:
                    stored.nsd_due_at = ts + CASCADE_WINDOW
                queue_trigger = is_nsd_trigger and stored.nsd_processed_at is None
                queue_periodic = stored.periodic_processed_at is None
            s.commit()
        self.latest_ts = ts if self.latest_ts is None else max(self.latest_ts, ts)
        self.last_ingest_wall = datetime.utcnow()
        if queue_periodic:
            self.touched.add(ev.object_id)

        # Триггер НСД: откладываем на 10 минут (нужен каскад открытий ПОСЛЕ)
        if queue_trigger and not any(item[0] == ev.event_id for item in self.pending):
            self.pending.append((ev.event_id, ev.object_id, ts, ev.sensor_type))
            log.info(f"NSD trigger: obj={ev.object_id} {ev.sensor_type} @ {ts}")

    def recover_work(self):
        with SessionLocal() as s:
            pending = s.scalars(
                select(SensorEventDB)
                .where(SensorEventDB.nsd_due_at.is_not(None))
                .where(SensorEventDB.nsd_processed_at.is_(None))
                .order_by(SensorEventDB.timestamp)
            ).all()
            self.pending = [
                (row.event_id, row.object_id, row.timestamp, row.sensor_type)
                for row in pending
            ]
            self.touched = set(s.scalars(
                select(SensorEventDB.object_id)
                .where(SensorEventDB.periodic_processed_at.is_(None))
                .distinct()
            ).all())
            self.latest_ts = s.scalar(select(func.max(SensorEventDB.timestamp)))
        log.info(
            "Recovered ML work: nsd=%d periodic_objects=%d",
            len(self.pending), len(self.touched),
        )

    # ---------------- цикл 1: классификатор НСД (событийный) ----------------
    async def sweep_triggers(self):
        now = datetime.utcnow()
        idle = (now - self.last_ingest_wall) > timedelta(seconds=IDLE_FLUSH_SEC)
        due = [t for t in self.pending
               if idle or (self.latest_ts and t[2] + CASCADE_WINDOW <= self.latest_ts)]
        if not due:
            return
        for event_id, obj, ts, stype in due:
            try:
                df = self.fe.load_events(obj, ts, lookback_days=40, forward_min=11)
                fdict = self.fe.nsd_event_features(df, ts, stype)
                pred = self.pr.nsd_event(obj, fdict)
                pred.prediction_id = uuid5(NAMESPACE_URL, f"nsd-event:{event_id}")
                await self.emit(pred, fdict)
                with SessionLocal() as s:
                    s.execute(
                        update(SensorEventDB)
                        .where(SensorEventDB.event_id == event_id)
                        .values(nsd_processed_at=datetime.utcnow())
                    )
                    s.commit()
                self.pending.remove((event_id, obj, ts, stype))
                log.info(f"NSD event pred: obj={obj} score={pred.risk_score:.3f} "
                         f"level={pred.risk_level} alert={pred.is_alert}")
            except Exception as e:
                log.error(f"nsd_event failed obj={obj}: {e}")

    # ---------------- цикл 2: плановые прогнозы (пожар + риск НСД) ----------------
    async def periodic_predictions(self):
        if not self.touched:
            return
        objs = list(self.touched)
        with SessionLocal() as s:
            rows = s.execute(
                select(SensorEventDB.object_id, func.max(SensorEventDB.timestamp))
                .where(SensorEventDB.object_id.in_(objs))
                .group_by(SensorEventDB.object_id)
            ).all()
        for obj, last_ts in rows:
            try:
                df = self.fe.load_events(obj, last_ts, lookback_days=40, forward_min=0)
                fire = self.pr.fire_risk(obj, self.fe.fire_features(df, last_ts))
                risk = self.pr.nsd_risk(obj, self.fe.nsd_risk_features(df, last_ts.date()))
                fault = self.pr.fault_risk(obj, self.fe.fault_features(df, last_ts.date()))
                for prediction in (fault, fire, risk):
                    prediction.prediction_id = uuid5(
                        NAMESPACE_URL,
                        f"periodic:{obj}:{last_ts.isoformat()}:{prediction.prediction_type}",
                    )
                await self.emit(fault)
                await self.emit(fire)
                await self.emit(risk)
                with SessionLocal() as s:
                    s.execute(
                        update(SensorEventDB)
                        .where(SensorEventDB.object_id == obj)
                        .where(SensorEventDB.timestamp <= last_ts)
                        .values(periodic_processed_at=datetime.utcnow())
                    )
                    s.commit()
                self.touched.discard(obj)
                log.info(f"Periodic: obj={obj} fire={fire.risk_score:.3f} "
                         f"nsd_risk={risk.risk_score:.3f} fault={fault.risk_score:.3f}")
            except Exception as e:
                log.error(f"periodic failed obj={obj}: {e}")

    # ---------------- emit + лог ----------------
    async def emit(self, pred: Prediction, fdict: dict | None = None):
        if self.producer is None:
            raise RuntimeError("Kafka producer is not ready")
        with SessionLocal() as s:
            exists = s.scalar(select(PredictionLogDB.id).where(
                PredictionLogDB.prediction_id == str(pred.prediction_id)))
            if exists is None:
                s.add(PredictionLogDB(
                    prediction_id=str(pred.prediction_id),
                    schema_version=pred.schema_version,
                    object_id=pred.object_id, prediction_type=pred.prediction_type,
                    risk_score=pred.risk_score, risk_level=pred.risk_level,
                    is_alert=pred.is_alert,
                    features_json=json.dumps(fdict or pred.features_used, default=str),
                    model_version=pred.model_version,
                    predicted_at=pred.predicted_at,
                ))
            s.commit()
        try:
            await publish_prediction(self.producer, pred)
        except Exception as error:
            log.error("prediction queued for retry: %s", error)
            return
        with SessionLocal() as s:
            row = s.scalar(select(PredictionLogDB).where(
                PredictionLogDB.prediction_id == str(pred.prediction_id)))
            if row is not None:
                row.published_at = datetime.utcnow()
                s.commit()

    async def flush_prediction_outbox(self):
        if self.producer is None:
            return
        with SessionLocal() as s:
            rows = s.scalars(
                select(PredictionLogDB)
                .where(PredictionLogDB.published_at.is_(None))
                .where(PredictionLogDB.prediction_id.is_not(None))
                .order_by(PredictionLogDB.id)
                .limit(100)
            ).all()
        for row in rows:
            prediction = Prediction(
                schema_version=row.schema_version,
                prediction_id=row.prediction_id,
                object_id=row.object_id,
                prediction_type=row.prediction_type,
                risk_score=row.risk_score,
                risk_level=row.risk_level,
                is_alert=row.is_alert,
                predicted_at=row.predicted_at.replace(tzinfo=timezone.utc),
                features_used=json.loads(row.features_json or "{}"),
                model_version=row.model_version,
            )
            try:
                await publish_prediction(self.producer, prediction)
            except Exception as error:
                log.error("prediction outbox publish failed: %s", error)
                return
            with SessionLocal() as s:
                stored = s.get(PredictionLogDB, row.id)
                if stored is not None:
                    stored.published_at = datetime.utcnow()
                    s.commit()

    async def predict_on_demand(self, request: PredictionRequest) -> PredictionResponse:
        with SessionLocal() as s:
            last_ts = s.scalar(
                select(func.max(SensorEventDB.timestamp))
                .where(SensorEventDB.object_id == request.object_id)
            )
        if last_ts is None:
            last_ts = datetime.utcnow()
            log.warning(
                "No telemetry found for object %s; using an empty baseline",
                request.object_id,
            )

        df = self.fe.load_events(request.object_id, last_ts, lookback_days=40, forward_min=0)
        requested = request.prediction_types or list(ON_DEMAND_TYPES)
        predictions = []
        for prediction_type in requested:
            if prediction_type == "fire_risk":
                prediction = self.pr.fire_risk(
                    request.object_id, self.fe.fire_features(df, last_ts))
            elif prediction_type == "nsd_risk":
                prediction = self.pr.nsd_risk(
                    request.object_id, self.fe.nsd_risk_features(df, last_ts.date()))
            elif prediction_type == "equipment_failure":
                prediction = self.pr.fault_risk(
                    request.object_id, self.fe.fault_features(df, last_ts.date()))
            else:
                triggers = df[
                    df["is_alarm"]
                    & df["sensor_type"].isin(NSD_TRIGGER_TYPES)
                    & (df["value"] == OPEN_VALUE)
                ]
                if triggers.empty:
                    raise ValueError("nsd_event requires an opening trigger in object history")
                trigger = triggers.sort_values("ts").iloc[-1]
                features = self.fe.nsd_event_features(
                    df, trigger["ts"], trigger["sensor_type"])
                prediction = self.pr.nsd_event(request.object_id, features)
            await self.emit(prediction)
            predictions.append(prediction)
        return PredictionResponse(predictions=predictions)

    # ---------------- главный цикл ----------------
    async def run(self):
        consumer = None
        sweeper_task = None
        try:
            init_db()
            self.recover_work()
            consumer = await create_consumer()
            self.producer = await create_producer()
            self.ready.set()
            log.info("Model service started")

            async def sweeper():
                while True:
                    await asyncio.sleep(5)
                    await self.flush_prediction_outbox()
                    await self.sweep_triggers()
                    now = datetime.utcnow()
                    if now - self.last_periodic >= timedelta(seconds=settings.prediction_interval):
                        self.last_periodic = now
                        await self.periodic_predictions()
                    if now - self.last_prune > timedelta(days=1):
                        self.last_prune = now
                        prune_old_events(45)
                        log.info("Pruned ml.events older than 45 days")

            sweeper_task = asyncio.create_task(sweeper())
            def sweeper_finished(task):
                if task.cancelled():
                    return
                self.ready.clear()
                error = task.exception()
                if error is not None:
                    log.error("prediction sweeper failed", exc_info=(
                        type(error), error, error.__traceback__))

            sweeper_task.add_done_callback(sweeper_finished)
            async for msg in consumer:
                if not self.ready.is_set():
                    raise RuntimeError("prediction sweeper is not running")
                try:
                    raw = json.loads(msg.value.decode("utf-8"))
                except Exception as e:
                    log.error(f"decode sensor event failed: {e}")
                    await publish_dead_letter(self.producer, msg, e)
                    await consumer.commit()
                    continue
                while self.ready.is_set():
                    try:
                        self.ingest(raw)
                        await consumer.commit()
                        break
                    except Exception as e:
                        log.error(f"ingest failed; retrying: {e}")
                        await asyncio.sleep(1)
        finally:
            self.ready.clear()
            if sweeper_task is not None:
                sweeper_task.cancel()
                await asyncio.gather(sweeper_task, return_exceptions=True)
            if consumer is not None:
                await consumer.stop()
            if self.producer is not None:
                await self.producer.stop()
                self.producer = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    service = ModelService()
    task = asyncio.create_task(service.run())

    def log_service_exit(completed_task: asyncio.Task):
        if completed_task.cancelled():
            log.info("Model service task stopped")
            return
        error = completed_task.exception()
        if error is None:
            log.error("Model service task exited unexpectedly")
            return
        log.error(
            "Model service task failed",
            exc_info=(type(error), error, error.__traceback__),
        )

    task.add_done_callback(log_service_exit)
    ready_task = asyncio.create_task(service.ready.wait())
    try:
        done, _ = await asyncio.wait(
            {task, ready_task}, timeout=30, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            await task
        if ready_task not in done:
            raise TimeoutError("model service startup timed out")
        app.state.model_service = service
        yield
    finally:
        ready_task.cancel()
        task.cancel()
        await asyncio.gather(ready_task, task, return_exceptions=True)

app = FastAPI(title="Sensor Predictive Model Service", lifespan=lifespan)

@app.get("/health/live")
async def live():
    return {"status": "ok"}

@app.get("/health/ready")
async def ready(request: Request):
    service: ModelService = request.app.state.model_service
    if not service.ready.is_set():
        raise HTTPException(status_code=503, detail="model service is not ready")
    return {"status": "ready"}

@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: PredictionRequest, request: Request):
    service: ModelService = request.app.state.model_service
    try:
        return await service.predict_on_demand(payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
