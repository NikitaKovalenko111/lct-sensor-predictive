import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select, func
from .config import settings, NSD_TRIGGER_TYPES, OPEN_VALUE
from .db import init_db, SessionLocal, SensorEventDB, PredictionLogDB, prune_old_events
from .feature_engine import FeatureEngine
from .predictor import Predictor
from .kafka_io import create_consumer, create_producer, publish_prediction
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
        self.pending = []                 # (object_id, trigger_ts, sensor_type)
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
        with SessionLocal() as s:
            if not s.query(SensorEventDB.id).filter_by(event_id=ev.event_id).first():
                s.add(SensorEventDB(
                    event_id=ev.event_id, object_id=ev.object_id,
                    channel_id=ev.channel_id, sensor_type=ev.sensor_type,
                    engineering_system=ev.engineering_system, value=ev.value,
                    is_alarm=ev.is_alarm, timestamp=ev.timestamp.replace(tzinfo=None),
                ))
                s.commit()
        ts = ev.timestamp.replace(tzinfo=None)
        self.latest_ts = ts if self.latest_ts is None else max(self.latest_ts, ts)
        self.last_ingest_wall = datetime.utcnow()
        self.touched.add(ev.object_id)

        # Триггер НСД: откладываем на 10 минут (нужен каскад открытий ПОСЛЕ)
        if (ev.is_alarm and ev.value == OPEN_VALUE
                and ev.sensor_type in NSD_TRIGGER_TYPES):
            self.pending.append((ev.object_id, ts, ev.sensor_type))
            log.info(f"NSD trigger: obj={ev.object_id} {ev.sensor_type} @ {ts}")

    # ---------------- цикл 1: классификатор НСД (событийный) ----------------
    async def sweep_triggers(self):
        now = datetime.utcnow()
        idle = (now - self.last_ingest_wall) > timedelta(seconds=IDLE_FLUSH_SEC)
        due = [t for t in self.pending
               if idle or (self.latest_ts and t[1] + CASCADE_WINDOW <= self.latest_ts)]
        if not due:
            return
        for obj, ts, stype in due:
            self.pending.remove((obj, ts, stype))
            try:
                df = self.fe.load_events(obj, ts, lookback_days=40, forward_min=11)
                fdict = self.fe.nsd_event_features(df, ts, stype)
                pred = self.pr.nsd_event(obj, fdict)
                await self.emit(pred, fdict)
                log.info(f"NSD event pred: obj={obj} score={pred.risk_score:.3f} "
                         f"level={pred.risk_level} alert={pred.is_alert}")
            except Exception as e:
                log.error(f"nsd_event failed obj={obj}: {e}")

    # ---------------- цикл 2: плановые прогнозы (пожар + риск НСД) ----------------
    async def periodic_predictions(self):
        if not self.touched:
            return
        objs = list(self.touched)
        self.touched.clear()
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
                await self.emit(fault)
                await self.emit(fire)
                await self.emit(risk)
                log.info(f"Periodic: obj={obj} fire={fire.risk_score:.3f} "
                         f"nsd_risk={risk.risk_score:.3f} fault={fault.risk_score:.3f}")
            except Exception as e:
                log.error(f"periodic failed obj={obj}: {e}")

    # ---------------- emit + лог ----------------
    async def emit(self, pred: Prediction, fdict: dict | None = None):
        if self.producer is None:
            raise RuntimeError("Kafka producer is not ready")
        await publish_prediction(self.producer, pred)
        import json as _json
        with SessionLocal() as s:
            s.add(PredictionLogDB(
                object_id=pred.object_id, prediction_type=pred.prediction_type,
                risk_score=pred.risk_score, risk_level=pred.risk_level,
                is_alert=pred.is_alert,
                features_json=_json.dumps(fdict or pred.features_used, default=str),
                predicted_at=pred.predicted_at,
            ))
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
            consumer = await create_consumer()
            self.producer = await create_producer()
            self.ready.set()
            log.info("Model service started")

            async def sweeper():
                while True:
                    await asyncio.sleep(5)
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
            async for msg in consumer:
                try:
                    self.ingest(msg.value)
                except Exception as e:
                    log.error(f"ingest failed: {e}")
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
