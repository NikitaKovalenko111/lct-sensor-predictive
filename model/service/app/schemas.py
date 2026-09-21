from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class SensorEvent(BaseModel):
    event_id: str
    object_id: int
    channel_id: Optional[str] = None
    sensor_type: str
    engineering_system: Optional[str] = None
    value: str
    is_alarm: bool = False
    timestamp: datetime

class Prediction(BaseModel):
    object_id: int
    prediction_type: str          # fire_risk | nsd_event | nsd_risk
    risk_score: float = Field(ge=0, le=1)
    risk_level: str               # low | medium | high | critical
    is_alert: bool                # превышен порог модели
    predicted_at: datetime
    features_used: Dict[str, Any] = {}
    model_version: str = "v1.0"