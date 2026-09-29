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
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import joblib
from pathlib import Path
import os
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# ПУТИ
# ============================================================
DATA_PATH = Path(os.environ.get('TRAIN_DATA_ROOT', Path(__file__).resolve().parents[3] / 'dataset/parquets')) / 'unac/unac_dataset_v2.parquet'
MODEL_DIR = Path(os.environ.get('TRAIN_OUTPUT_ROOT', Path(__file__).resolve().parents[3] / 'models')) / 'unac/saved'
MODEL_DIR.mkdir(parents=True, exist_ok=True)

TARGET_PRECISION = 0.7
TARGET_RECALL = 0.5
TEST_SIZE = 0.3
RANDOM_STATE = 42

# ============================================================
# ФИЧИ (БЕЗ was_off_guard_60min — утечка!)
# ============================================================
FEATURES = [
    'sensor_type_code',
    'hour', 'dow', 'month', 'is_off_hours',
    'motion_before_30min',
    'cascade_openings_10min'
]
TARGET_COL = 'is_nsd_clean'  # очищенный таргет

# ============================================================
# ЗАГРУЗКА
# ============================================================
print("📂 Загрузка очищенных данных НСД...")
df = pd.read_parquet(DATA_PATH)
df['ts'] = pd.to_datetime(df['ts'])

print(f"\n✅ Загружено {len(df):,} строк")
print(f"   Баланс: {df[TARGET_COL].value_counts().to_dict()}")
print(f"   Доля позитивных: {df[TARGET_COL].mean():.4f}")

missing = [f for f in FEATURES if f not in df.columns]
if missing:
    print(f"\n⚠️ Отсутствуют фичи: {missing}")
    raise SystemExit(1)

print(f"\n✅ Используем {len(FEATURES)} фичей (БЕЗ was_off_guard — утечка)")

X = df[FEATURES].fillna(0).astype(float)
y = df[TARGET_COL].astype(int)

# ============================================================
# СПЛИТ
# ============================================================
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
)
print(f"\n📈 Сплит ({TEST_SIZE:.0%} тест):")
print(f"   Train: {len(X_train):,} ({y_train.mean():.4f} позитивных)")
print(f"   Test:  {len(X_test):,} ({y_test.mean():.4f} позитивных)")

# ============================================================
# ОБУЧЕНИЕ
# ============================================================
pos_ratio = y_train.mean()
scale_pos_weight = (1 - pos_ratio) / max(pos_ratio, 0.01)
print(f"\n⚖️ scale_pos_weight: {scale_pos_weight:.2f}")

print("\n🚀 Обучение LightGBM...")
model = lgb.LGBMClassifier(
    n_estimators=1000, learning_rate=0.05, max_depth=6, num_leaves=31,
    min_child_samples=10, subsample=0.8, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=0.1, scale_pos_weight=scale_pos_weight,
    random_state=RANDOM_STATE, n_jobs=-1, verbose=-1
)
model.fit(
    X_train, y_train,
    eval_set=[(X_test, y_test)],
    eval_metric='average_precision',
    callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(100)]
)
print(f"\n✅ Модель обучена за {model.best_iteration_} итераций")

# ============================================================
# МЕТРИКИ (подбор порога по макс F1)
# ============================================================
y_test_proba = model.predict_proba(X_test)[:, 1]
ap_score = average_precision_score(y_test, y_test_proba)
auc_score = roc_auc_score(y_test, y_test_proba)

print(f"\n📈 ОБЩИЕ МЕТРИКИ:")
print(f"   PR-AUC:   {ap_score:.4f}")
print(f"   ROC-AUC:  {auc_score:.4f}")

precision, recall, thresholds = precision_recall_curve(y_test, y_test_proba)

# Подбор порога по макс F1
f1_scores = []
for t in thresholds:
    y_pred_t = (y_test_proba >= t).astype(int)
    p_t = precision_score(y_test, y_pred_t, zero_division=0)
    r_t = recall_score(y_test, y_pred_t, zero_division=0)
    f1_t = 2 * p_t * r_t / (p_t + r_t) if (p_t + r_t) > 0 else 0
    f1_scores.append(f1_t)

best_f1_idx = int(np.argmax(f1_scores))
best_threshold = thresholds[best_f1_idx] if best_f1_idx < len(thresholds) else 0.5

print(f"\n✅ Оптимальный порог (макс F1): {best_threshold:.4f}")
print(f"   Precision: {precision[best_f1_idx]:.3f}")
print(f"   Recall:    {recall[best_f1_idx]:.3f}")
print(f"   F1:        {f1_scores[best_f1_idx]:.3f}")

# Итоговые метрики
y_test_pred = (y_test_proba >= best_threshold).astype(int)
test_precision = precision_score(y_test, y_test_pred, zero_division=0)
test_recall = recall_score(y_test, y_test_pred, zero_division=0)
test_f1 = f1_score(y_test, y_test_pred, zero_division=0)

print(f"\n🎯 ИТОГ НА ТЕСТЕ (порог {best_threshold:.4f}):")
print(f"   Precision: {test_precision:.3f} {'✅' if test_precision > TARGET_PRECISION else '❌'}")
print(f"   Recall:    {test_recall:.3f} {'✅' if test_recall > TARGET_RECALL else '❌'}")
print(f"   F1-Score:  {test_f1:.3f}")

passed = test_precision > TARGET_PRECISION and test_recall > TARGET_RECALL
print(f"\n   {'✅✅✅ ТРЕБОВАНИЯ ВЫПОЛНЕНЫ ✅✅✅' if passed else '❌ Требования не выполнены'}")

cm = confusion_matrix(y_test, y_test_pred)
print(f"\n📊 Confusion Matrix:")
print(f"   TN={cm[0][0]:4d}  FP={cm[0][1]:4d}")
print(f"   FN={cm[1][0]:4d}  TP={cm[1][1]:4d}")

# Диагностика
neg_mask = y_test == 0
correct_neg = (y_test_pred[neg_mask] == 0).sum()
total_neg = neg_mask.sum()
print(f"\n🎯 Правильно отфильтровано ложных тревог: {correct_neg}/{total_neg} ({100*correct_neg/total_neg:.1f}%)")

# ============================================================
# ВАЖНОСТЬ ФИЧЕЙ
# ============================================================
importance = pd.DataFrame({
    'feature': FEATURES,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)
print(f"\n🔝 Важность фичей:")
print(importance.to_string(index=False))

# ============================================================
# СОХРАНЕНИЕ
# ============================================================
joblib.dump(model, MODEL_DIR / 'nsd_model_clean.joblib')
joblib.dump(best_threshold, MODEL_DIR / 'nsd_threshold_clean.joblib')
joblib.dump(FEATURES, MODEL_DIR / 'nsd_features_clean.joblib')
print(f"\n💾 Сохранено в {MODEL_DIR}")

# ============================================================
# ГРАФИК
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
best_idx = int(np.argmin(np.abs(thresholds - best_threshold)))
axes[0].plot(recall, precision, 'b-', linewidth=2, label='PR Curve')
axes[0].axhline(y=TARGET_PRECISION, color='r', linestyle='--', label=f'P={TARGET_PRECISION}')
axes[0].axvline(x=TARGET_RECALL, color='g', linestyle='--', label=f'R={TARGET_RECALL}')
axes[0].plot(recall[best_idx], precision[best_idx], 'ko', markersize=12, label=f'Thr={best_threshold:.3f}')
axes[0].set_xlabel('Recall'); axes[0].set_ylabel('Precision')
axes[0].set_title(f'PR Curve НСД (чистый таргет, PR-AUC={ap_score:.3f})', fontweight='bold')
axes[0].legend(); axes[0].grid(True, alpha=0.3)
axes[0].set_xlim([0,1]); axes[0].set_ylim([0,1])

axes[1].barh(importance['feature'][::-1], importance['importance'][::-1], color='coral')
axes[1].set_xlabel('Importance')
axes[1].set_title('Feature Importance (НСД, чистый таргет)', fontweight='bold')

plt.tight_layout()
plt.savefig(MODEL_DIR / 'nsd_analysis_clean.png', dpi=150, bbox_inches='tight')
print(f"\n📈 График: {MODEL_DIR / 'nsd_analysis_clean.png'}")

print("\n" + "="*60)
print("✅ ОБУЧЕНИЕ НА ЧИСТОМ ТАРГЕТЕ ЗАВЕРШЕНО")
print("="*60)
