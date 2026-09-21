import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func, delete
from .config import settings, NSD_TRIGGER_TYPES, OPEN_VALUE
from .db import init_db, SessionLocal, SensorEventDB, PredictionLogDB, prune_old_events
from .feature_engine import FeatureEngine
from .predictor import Predictor
from .kafka_io import create_consumer, create_producer
from .schemas import SensorEvent, Prediction
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("model-service")

CASCADE_WINDOW = timedelta(minutes=10)   # окно каскада из обучения
IDLE_FLUSH_SEC = 15                      # flush отложенных триггеров при простое потока

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
    async def sweep_triggers(self, producer):
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
                await self.emit(producer, pred, fdict)
                log.info(f"NSD event pred: obj={obj} score={pred.risk_score:.3f} "
                         f"level={pred.risk_level} alert={pred.is_alert}")
            except Exception as e:
                log.error(f"nsd_event failed obj={obj}: {e}")

    # ---------------- цикл 2: плановые прогнозы (пожар + риск НСД) ----------------
    async def periodic_predictions(self, producer):
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
                await self.emit(producer, fire)
                await self.emit(producer, risk)
                log.info(f"Periodic: obj={obj} fire={fire.risk_score:.3f} "
                         f"nsd_risk={risk.risk_score:.3f}")
            except Exception as e:
                log.error(f"periodic failed obj={obj}: {e}")

    # ---------------- emit + лог ----------------
    async def emit(self, producer, pred: Prediction, fdict: dict | None = None):
        await producer.send_and_wait(settings.kafka_output_topic, pred.model_dump())
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

    # ---------------- главный цикл ----------------
    async def run(self):
        init_db()
        consumer = await create_consumer()
        producer = await create_producer()
        log.info("Model service started")

        async def sweeper():
            while True:
                await asyncio.sleep(5)
                await self.sweep_triggers(producer)
                now = datetime.utcnow()
                if now - self.last_periodic >= timedelta(seconds=settings.prediction_interval):
                    self.last_periodic = now
                    await self.periodic_predictions(producer)
                if now - self.last_prune > timedelta(days=1):
                    self.last_prune = now
                    prune_old_events(45)
                    log.info("Pruned ml.events older than 45 days")

        task = asyncio.create_task(sweeper())
        try:
            async for msg in consumer:
                try:
                    self.ingest(msg.value)
                except Exception as e:
                    log.error(f"ingest failed: {e}")
        finally:
            task.cancel()
            await consumer.stop()
            await producer.stop()

def main():
    asyncio.run(ModelService().run())

if __name__ == "__main__":
    main()