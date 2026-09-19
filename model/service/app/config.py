from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../model

class Settings(BaseSettings):
    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_input_topic: str = "sensor_events"
    kafka_output_topic: str = "predictions"
    kafka_consumer_group: str = "model-service"

    # PostgreSQL
    database_url: str = "postgresql://postgres:postgres@localhost:5432/model_db"

    # Артефакты моделей (лежат в уже существующих папках)
    fire_model_path: Path  = PROJECT_ROOT / "models/fire_risk/saved/fire_risk_model.joblib"
    fire_thr_path: Path    = PROJECT_ROOT / "models/fire_risk/saved/fire_risk_threshold.joblib"
    fire_feat_path: Path   = PROJECT_ROOT / "models/fire_risk/saved/fire_risk_features.joblib"

    nsd_model_path: Path   = PROJECT_ROOT / "models/unac/saved/nsd_best_model.joblib"
    nsd_feat_path: Path    = PROJECT_ROOT / "models/unac/saved/nsd_best_features.joblib"
    nsd_threshold: float   = 0.3053   # из compare_models (макс F1); лучше сохранить joblib-ом

    risk_model_path: Path  = PROJECT_ROOT / "models/unac/saved/nsd_risk_model.joblib"
    risk_thr_path: Path    = PROJECT_ROOT / "models/unac/saved/nsd_risk_threshold.joblib"
    risk_feat_path: Path   = PROJECT_ROOT / "models/unac/saved/nsd_risk_features.joblib"

    # Периодичность плановых прогнозов (сек)
    prediction_interval: int = 3600

    class Config:
        env_file = ".env"

settings = Settings()

# ============================================================
# СЛОВАРИ ТИПОВ ДАТЧИКОВ — СВЕРИТЬ С ТРЕНИРОВОЧНЫМИ SQL!
# ============================================================
# Исключались из счётчиков тревог пожарной модели (иначе утечка таргета)
FIRE_DETECTOR_TYPES = {"Датчик дыма", "Тепловой датчик", "Ручной извещатель", "Состояние УИР-Р"}

MOTION_SENSOR_TYPES = {"Датчик движения"}
TEMP_SENSOR_TYPES   = {"Датчик температуры"}

# Триггеры НСД + коды (как в обучении)
NSD_TRIGGER_TYPES = {"КД Дверь": 1, "КД Люк": 2, "Стекло": 3}

# Поломки (без датчика дыма — спам)
FAILURE_VALUES = {"Неисправен", "Обесточен", "Питание от батарей", "Много неисправных устройств"}
FAILURE_EXCLUDED_TYPES = {"Датчик дыма"}

OPEN_VALUE      = "Не замкнут"
MOTION_VALUE    = "Обнаружено движение"
OFF_GUARD_VALUE = "Снято с охраны"