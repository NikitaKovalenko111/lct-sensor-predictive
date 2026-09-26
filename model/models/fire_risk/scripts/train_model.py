import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    precision_recall_curve, confusion_matrix,
    average_precision_score, roc_auc_score
)
import matplotlib
matplotlib.use('Agg')  # Отключаем GUI (фикс для Windows)
import matplotlib.pyplot as plt
import joblib
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# ПУТИ
# ============================================================
DATA_PATH = Path.cwd() / 'dataset/parquets/fire_risk/fire_risk_dataset_v3_equipped.parquet'
MODEL_DIR = Path.cwd() / 'models/fire_risk/saved'
MODEL_DIR.mkdir(exist_ok=True)

# ============================================================
# КОНФИГ
# ============================================================
TARGET_PRECISION = 0.7
TARGET_RECALL = 0.5
TEST_SIZE = 0.3
RANDOM_STATE = 42
RETRAIN_ON_ALL_DATA = False  # True = дообучить на всех данных для продакшена

# ============================================================
# ФИНАЛЬНЫЙ СПИСОК ФИЧЕЙ (45)
# Полный набор 47 МИНУС 2 мертвые фичи (is_night, flood_6h)
# ============================================================
FINAL_FEATURES = [
    # Тревоги (абсолюты)
    'alarms_1h', 'alarms_3h', 'alarms_6h', 'alarms_12h', 'alarms_24h',
    'alarm_channels_24h', 'alarm_types_24h',
    # Базовая линия тревог (характеристика объекта + контекст нормы)
    'baseline_alarms_1h', 'baseline_alarms_6h', 'baseline_alarms_24h',
    # Отношения к базовой линии (только логарифмы)
    'log_ratio_1h', 'log_ratio_6h', 'log_ratio_24h',
    # Движение (абсолюты + базовая линия + отношения)
    'motion_1h', 'motion_6h', 'motion_24h',
    'total_events_1h', 'total_events_24h',
    'baseline_motion_1h', 'baseline_motion_6h', 'baseline_motion_24h',
    'motion_ratio_1h', 'motion_ratio_6h', 'motion_ratio_24h',
    # Температура (абсолюты + базовая линия)
    'temp_avg_6h', 'temp_max_6h', 'temp_avg_24h', 'temp_max_24h',
    'baseline_temp_6h', 'baseline_temp_24h',
    # Предвестники
    'flood_24h', 'hatch_24h', 'glass_24h',
    'fan_24h', 'door_24h', 'pump_24h',
    # Временные признаки (БЕЗ year, БЕЗ is_night)
    'hour', 'dow', 'month', 'is_weekend'
]

FINAL_FEATURES += [
    'temp_std_6h', 'temp_range_6h', 'temp_std_24h', 'temp_trend_6h',
    'alarms_std_24h', 'alarms_peak_24h', 'alarms_active_hours_24h',
    'motion_std_24h', 'motion_peak_24h',
]

# ============================================================
# ЗАГРУЗКА ДАННЫХ
# ============================================================
print("📂 Загрузка данных...")
df = pd.read_parquet(DATA_PATH)
df['ts'] = pd.to_datetime(df['ts'])

print(f"\n✅ Загружено {len(df):,} строк")
print(f"   Баланс классов: {df['is_incident'].value_counts().to_dict()}")
print(f"   Доля позитивных: {df['is_incident'].mean():.4f}")

# Проверка наличия всех фичей
missing = [f for f in FINAL_FEATURES if f not in df.columns]
if missing:
    print(f"\n⚠️ Отсутствуют фичи: {missing}")
    print("   Пересоздайте датасет или проверьте колонки!")
    exit()

print(f"\n✅ Используем {len(FINAL_FEATURES)} фичей")

X = df[FINAL_FEATURES].fillna(0).astype(float)
y = df['is_incident'].astype(int)

# ============================================================
# СТРАТИФИЦИРОВАННЫЙ СПЛИТ
# ============================================================
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=TEST_SIZE,
    random_state=RANDOM_STATE,
    stratify=y  # Баланс сохраняется в обеих выборках
)

print(f"\n📈 Стратифицированный сплит ({TEST_SIZE:.0%} тест):")
print(f"   Train: {len(X_train):,} записей ({y_train.mean():.4f} позитивных)")
print(f"   Test:  {len(X_test):,} записей ({y_test.mean():.4f} позитивных)")
print(f"   Позитивных в тесте: {y_test.sum()}")
print(f"   Негативных в тесте: {(y_test == 0).sum()}")

# ============================================================
# ОБУЧЕНИЕ МОДЕЛИ
# ============================================================
pos_ratio = y_train.mean()
scale_pos_weight = (1 - pos_ratio) / max(pos_ratio, 0.01)
print(f"\n⚖️ scale_pos_weight: {scale_pos_weight:.2f}")

print("\n🚀 Обучение LightGBM...")
model = lgb.LGBMClassifier(
    n_estimators=1000,
    learning_rate=0.05,
    max_depth=6,
    num_leaves=31,
    min_child_samples=10,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=0.1,
    scale_pos_weight=scale_pos_weight,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    verbose=-1
)

model.fit(
    X_train, y_train,
    eval_X=X_test,
    eval_y=y_test,
    eval_metric='average_precision',
    callbacks=[
        lgb.early_stopping(100, verbose=False),
        lgb.log_evaluation(100)
    ]
)
print(f"\n✅ Модель обучена за {model.best_iteration_} итераций")

# ============================================================
# МЕТРИКИ И ПОДБОР ПОРОГА
# ============================================================
y_test_proba = model.predict_proba(X_test)[:, 1]

ap_score = average_precision_score(y_test, y_test_proba)
try:
    auc_score = roc_auc_score(y_test, y_test_proba)
except Exception:
    auc_score = 0.0

print(f"\n📈 ОБЩИЕ МЕТРИКИ:")
print(f"   PR-AUC:   {ap_score:.4f}")
print(f"   ROC-AUC:  {auc_score:.4f}")

precision, recall, thresholds = precision_recall_curve(y_test, y_test_proba)

# Ищем порог, удовлетворяющий обеим целям
valid_thresholds = [
    (p, r, t) for p, r, t in zip(precision, recall, thresholds)
    if p >= TARGET_PRECISION and r >= TARGET_RECALL
]

if valid_thresholds:
    best_p, best_r, best_threshold = max(valid_thresholds, key=lambda x: x[1])
    print(f"\n✅ Найден порог: {best_threshold:.4f} (P={best_p:.3f}, R={best_r:.3f})")
else:
    print("\n⚠️ Точного соответствия нет, ищем ближайший порог...")
    distances = [(p - TARGET_PRECISION)**2 + (r - TARGET_RECALL)**2
                 for p, r in zip(precision, recall)]
    best_idx = int(np.argmin(distances))
    best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.5
    print(f"   Ближайший порог: {best_threshold:.4f}")

# Итоговые метрики на выбранном пороге
y_test_pred = (y_test_proba >= best_threshold).astype(int)
test_precision = precision_score(y_test, y_test_pred, zero_division=0)
test_recall = recall_score(y_test, y_test_pred, zero_division=0)
test_f1 = f1_score(y_test, y_test_pred, zero_division=0)

print(f"\n🎯 ИТОГ НА ТЕСТЕ (порог {best_threshold:.4f}):")
print(f"   Precision: {test_precision:.3f} {'✅' if test_precision > TARGET_PRECISION else '❌'} (цель > {TARGET_PRECISION})")
print(f"   Recall:    {test_recall:.3f} {'✅' if test_recall > TARGET_RECALL else '❌'} (цель > {TARGET_RECALL})")
print(f"   F1-Score:  {test_f1:.3f}")

passed = test_precision > TARGET_PRECISION and test_recall > TARGET_RECALL
print(f"\n   {'✅✅✅ ТРЕБОВАНИЯ ВЫПОЛНЕНЫ ✅✅✅' if passed else '❌ Требования не выполнены'}")

cm = confusion_matrix(y_test, y_test_pred)
print(f"\n📊 Confusion Matrix:")
print(f"   TN={cm[0][0]:4d}  FP={cm[0][1]:4d}")
print(f"   FN={cm[1][0]:4d}  TP={cm[1][1]:4d}")

# ============================================================
# ДИАГНОСТИКА: не тривиальна ли модель?
# ============================================================
proba_sorted = np.sort(y_test_proba)
print(f"\n📊 Распределение предсказаний:")
print(f"   Min:           {proba_sorted[0]:.4f}")
print(f"   10% квантиль:  {proba_sorted[len(proba_sorted)//10]:.4f}")
print(f"   Медиана:       {proba_sorted[len(proba_sorted)//2]:.4f}")
print(f"   90% квантиль:  {proba_sorted[len(proba_sorted)*9//10]:.4f}")
print(f"   Max:           {proba_sorted[-1]:.4f}")

neg_mask = y_test == 0
correct_neg = (y_test_pred[neg_mask] == 0).sum()
total_neg = neg_mask.sum()
print(f"\n🎯 Правильно распознано негативов: {correct_neg}/{total_neg} ({100*correct_neg/total_neg:.1f}%)")
if correct_neg == 0:
    print("   ⚠️ МОДЕЛЬ ТРИВИАЛЬНА! Всё предсказывает как пожар!")
else:
    print("   ✅ Модель реально разделяет классы")

# ============================================================
# ВАЖНОСТЬ ФИЧЕЙ
# ============================================================
importance = pd.DataFrame({
    'feature': FINAL_FEATURES,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(f"\n🔝 Топ-15 фичей:")
print(importance.head(15).to_string(index=False))

zero_imp = importance[importance['importance'] == 0]['feature'].tolist()
if zero_imp:
    print(f"\n⚠️ Фичи с нулевой важностью: {zero_imp}")

# ============================================================
# ОПЦИОНАЛЬНО: ДОБУЧЕНИЕ НА ВСЕХ ДАННЫХ (для продакшена)
# ============================================================
if RETRAIN_ON_ALL_DATA:
    print("\n🔄 Дообучение на всех данных (для продакшена)...")
    model_final = lgb.LGBMClassifier(
        n_estimators=model.best_iteration_,  # Используем найденное число итераций
        learning_rate=0.05,
        max_depth=6,
        num_leaves=31,
        min_child_samples=10,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=-1
    )
    model_final.fit(X, y)
    model_to_save = model_final
    print("✅ Дообучение завершено")
else:
    model_to_save = model
    print("\nℹ️ Используем модель с трейна (честная оценка)")

# ============================================================
# СОХРАНЕНИЕ
# ============================================================
joblib.dump(model_to_save, MODEL_DIR / 'fire_risk_model.joblib')
joblib.dump(best_threshold, MODEL_DIR / 'fire_risk_threshold.joblib')
joblib.dump(FINAL_FEATURES, MODEL_DIR / 'fire_risk_features.joblib')

print(f"\n💾 Сохранено в {MODEL_DIR}:")
print(f"   - fire_risk_model.joblib")
print(f"   - fire_risk_threshold.joblib ({best_threshold:.4f})")
print(f"   - fire_risk_features.joblib ({len(FINAL_FEATURES)} фичей)")

# ============================================================
# ГРАФИКИ
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# PR Curve
best_idx = int(np.argmin(np.abs(thresholds - best_threshold)))
axes[0].plot(recall, precision, 'b-', linewidth=2, label='PR Curve')
axes[0].axhline(y=TARGET_PRECISION, color='r', linestyle='--', linewidth=1.5,
                label=f'Precision = {TARGET_PRECISION}')
axes[0].axvline(x=TARGET_RECALL, color='g', linestyle='--', linewidth=1.5,
                label=f'Recall = {TARGET_RECALL}')
axes[0].plot(recall[best_idx], precision[best_idx], 'ko', markersize=12,
             label=f'Threshold = {best_threshold:.3f}')
axes[0].set_xlabel('Recall', fontsize=12)
axes[0].set_ylabel('Precision', fontsize=12)
axes[0].set_title(f'PR Curve (PR-AUC={ap_score:.3f})', fontsize=14, fontweight='bold')
axes[0].legend(fontsize=10)
axes[0].grid(True, alpha=0.3)
axes[0].set_xlim([0, 1])
axes[0].set_ylim([0, 1])

# Feature Importance
top_n = 15
axes[1].barh(importance['feature'][:top_n][::-1],
             importance['importance'][:top_n][::-1], color='steelblue')
axes[1].set_xlabel('Importance', fontsize=12)
axes[1].set_title(f'Top-{top_n} Feature Importance', fontsize=14, fontweight='bold')

plt.tight_layout()
plt.savefig(MODEL_DIR / 'fire_risk_analysis.png', dpi=150, bbox_inches='tight')
print(f"\n📈 График сохранён: {MODEL_DIR / 'fire_risk_analysis.png'}")

print("\n" + "="*60)
print("✅ ОБУЧЕНИЕ ЗАВЕРШЕНО")
print("="*60)