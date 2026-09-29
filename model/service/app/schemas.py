from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

class SensorEvent(BaseModel):
    schema_version: Literal[1]
    event_id: str
    object_id: int
    channel_id: Optional[str] = None
    sensor_type: str
    engineering_system: Optional[str] = None
    value: str
    is_alarm: bool = False
    timestamp: datetime

class Prediction(BaseModel):
    schema_version: Literal[1] = 1
    prediction_id: UUID = Field(default_factory=uuid4)
    object_id: int
    prediction_type: Literal["fire_risk", "nsd_event", "nsd_risk", "equipment_failure"]
    risk_score: float = Field(ge=0, le=1)
    risk_level: Literal["low", "medium", "high", "critical"]
    is_alert: bool                # превышен порог модели
    predicted_at: datetime
    features_used: Dict[str, Any] = Field(default_factory=dict)
    model_version: str = "v1.0"

class PredictionRequest(BaseModel):
    object_id: int = Field(gt=0)
    prediction_types: list[Literal[
        "fire_risk", "nsd_event", "nsd_risk", "equipment_failure"
    ]] = Field(default_factory=list)

    @field_validator("prediction_types")
    @classmethod
    def unique_prediction_types(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("prediction_types must be unique")
        return values

class PredictionResponse(BaseModel):
    predictions: list[Prediction]
