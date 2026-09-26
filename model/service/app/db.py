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

class PredictionLogDB(Base):
    """Своя копия прогнозов: мониторинг, дрейф, дообучение."""
    __tablename__ = "prediction_log"
    __table_args__ = (
        Index("ix_ml_predlog_obj_ts", "object_id", "predicted_at"),
        {"schema": "ml"},
    )
    id = Column(BigInteger, primary_key=True)
    object_id = Column(Integer, nullable=False)
    prediction_type = Column(String, nullable=False)
    risk_score = Column(Float)
    risk_level = Column(String)
    is_alert = Column(Boolean)
    features_json = Column(Text)
    predicted_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    with engine.connect() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS ml"))
        c.commit()
    Base.metadata.create_all(engine, checkfirst=True)

def prune_old_events(days: int = 45):
    """Держим копию модели крошечной."""
    from sqlalchemy import delete
    cutoff = datetime.utcnow() - __import__("datetime").timedelta(days=days)
    with SessionLocal() as s:
        s.execute(delete(SensorEventDB).where(SensorEventDB.timestamp < cutoff))
        s.commit()