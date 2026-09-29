import numpy as np
import pandas as pd
from datetime import timedelta
from sqlalchemy import select
from .db import SessionLocal, SensorEventDB
from . import config

H = timedelta(hours=1)

FAULT_TYPE_MAPPING = {
    'Состояние насоса': 'pump',
    'Состояние вентилятора': 'fan',
    'ИБП': 'ups',
    'Состояние фазы': 'phase',
}

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

        temp6 = temp.loc[(temp["ts"] >= ts - 6 * H) & (temp["ts"] < ts)].copy()
        temp24 = temp.loc[(temp["ts"] >= ts - 24 * H) & (temp["ts"] < ts)].copy()
        f["temp_std_6h"] = float(temp6["num"].std(ddof=0)) if len(temp6) > 1 else 0.0
        f["temp_range_6h"] = float(temp6["num"].max() - temp6["num"].min()) if len(temp6) else 0.0
        f["temp_std_24h"] = float(temp24["num"].std(ddof=0)) if len(temp24) > 1 else 0.0
        if len(temp6) > 1:
            elapsed_hours = (temp6["ts"] - temp6["ts"].min()).dt.total_seconds() / 3600
            f["temp_trend_6h"] = float(np.polyfit(elapsed_hours, temp6["num"], 1)[0]) if elapsed_hours.nunique() > 1 else 0.0
        else:
            f["temp_trend_6h"] = 0.0

        def hourly_stats(mask):
            window = df.loc[mask & (df["ts"] >= ts - 24 * H) & (df["ts"] < ts), "ts"]
            counts = window.dt.floor("h").value_counts()
            hourly = pd.Series(0.0, index=pd.date_range(ts - 24 * H, periods=24, freq="h"))
            for hour, count in counts.items():
                if hour in hourly.index:
                    hourly.loc[hour] = float(count)
            return float(hourly.std(ddof=0)), float(hourly.max()), int((hourly > 0).sum())

        alarm_std, alarm_peak, alarm_active = hourly_stats(alarms)
        f["alarms_std_24h"] = alarm_std
        f["alarms_peak_24h"] = alarm_peak
        f["alarms_active_hours_24h"] = alarm_active
        motion_std, motion_peak, _ = hourly_stats(motion)
        f["motion_std_24h"] = motion_std
        f["motion_peak_24h"] = motion_peak

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

    # ==========================================================
    # МОДЕЛЬ 4: ПРОГНОЗ ПОЛОМОК (21 фича, на объект-день)
    # ==========================================================
    def fault_features(self, df: pd.DataFrame, day) -> dict:       
        day = pd.Timestamp(day).normalize()
        f = {}
        
        # === Базовые фичи из истории НСД (аналогично nsd_risk_features) ===
        openings_ts = df.loc[
            df["is_alarm"]
            & df["sensor_type"].isin(config.NSD_TRIGGER_TYPES)
            & (df["value"] == config.OPEN_VALUE), "ts"].tolist()
        motion_ts = df.loc[self._motion_mask(df), "ts"].to_numpy()
        offguard_ts = df.loc[df["value"] == config.OFF_GUARD_VALUE, "ts"].to_numpy()
        
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
        
        # Календарные фичи
        f["dow"] = duck_dow(day)
        f["month"] = day.month
        f["is_weekend"] = 1 if day.weekday() >= 5 else 0
        
        # === История поломок и плановых работ ===
        failures = self._failure_mask(df)
        offguard = df["value"] == config.OFF_GUARD_VALUE
        
        for d in (7, 30):
            f[f"failures_prev_{d}d"] = self._cnt(df, failures, day - timedelta(days=d), day)
            f[f"off_guard_prev_{d}d"] = self._cnt(df, offguard, day - timedelta(days=d), day)
        
        # === Эпизоды поломок (группы с разрывом > 7 дней) ===
        fault_events = df.loc[failures, "ts"].sort_values().tolist()
        
        # Группируем в эпизоды (разрыв > 7 дней)
        episodes = []
        if fault_events:
            episodes.append(fault_events[0])
            for i in range(1, len(fault_events)):
                if (fault_events[i] - fault_events[i-1]).days > 7:
                    episodes.append(fault_events[i])
        
        episodes_series = pd.to_datetime(pd.Series(episodes, dtype="datetime64[ns]")) if episodes \
            else pd.Series([], dtype="datetime64[ns]")
        
        f["episodes_prev_7d"] = int(((episodes_series >= day - timedelta(days=7)) & 
                                    (episodes_series < day)).sum())
        f["episodes_prev_30d"] = int(((episodes_series >= day - timedelta(days=30)) & 
                                    (episodes_series < day)).sum())
        
        # Свежесть последней поломки
        if episodes:
            last_ep = max(episodes)
            f["days_since_last_episode"] = (day - last_ep).days
        else:
            f["days_since_last_episode"] = 999  # давно не было поломок
        
        # === Каналы и события поломок за последний день ===
        faults_prev_1d = failures & (df["ts"] >= day - timedelta(days=1)) & (df["ts"] < day)
        f["fault_channels_prev_1d"] = int(df.loc[faults_prev_1d, "channel_id"].nunique())
        f["fault_events_prev_1d"] = int(faults_prev_1d.sum())
        
        # === Пер-типовые счётчики эпизодов за 30 дней ===
        type_counts = {t: 0 for t in FAULT_TYPE_MAPPING.values()}
        
        for sensor_type, type_key in FAULT_TYPE_MAPPING.items():
            type_failures = failures & (df["sensor_type"] == sensor_type)
            type_fault_events = df.loc[type_failures, "ts"].sort_values().tolist()
            
            if not type_fault_events:
                continue
            
            # Группируем в эпизоды
            type_episodes = [type_fault_events[0]]
            for i in range(1, len(type_fault_events)):
                if (type_fault_events[i] - type_fault_events[i-1]).days > 7:
                    type_episodes.append(type_fault_events[i])
            
            # Считаем эпизоды за последние 30 дней
            type_episodes_series = pd.to_datetime(pd.Series(type_episodes, dtype="datetime64[ns]"))
            recent_episodes = int(((type_episodes_series >= day - timedelta(days=30)) & 
                                (type_episodes_series < day)).sum())
            type_counts[type_key] = recent_episodes
        
        f["pump_eps_30d"] = type_counts.get('pump', 0)
        f["fan_eps_30d"] = type_counts.get('fan', 0)
        f["ups_eps_30d"] = type_counts.get('ups', 0)
        f["phase_eps_30d"] = type_counts.get('phase', 0)
        
        # === Хроничность каналов ===
        faults_prev_30d = failures & (df["ts"] >= day - timedelta(days=30)) & (df["ts"] < day)
        channel_counts = df.loc[faults_prev_30d].groupby("channel_id").size()
        
        if len(channel_counts) > 0:
            f["max_channel_eps_30d"] = int(channel_counts.max())
            f["repeat_channels_30d"] = int((channel_counts >= 2).sum())
        else:
            f["max_channel_eps_30d"] = 0
            f["repeat_channels_30d"] = 0
        
        return f
