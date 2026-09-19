import joblib
import numpy as np
from datetime import datetime
from pathlib import Path
from config import settings
from schemas import Prediction, ObjectFeatures

class Predictor:
    """Загружает модели и делает предсказания."""
    
    def __init__(self):
        self.models_dir = settings.models_dir
        
        # Загрузка моделей
        self.fire_model = joblib.load(self.models_dir / settings.fire_model_name)
        self.fire_threshold = settings.fire_threshold
        
        self.nsd_model = joblib.load(self.models_dir / settings.nsd_model_name)
        self.nsd_threshold = settings.nsd_threshold
        
        self.nsd_risk_model = joblib.load(self.models_dir / settings.nsd_risk_model_name)
        self.nsd_risk_threshold = settings.nsd_risk_threshold
        
        # Фичи для каждой модели (из обучения)
        self.fire_features = joblib.load(self.models_dir / "fire_risk_features.joblib")
        self.nsd_features = joblib.load(self.models_dir / "nsd_best_features.joblib")
        self.nsd_risk_features = joblib.load(self.models_dir / "nsd_risk_features.joblib")
    
    def _risk_level(self, score: float) -> str:
        if score >= 0.8: return "critical"
        if score >= 0.6: return "high"
        if score >= 0.3: return "medium"
        return "low"
    
    def predict_fire_risk(self, features: ObjectFeatures) -> Prediction:
        """Прогноз пожароопасности."""
        # Формируем вектор фичей
        feature_dict = features.dict()
        X = np.array([[feature_dict.get(f, 0) for f in self.fire_features]])
        
        proba = self.fire_model.predict_proba(X)[0][1]
        
        return Prediction(
            object_id=features.object_id,
            prediction_type="fire_risk",
            risk_score=float(proba),
            risk_level=self._risk_level(proba),
            predicted_at=datetime.utcnow(),
            features_used={k: feature_dict.get(k) for k in self.fire_features[:5]},
            model_version="v1.0"
        )
    
    def predict_nsd_event(self, features: ObjectFeatures) -> Prediction:
        """Классификация НСД (реальное или ложное)."""
        feature_dict = features.dict()
        X = np.array([[feature_dict.get(f, 0) for f in self.nsd_features]])
        
        proba = self.nsd_model.predict_proba(X)[0][1]
        
        return Prediction(
            object_id=features.object_id,
            prediction_type="nsd_event",
            risk_score=float(proba),
            risk_level=self._risk_level(proba),
            predicted_at=datetime.utcnow(),
            features_used={k: feature_dict.get(k) for k in self.nsd_features},
            model_version="v1.0"
        )
    
    def predict_nsd_risk(self, features: ObjectFeatures) -> Prediction:
        """Прогноз риска НСД на 24ч."""
        feature_dict = features.dict()
        X = np.array([[feature_dict.get(f, 0) for f in self.nsd_risk_features]])
        
        proba = self.nsd_risk_model.predict_proba(X)[0][1]
        
        return Prediction(
            object_id=features.object_id,
            prediction_type="nsd_risk",
            risk_score=float(proba),
            risk_level=self._risk_level(proba),
            predicted_at=datetime.utcnow(),
            features_used={k: feature_dict.get(k) for k in self.nsd_risk_features},
            model_version="v1.0"
        )