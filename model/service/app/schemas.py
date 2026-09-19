from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class SensorEvent(BaseModel):
    """Входящее событие датчика от основного бэкенда."""
    event_id: str
    object_id: int
    channel_id: str
    sensor_type: str
    engineering_system: str
    value: str
    is_alarm: bool
    timestamp: datetime

class Prediction(BaseModel):
    """Прогноз для объекта."""
    object_id: int
    prediction_type: str  # fire_risk | nsd_event | nsd_risk
    risk_score: float = Field(..., ge=0, le=1)
    risk_level: str  # low | medium | high | critical
    predicted_at: datetime
    features_used: Dict[str, Any]
    model_version: str = "v1.0"

class ObjectFeatures(BaseModel):
    """Агрегированные фичи для объекта."""
    object_id: int
    timestamp: datetime
    
    # Пожарные фичи
    alarms_1h: int = 0
    alarms_3h: int = 0
    alarms_6h: int = 0
    alarms_24h: int = 0
    temp_max_6h: float = 0
    motion_24h: int = 0
    
    # НСД фичи
    door_openings_24h: int = 0
    motion_before_30min: int = 0
    
    # Риск-скоринг
    nsd_prev_7d: int = 0
    failures_prev_7d: int = 0