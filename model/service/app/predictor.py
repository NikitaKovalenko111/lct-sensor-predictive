import joblib
import numpy as np
from datetime import datetime, timezone
from .config import settings
from .schemas import Prediction

class Predictor:
    def __init__(self):
        m = settings
        self.fire      = joblib.load(m.fire_model_path)
        self.fire_thr  = joblib.load(m.fire_thr_path)
        self.fire_ft   = joblib.load(m.fire_feat_path)

        self.nsd       = joblib.load(m.nsd_model_path)
        self.nsd_ft    = joblib.load(m.nsd_feat_path)
        self.nsd_thr   = joblib.load(m.nsd_threshold)

        self.risk      = joblib.load(m.risk_model_path)
        self.risk_thr  = joblib.load(m.risk_thr_path)
        self.risk_ft   = joblib.load(m.risk_feat_path)

        self.fault     = joblib.load(m.fault_model_path)
        self.fault_thr = joblib.load(m.fault_thr_path)
        self.fault_ft  = joblib.load(m.fault_feat_path)

    @staticmethod
    def _vec(fdict: dict, feats: list) -> np.ndarray:
        return np.array([[float(fdict.get(f, 0) or 0) for f in feats]])

    @staticmethod
    def _level(p: float) -> str:
        return ("critical" if p >= 0.8 else "high" if p >= 0.6
                else "medium" if p >= 0.3 else "low")

    def _make(self, obj, ptype, proba, thr, fdict, feats) -> Prediction:
        return Prediction(
            object_id=obj,
            prediction_type=ptype,
            risk_score=round(float(proba), 4),
            risk_level=self._level(proba),
            is_alert=bool(proba >= thr),
            predicted_at=datetime.now(timezone.utc),
            features_used={k: fdict.get(k) for k in feats[:6]},
        )

    def fire_risk(self, obj, fdict):
        p = self.fire.predict_proba(self._vec(fdict, self.fire_ft))[0, 1]
        return self._make(obj, "fire_risk", p, self.fire_thr, fdict, self.fire_ft)

    def nsd_event(self, obj, fdict):
        p = self.nsd.predict_proba(self._vec(fdict, self.nsd_ft))[0, 1]
        return self._make(obj, "nsd_event", p, self.nsd_thr, fdict, self.nsd_ft)

    def nsd_risk(self, obj, fdict):
        p = self.risk.predict_proba(self._vec(fdict, self.risk_ft))[0, 1]
        return self._make(obj, "nsd_risk", p, self.risk_thr, fdict, self.risk_ft)

    def fault_risk(self, obj, fdict):
        p = self.fault.predict_proba(self._vec(fdict, self.fault_ft))[0, 1]
        return self._make(obj, "equipment_failure", p, self.fault_thr, fdict, self.fault_ft)
