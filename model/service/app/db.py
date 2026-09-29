from datetime import datetime
from sqlalchemy import (create_engine, Column, Integer, BigInteger, String,
                        Boolean, Float, DateTime, Text, Index, text)
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

Base = declarative_base()

class SensorEventDB(Base):
    """Проекция потока событий (роллинг ~45 дней). Только для фичей."""
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_ml_events_obj_ts", "object_id", "timestamp"),
        Index("ix_ml_events_obj_type_ts", "object_id", "sensor_type", "timestamp"),
        Index("ix_ml_events_alarm", "object_id", "timestamp"),
        {"schema": "ml"},
    )
    id = Column(BigInteger, primary_key=True)
    event_id = Column(String, unique=True, index=True)
    object_id = Column(Integer, nullable=False)
    channel_id = Column(String)
    sensor_type = Column(String, nullable=False)
    engineering_system = Column(String)
    value = Column(String, nullable=False)
    is_alarm = Column(Boolean, nullable=False, default=False)
    timestamp = Column(DateTime, nullable=False)
    nsd_due_at = Column(DateTime)
    nsd_processed_at = Column(DateTime)
    periodic_processed_at = Column(DateTime)
    nsd_due_at = Column(DateTime)
    nsd_processed_at = Column(DateTime)
    periodic_processed_at = Column(DateTime)

class PredictionLogDB(Base):
    """Своя копия прогнозов: мониторинг, дрейф, дообучение."""
    __tablename__ = "prediction_log"
    __table_args__ = (
        Index("ix_ml_predlog_obj_ts", "object_id", "predicted_at"),
        {"schema": "ml"},
    )
    id = Column(BigInteger, primary_key=True)
    prediction_id = Column(String, unique=True, index=True)
    schema_version = Column(Integer, nullable=False, default=1)
    object_id = Column(Integer, nullable=False)
    prediction_type = Column(String, nullable=False)
    risk_score = Column(Float)
    risk_level = Column(String)
    is_alert = Column(Boolean)
    features_json = Column(Text)
    model_version = Column(String, nullable=False, default="v1.0")
    predicted_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    with engine.connect() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS ml"))
        c.commit()
    Base.metadata.create_all(engine, checkfirst=True)
    with engine.connect() as c:
        c.execute(text("ALTER TABLE ml.events ADD COLUMN IF NOT EXISTS nsd_due_at TIMESTAMP"))
        c.execute(text("ALTER TABLE ml.events ADD COLUMN IF NOT EXISTS nsd_processed_at TIMESTAMP"))
        c.execute(text("ALTER TABLE ml.events ADD COLUMN IF NOT EXISTS periodic_processed_at TIMESTAMP"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_ml_events_pending_nsd ON ml.events (nsd_due_at) WHERE nsd_due_at IS NOT NULL AND nsd_processed_at IS NULL"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_ml_events_pending_periodic ON ml.events (object_id, timestamp) WHERE periodic_processed_at IS NULL"))
        c.execute(text("ALTER TABLE ml.events ADD COLUMN IF NOT EXISTS nsd_due_at TIMESTAMP"))
        c.execute(text("ALTER TABLE ml.events ADD COLUMN IF NOT EXISTS nsd_processed_at TIMESTAMP"))
        c.execute(text("ALTER TABLE ml.events ADD COLUMN IF NOT EXISTS periodic_processed_at TIMESTAMP"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_ml_events_pending_nsd ON ml.events (nsd_due_at) WHERE nsd_due_at IS NOT NULL AND nsd_processed_at IS NULL"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_ml_events_pending_periodic ON ml.events (object_id, timestamp) WHERE periodic_processed_at IS NULL"))
        c.execute(text("ALTER TABLE ml.prediction_log ADD COLUMN IF NOT EXISTS prediction_id VARCHAR"))
        c.execute(text("ALTER TABLE ml.prediction_log ADD COLUMN IF NOT EXISTS schema_version INTEGER NOT NULL DEFAULT 1"))
        c.execute(text("ALTER TABLE ml.prediction_log ADD COLUMN IF NOT EXISTS model_version VARCHAR NOT NULL DEFAULT 'v1.0'"))
        c.execute(text("ALTER TABLE ml.prediction_log ADD COLUMN IF NOT EXISTS published_at TIMESTAMP"))
        c.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_ml_prediction_log_prediction_id ON ml.prediction_log (prediction_id) WHERE prediction_id IS NOT NULL"))
        c.commit()

def prune_old_events(days: int = 45):
    """Держим копию модели крошечной."""
    from sqlalchemy import delete
    cutoff = datetime.utcnow() - __import__("datetime").timedelta(days=days)
    with SessionLocal() as s:
        s.execute(delete(SensorEventDB).where(SensorEventDB.timestamp < cutoff))
        s.commit()
