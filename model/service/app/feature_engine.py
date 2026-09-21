import numpy as np
import pandas as pd
from datetime import timedelta
from sqlalchemy import select
from .db import SessionLocal, SensorEventDB
from . import config

H = timedelta(hours=1)

def duck_dow(ts) -> int:
    """Приводим pandas-день недели к договорённости DuckDB (0=вс)."""
    return (ts.weekday() + 1) % 7

class FeatureEngine:
    """Считает фичи всех трёх моделей из сырых событий в PostgreSQL.
    Определения ДОЛЖНЫ совпадать с тренировочными SQL 1-в-1."""

    # ---------- загрузка ----------
    def load_events(self, object_id: int, ts, lookback_days: int = 40, forward_min: int = 15):
        start = ts - timedelta(days=lookback_days)
        end = ts + timedelta(minutes=forward_min)  # нужно для cascade_openings_10min
        with SessionLocal() as s:
            rows = s.execute(
                select(SensorEventDB).where(
                    SensorEventDB.object_id == object_id,
                    SensorEventDB.timestamp >= start,
                    SensorEventDB.timestamp < end,
                )
            ).scalars().all()
        if not rows:
            return pd.DataFrame(columns=["channel_id", "sensor_type", "value", "is_alarm", "ts"])
        df = pd.DataFrame([{
            "channel_id": r.channel_id,
            "sensor_type": r.sensor_type,
            "value": r.value,
            "is_alarm": r.is_alarm,
            "ts": pd.Timestamp(r.timestamp),
        } for r in rows])
        return df

    @staticmethod
    def _cnt(df, mask, lo, hi, strict_lo=False):
        m = mask & (df["ts"] > lo if strict_lo else df["ts"] >= lo) & (df["ts"] < hi)
        return int(m.sum())

    # ---------- masks ----------
    @staticmethod
    def _alarm_mask(df):
        return df["is_alarm"] & ~df["sensor_type"].isin(config.FIRE_DETECTOR_TYPES)

    @staticmethod
    def _motion_mask(df):
        return (df["sensor_type"].isin(config.MOTION_SENSOR_TYPES)
                & (df["value"] == config.MOTION_VALUE))

    @staticmethod
    def _failure_mask(df):
        return (df["is_alarm"]
                & df["value"].isin(config.FAILURE_VALUES)
                & ~df["sensor_type"].isin(config.FAILURE_EXCLUDED_TYPES))

    # ==========================================================
    # МОДЕЛЬ 1: ПОЖАР (45 фичей)
    # ==========================================================
    def fire_features(self, df: pd.DataFrame, ts) -> dict:
        f = {}
        alarms = self._alarm_mask(df)
        b = ts - timedelta(days=7)  # точка базовой линии

        for h in (1, 3, 6, 12, 24):
            f[f"alarms_{h}h"] = self._cnt(df, alarms, ts - h * H, ts)

        w24 = alarms & (df["ts"] >= ts - 24 * H) & (df["ts"] < ts)
        f["alarm_channels_24h"] = int(df.loc[w24, "channel_id"].nunique())
        f["alarm_types_24h"] = int(df.loc[w24, "sensor_type"].nunique())

        for h in (1, 6, 24):
            f[f"baseline_alarms_{h}h"] = self._cnt(df, alarms, b - h * H, b)
        for h in (1, 6, 24):
            base = f[f"baseline_alarms_{h}h"]
            f[f"log_ratio_{h}h"] = float(np.log1p(f[f"alarms_{h}h"] / base)) if base else 0.0

        motion = self._motion_mask(df)
        all_motion = df["sensor_type"].isin(config.MOTION_SENSOR_TYPES)
        for h in (1, 6, 24):
            f[f"motion_{h}h"] = self._cnt(df, motion, ts - h * H, ts)
            f[f"baseline_motion_{h}h"] = self._cnt(df, motion, b - h * H, b)
        f["total_events_1h"] = self._cnt(df, all_motion, ts - H, ts)
        f["total_events_24h"] = self._cnt(df, all_motion, ts - 24 * H, ts)
        for h in (1, 6, 24):
            base = f[f"baseline_motion_{h}h"]
            f[f"motion_ratio_{h}h"] = f[f"motion_{h}h"] / base if base else 0.0

        # Температура (значения парсим из строки)
        temp = df[df["sensor_type"].isin(config.TEMP_SENSOR_TYPES)].copy()
        temp["num"] = pd.to_numeric(temp["value"], errors="coerce")
        temp = temp.dropna(subset=["num"])
        for h in (6, 24):
            w = (temp["ts"] >= ts - h * H) & (temp["ts"] < ts)
            wb = (temp["ts"] >= b - h * H) & (temp["ts"] < b)
            f[f"temp_avg_{h}h"] = float(temp.loc[w, "num"].mean()) if w.sum() else 0.0
            f[f"temp_max_{h}h"] = float(temp.loc[w, "num"].max()) if w.sum() else 0.0
            f[f"baseline_temp_{h}h"] = float(temp.loc[wb, "num"].mean()) if wb.sum() else 0.0

        # Предвестники
        precursors = {
            "flood_24h": "Датчик затопления", "hatch_24h": "КД Люк",
            "glass_24h": "Стекло", "fan_24h": "Состояние вентилятора",
            "door_24h": "КД Дверь", "pump_24h": "Состояние насоса",
        }
        for name, stype in precursors.items():
            f[name] = self._cnt(df, alarms & (df["sensor_type"] == stype), ts - 24 * H, ts)

        # Временные
        f["hour"] = ts.hour
        f["dow"] = duck_dow(ts)
        f["month"] = ts.month
        f["is_weekend"] = 1 if ts.weekday() >= 5 else 0
        return f

    # ==========================================================
    # МОДЕЛЬ 2: КЛАССИФИКАТОР НСД (9 фичей, на событие-триггер)
    # ==========================================================
    def nsd_event_features(self, df: pd.DataFrame, ts, trigger_type: str) -> dict:
        f = {}
        f["sensor_type_code"] = config.NSD_TRIGGER_TYPES[trigger_type]
        f["hour"] = ts.hour
        f["dow"] = duck_dow(ts)
        f["month"] = ts.month
        f["is_off_hours"] = 1 if (ts.hour >= 22 or ts.hour < 6 or ts.weekday() >= 5) else 0

        f["motion_before_30min"] = self._cnt(
            df, self._motion_mask(df), ts - timedelta(minutes=30), ts)

        # Каскад: другие открытия СТРОГО после триггера, в течение 10 мин
        openings = (df["is_alarm"]
                    & df["sensor_type"].isin(config.NSD_TRIGGER_TYPES)
                    & (df["value"] == config.OPEN_VALUE))
        f["cascade_openings_10min"] = self._cnt(
            df, openings, ts, ts + timedelta(minutes=10), strict_lo=True)

        failures = self._failure_mask(df)
        f["failures_14d"] = self._cnt(df, failures, ts - timedelta(days=14), ts)
        f["failures_30d"] = self._cnt(df, failures, ts - timedelta(days=30), ts)
        return f

    # ==========================================================
    # МОДЕЛЬ 3: РИСК-СКОРИНГ НСД (10 фичей, на объект-день)
    # ==========================================================
    def nsd_risk_features(self, df: pd.DataFrame, day) -> dict:
        day = pd.Timestamp(day).normalize()
        f = {}
        openings_ts = df.loc[
            df["is_alarm"]
            & df["sensor_type"].isin(config.NSD_TRIGGER_TYPES)
            & (df["value"] == config.OPEN_VALUE), "ts"].tolist()
        motion_ts = df.loc[self._motion_mask(df), "ts"].to_numpy()
        offguard_ts = df.loc[df["value"] == config.OFF_GUARD_VALUE, "ts"].to_numpy()

        # "Чистые" НСД в прошлом: открытие + движение в 5 мин ПОСЛЕ + НЕ снято с охраны за 60 мин до
        clean = []
        m5 = timedelta(minutes=5)
        h60 = timedelta(minutes=60)
        for t in openings_ts:
            t_np = np.datetime64(t)
            has_motion = ((motion_ts > t_np) & (motion_ts <= t_np + m5)).any()
            was_off = len(offguard_ts) and ((offguard_ts >= t_np - h60) & (offguard_ts < t_np)).any()
            if has_motion and not was_off:
                clean.append(t)
        clean = pd.to_datetime(pd.Series(clean, dtype="datetime64[ns]")) if clean \
            else pd.Series([], dtype="datetime64[ns]")

        for d in (1, 7, 30):
            lo, hi = day - timedelta(days=d), day
            f[f"nsd_prev_{d}d"] = int(((clean >= lo) & (clean < hi)).sum())

        failures = self._failure_mask(df)
        offguard = df["value"] == config.OFF_GUARD_VALUE
        for d in (7, 30):
            f[f"failures_prev_{d}d"] = self._cnt(df, failures, day - timedelta(days=d), day)
            f[f"off_guard_prev_{d}d"] = self._cnt(df, offguard, day - timedelta(days=d), day)

        f["dow"] = duck_dow(day)
        f["month"] = day.month
        f["is_weekend"] = 1 if day.weekday() >= 5 else 0
        return f