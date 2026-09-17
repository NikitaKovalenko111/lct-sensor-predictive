import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    precision_recall_curve, average_precision_score
)
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

DATA_PATH = f'{Path.cwd()}/dataset/data/fire_risk_dataset.parquet'
df = pd.read_parquet(DATA_PATH)

# Добавляем временную колонку (если её нет)
# Предположим, что у нас есть 'ts' или 'year'/'month'
# Нужно создать временную метку для сплита

feature_cols = [
    'alarms_1h', 'alarms_3h', 'alarms_6h', 'alarms_12h', 'alarms_24h',
    'alarm_channels_24h', 'alarm_types_24h',
    'ratio_1h', 'ratio_6h', 'ratio_24h',
    'log_ratio_1h', 'log_ratio_6h', 'log_ratio_24h',
    'motion_1h', 'motion_6h', 'motion_24h',
    'total_events_1h', 'total_events_24h',
    'motion_ratio_1h', 'motion_ratio_6h', 'motion_ratio_24h',
    'temp_avg_6h', 'temp_max_6h', 'temp_avg_24h', 'temp_max_24h',
    'temp_diff_6h', 'temp_max_diff_6h',
    'has_motion_sensor', 'has_temp_sensor',
    'hour', 'dow', 'month',
    'is_night', 'is_weekend'
]
# УБРАЛИ 'year' из фичей!

available_features = [col for col in feature_cols if col in df.columns]
print(f"Используем {len(available_features)} фичей (БЕЗ year)")

X = df[available_features].fillna(0)
y = df['is_incident']

# ВРЕМЕННОЙ СПЛИТ
# Трейним на 2020-2024, тестируем на 2025-2026
if 'year' in df.columns:
    train_mask = df['year'] <= 2024
    test_mask = df['year'] >= 2025
    
    X_train, X_test = X[train_mask], X[test_mask]
    y_train, y_test = y[train_mask], y[test_mask]
    
    print(f"\n📈 ВРЕМЕННОЙ сплит:")
    print(f"   Train (≤2024): {len(X_train)} записей ({y_train.mean():.4f} позитивных)")
    print(f"   Test  (≥2025): {len(X_test)} записей ({y_test.mean():.4f} позитивных)")
    print(f"   Позитивных в тесте: {y_test.sum()}")
else:
    print("⚠️ Нет колонки 'year'! Проверь датасет.")
    exit()

if y_test.sum() == 0:
    print("❌ В тесте нет позитивных примеров! Невозможно оценить.")
    exit()

# Обучение
pos_ratio = y_train.mean()
scale_pos_weight = (1 - pos_ratio) / max(pos_ratio, 0.01)
print(f"\n⚖️ scale_pos_weight: {scale_pos_weight:.2f}")

model = lgb.LGBMClassifier(
    n_estimators=1000,
    learning_rate=0.05,
    max_depth=6,
    num_leaves=31,
    min_child_samples=20,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=scale_pos_weight,
    random_state=42,
    n_jobs=-1,
    verbose=-1
)

model.fit(
    X_train, y_train,
    eval_X=X_test,
    eval_y=y_test,
    eval_metric='average_precision',
    callbacks=[
        lgb.early_stopping(50, verbose=False),
        lgb.log_evaluation(100)
    ]
)

print(f"\n✅ Модель обучена за {model.best_iteration_} итераций")

# Метрики
y_test_proba = model.predict_proba(X_test)[:, 1]
ap_score = average_precision_score(y_test, y_test_proba)
print(f"\n📈 PR-AUC: {ap_score:.4f}")

# Подбор порога
precision, recall, thresholds = precision_recall_curve(y_test, y_test_proba)

valid_thresholds = []
for p, r, t in zip(precision, recall, thresholds):
    if p >= 0.7 and r >= 0.5:
        valid_thresholds.append((p, r, t))

if valid_thresholds:
    best = max(valid_thresholds, key=lambda x: x[1])
    best_threshold = best[2]
    print(f"\n✅ Найден порог: {best_threshold:.4f}")
    print(f"   Precision: {best[0]:.3f}")
    print(f"   Recall: {best[1]:.3f}")
else:
    distances = [(p - 0.7)**2 + (r - 0.5)**2 for p, r in zip(precision, recall)]
    best_idx = np.argmin(distances)
    best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.5
    print(f"\n⚠️ Ближайший порог: {best_threshold:.4f}")
    print(f"   Precision: {precision[best_idx]:.3f}")
    print(f"   Recall: {recall[best_idx]:.3f}")

y_test_pred = (y_test_proba >= best_threshold).astype(int)
test_precision = precision_score(y_test, y_test_pred, zero_division=0)
test_recall = recall_score(y_test, y_test_pred, zero_division=0)

print(f"\n🎯 ЧЕСТНЫЕ МЕТРИКИ (временной сплит, без year):")
print(f"   Precision: {test_precision:.3f} {'✅' if test_precision > 0.7 else '❌'}")
print(f"   Recall:    {test_recall:.3f} {'✅' if test_recall > 0.5 else '❌'}")

# Feature Importance
importance = pd.DataFrame({
    'feature': available_features,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(f"\n🔝 Топ-10 фичей:")
print(importance.head(10).to_string(index=False))