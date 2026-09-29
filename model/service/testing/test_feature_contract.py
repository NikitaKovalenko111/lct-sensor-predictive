import unittest

import pandas as pd

from service.app import config
from service.app.feature_engine import FeatureEngine


FIRE_FEATURES = {
    "alarms_1h", "alarms_3h", "alarms_6h", "alarms_12h", "alarms_24h",
    "alarm_channels_24h", "alarm_types_24h",
    "baseline_alarms_1h", "baseline_alarms_6h", "baseline_alarms_24h",
    "log_ratio_1h", "log_ratio_6h", "log_ratio_24h",
    "motion_1h", "motion_6h", "motion_24h",
    "total_events_1h", "total_events_24h",
    "baseline_motion_1h", "baseline_motion_6h", "baseline_motion_24h",
    "motion_ratio_1h", "motion_ratio_6h", "motion_ratio_24h",
    "temp_avg_6h", "temp_max_6h", "temp_avg_24h", "temp_max_24h",
    "baseline_temp_6h", "baseline_temp_24h",
    "flood_24h", "hatch_24h", "glass_24h",
    "fan_24h", "door_24h", "pump_24h",
    "hour", "dow", "month", "is_weekend",
    "temp_std_6h", "temp_range_6h", "temp_std_24h", "temp_trend_6h",
    "alarms_std_24h", "alarms_peak_24h", "alarms_active_hours_24h",
    "motion_std_24h", "motion_peak_24h",
}


class FireFeatureContractTest(unittest.TestCase):
    def test_online_engine_produces_all_training_features(self):
        timestamp = pd.Timestamp("2026-09-29 12:00:00")
        rows = [
            {
                "channel_id": "alarm",
                "sensor_type": "generic alarm",
                "value": "alarm",
                "is_alarm": True,
                "ts": timestamp - pd.Timedelta(hours=1),
            },
            {
                "channel_id": "temperature",
                "sensor_type": next(iter(config.TEMP_SENSOR_TYPES)),
                "value": "24.5",
                "is_alarm": False,
                "ts": timestamp - pd.Timedelta(hours=2),
            },
            {
                "channel_id": "motion",
                "sensor_type": next(iter(config.MOTION_SENSOR_TYPES)),
                "value": config.MOTION_VALUE,
                "is_alarm": False,
                "ts": timestamp - pd.Timedelta(hours=3),
            },
        ]

        features = FeatureEngine().fire_features(pd.DataFrame(rows), timestamp)

        self.assertEqual(FIRE_FEATURES, set(features))
        self.assertTrue(all(pd.notna(value) for value in features.values()))


if __name__ == "__main__":
    unittest.main()
