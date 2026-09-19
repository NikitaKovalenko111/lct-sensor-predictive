from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import settings

Base = declarative_base()

class SensorEventDB(Base):
    """Сырые события датчиков (для дообучения)."""
    __tablename__ = "sensor_events"
    
    id = Column(Integer, primary_key=True)
    event_id = Column(String, unique=True, index=True)
    object_id = Column(Integer, index=True)
    sensor_type = Column(String)
    value = Column(String)
    is_alarm = Column(Boolean)
    timestamp = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PredictionDB(Base):
    """История прогнозов (для мониторинга качества)."""
    __tablename__ = "predictions"
    
    id = Column(Integer, primary_key=True)
    object_id = Column(Integer, index=True)
    prediction_type = Column(String)
    risk_score = Column(Float)
    risk_level = Column(String)
    features_json = Column(Text)  # JSON с фичами
    predicted_at = Column(DateTime, index=True)

# Инициализация
engine = create_engine(settings.database_url)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def save_event(event: SensorEventDB):
    with SessionLocal() as session:
        session.add(event)
        session.commit()

def save_prediction(pred: PredictionDB):
    with SessionLocal() as session:
        session.add(pred)
        session.commit()