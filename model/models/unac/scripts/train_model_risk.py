import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    precision_recall_curve, average_precision_score,
    roc_auc_score, confusion_matrix
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import joblib
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# ПУТИ
# ============================================================
DATA_PATH = Path.cwd() / 'dataset/parquets/unac/unac_risk_dataset.parquet'
MODEL_DIR = Path.cwd() / 'models/unac/saved'
MODEL_DIR.mkdir(exist_ok=True)

# ============================================================
# ФИЧИ И КОНФИГ
# ============================================================
FEATURES = [
    # Исторические НСД (автокорреляция)
    'nsd_prev_1d', 'nsd_prev_7d', 'nsd_prev_30d',
    # Календарные
    'dow', 'month', 'is_weekend',
    # Поломки
    'failures_prev_7d', 'failures_prev_30d',
    # Снятия с охраны
    'off_guard_prev_7d', 'off_guard_prev_30d'
]
TARGET = 'is_nsd_day'
SPLIT_YEAR = 2024  # трейним до 2024, тестим с 2024
RANDOM_STATE = 42

# ============================================================
# ЗАГРУЗКА
# ============================================================
print("📂 Загрузка данных риск-скоринга...")
df = pd.read_parquet(DATA_PATH)
df['day'] = pd.to_datetime(df['day'])

print(f"\n✅ Загружено {len(df):,} строк")
print(f"   Баланс: {df[TARGET].value_counts().to_dict()}")
print(f"   Доля позитивных: {df[TARGET].mean():.4f}")
print(f"   Объектов: {df['ид_объект'].nunique()}")
print(f"   Период: {df['day'].min().date()} → {df['day'].max().date()}")

# ============================================================
# ВРЕМЕННОЙ СПЛИТ (критично для временных рядов!)
# ============================================================
df['year'] = df['day'].dt.year

train_mask = df['year'] < SPLIT_YEAR
test_mask = df['year'] >= SPLIT_YEAR

X_train = df.loc[train_mask, FEATURES].fillna(0)
y_train = df.loc[train_mask, TARGET].astype(int)
X_test = df.loc[test_mask, FEATURES].fillna(0)
y_test = df.loc[test_mask, TARGET].astype(int)

print(f"\n📈 Временной сплит (граница {SPLIT_YEAR}):")
print(f"   Train (<{SPLIT_YEAR}): {len(X_train):,} ({y_train.mean():.4f} позитивных, {y_train.sum()} дней с НСД)")
print(f"   Test  (>={SPLIT_YEAR}): {len(X_test):,} ({y_test.mean():.4f} позитивных, {y_test.sum()} дней с НСД)")

if y_test.sum() == 0:
    print("\n❌ В тесте нет позитивных примеров!")
    exit()

# ============================================================
# ОБУЧЕНИЕ
# ============================================================
pos_ratio = y_train.mean()
spw = (1 - pos_ratio) / max(pos_ratio, 0.01)
print(f"\n⚖️ scale_pos_weight: {spw:.2f}")

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
    scale_pos_weight=spw,
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
# МЕТРИКИ
# ============================================================
y_proba = model.predict_proba(X_test)[:, 1]

ap = average_precision_score(y_test, y_proba)
auc = roc_auc_score(y_test, y_proba)

print(f"\n📈 ОБЩИЕ МЕТРИКИ:")
print(f"   PR-AUC:  {ap:.4f}")
print(f"   ROC-AUC: {auc:.4f}")

# Бейзлайн (частота позитивов в трейне)
baseline = y_train.mean()
print(f"   Бейзлайн (частота в трейне): {baseline:.4f}")
print(f"   Lift PR-AUC над бейзлайном: {ap/baseline:.2f}x")

# ============================================================
# ТРИ СТРАТЕГИИ ВЫБОРА ПОРОГА
# ============================================================
precision, recall, thresholds = precision_recall_curve(y_test, y_proba)

# Стратегия 1: Макс F1
f1_scores = [f1_score(y_test, (y_proba >= t).astype(int), zero_division=0) 
             for t in thresholds]
best_f1_idx = int(np.argmax(f1_scores))
thr_f1 = thresholds[best_f1_idx]

# Стратегия 2: Топ-10% самых рискованных дней
top_k = int(len(y_proba) * 0.10)
thr_top10 = np.sort(y_proba)[-top_k] if top_k > 0 else 0.5

# Стратегия 3: Фиксированный Recall 80%
target_recall = 0.80
valid_recall = [(p, r, t) for p, r, t in zip(precision, recall, thresholds)
                if r >= target_recall]
if valid_recall:
    best_recall_choice = max(valid_recall, key=lambda x: x[0])  # макс Precision при R>=80%
    thr_recall80 = best_recall_choice[2]
else:
    thr_recall80 = thr_f1

# Сравниваем стратегии
print(f"\n🎯 СРАВНЕНИЕ СТРАТЕГИЙ ВЫБОРА ПОРОГА:")
print(f"{'Стратегия':<30} {'Порог':<10} {'Precision':<12} {'Recall':<10} {'F1':<10}")
print("-" * 80)

for name, thr in [
    ('Макс F1', thr_f1),
    ('Топ-10% рискованных', thr_top10),
    ('Recall >= 80%', thr_recall80)
]:
    y_pred = (y_proba >= thr).astype(int)
    p = precision_score(y_test, y_pred, zero_division=0)
    r = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    n_alerts = y_pred.sum()
    print(f"{name:<30} {thr:<10.4f} {p:<12.3f} {r:<10.3f} {f1:<10.3f}  (алертов: {n_alerts})")

# Используем макс F1 как основной порог
best_threshold = thr_f1

# ============================================================
# ИТОГОВЫЕ МЕТРИКИ НА ВЫБРАННОМ ПОРОГЕ
# ============================================================
y_pred = (y_proba >= best_threshold).astype(int)
test_p = precision_score(y_test, y_pred, zero_division=0)
test_r = recall_score(y_test, y_pred, zero_division=0)
test_f1 = f1_score(y_test, y_pred, zero_division=0)

print(f"\n🎯 ИТОГ (порог {best_threshold:.4f}):")
print(f"   Precision: {test_p:.3f}")
print(f"   Recall:    {test_r:.3f}")
print(f"   F1:        {test_f1:.3f}")

tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
print(f"\n📊 Confusion Matrix:")
print(f"   TN={tn:5d}  FP={fp:5d}")
print(f"   FN={fn:5d}  TP={tp:5d}")

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
# АНАЛИЗ ПО ОБЪЕКТАМ: топ рискованных
# ============================================================
df_test = df[test_mask].copy()
df_test['risk_proba'] = y_proba

object_risk = df_test.groupby('ид_объект').agg(
    avg_risk=('risk_proba', 'mean'),
    max_risk=('risk_proba', 'max'),
    total_days=('day', 'count'),
    nsd_days=(TARGET, 'sum')
).sort_values('avg_risk', ascending=False)

print(f"\n🏢 Топ-10 объектов по среднему риску (тест):")
print(object_risk.head(10).to_string())

# ============================================================
# СОХРАНЕНИЕ
# ============================================================
joblib.dump(model, MODEL_DIR / 'nsd_risk_model.joblib')
joblib.dump(best_threshold, MODEL_DIR / 'nsd_risk_threshold.joblib')
joblib.dump(FEATURES, MODEL_DIR / 'nsd_risk_features.joblib')

print(f"\n💾 Сохранено в {MODEL_DIR}:")
print(f"   - nsd_risk_model.joblib")
print(f"   - nsd_risk_threshold.joblib ({best_threshold:.4f})")
print(f"   - nsd_risk_features.joblib")

# ============================================================
# ГРАФИКИ
# ============================================================
fig, axes = plt.subplots(2, 2, figsize=(16, 12))

# 1. PR Curve
best_idx = int(np.argmin(np.abs(thresholds - best_threshold)))
axes[0, 0].plot(recall, precision, 'b-', linewidth=2, label='PR Curve')
axes[0, 0].axhline(y=baseline, color='r', linestyle='--', label=f'Бейзлайн {baseline:.3f}')
axes[0, 0].plot(recall[best_idx], precision[best_idx], 'ko', markersize=12,
                label=f'Threshold={best_threshold:.3f}')
axes[0, 0].set_xlabel('Recall', fontsize=12)
axes[0, 0].set_ylabel('Precision', fontsize=12)
axes[0, 0].set_title(f'PR Curve (PR-AUC={ap:.3f})', fontsize=14, fontweight='bold')
axes[0, 0].legend()
axes[0, 0].grid(True, alpha=0.3)

# 2. Feature Importance
axes[0, 1].barh(importance['feature'][::-1], importance['importance'][::-1], color='steelblue')
axes[0, 1].set_xlabel('Importance')
axes[0, 1].set_title('Feature Importance', fontweight='bold')

# 3. Распределение предсказаний
axes[1, 0].hist(y_proba[y_test == 0], bins=50, alpha=0.6, label='Без НСД', color='blue')
axes[1, 0].hist(y_proba[y_test == 1], bins=50, alpha=0.6, label='С НСД', color='red')
axes[1, 0].axvline(x=best_threshold, color='black', linestyle='--', label=f'Порог')
axes[1, 0].set_xlabel('Вероятность НСД')
axes[1, 0].set_ylabel('Количество дней')
axes[1, 0].set_title('Распределение предсказаний', fontweight='bold')
axes[1, 0].legend()
axes[1, 0].grid(True, alpha=0.3)

# 4. Топ объектов по риску
top10 = object_risk.head(10)
axes[1, 1].barh([str(o) for o in top10.index][::-1], top10['avg_risk'][::-1], color='coral')
axes[1, 1].set_xlabel('Средний риск НСД')
axes[1, 1].set_title('Топ-10 объектов по риску', fontweight='bold')

plt.tight_layout()
plt.savefig(MODEL_DIR / 'nsd_risk_analysis.png', dpi=150, bbox_inches='tight')
print(f"\n📈 График: {MODEL_DIR / 'nsd_risk_analysis.png'}")

print("\n" + "="*60)
print("✅ ОБУЧЕНИЕ МОДЕЛИ РИСК-СКОРИНГА ЗАВЕРШЕНО")
print("="*60)