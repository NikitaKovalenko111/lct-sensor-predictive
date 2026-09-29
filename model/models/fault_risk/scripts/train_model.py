import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (average_precision_score, roc_auc_score,
                             precision_recall_curve, precision_score,
                             recall_score, f1_score, confusion_matrix)
from catboost import CatBoostClassifier
import lightgbm as lgb
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
DATA = Path('dataset/parquets/fault_risk/fault_dataset_v2.parquet')
MODEL_DIR = Path('models/fault_risk/saved')
MODEL_DIR.mkdir(parents=True, exist_ok=True)
SPLIT_YEAR = 2024

FEATURES = [
    # Базовые из risk-модели (10)
    'nsd_prev_1d', 'nsd_prev_7d', 'nsd_prev_30d',
    'dow', 'month', 'is_weekend',
    'failures_prev_7d', 'failures_prev_30d',
    'off_guard_prev_7d', 'off_guard_prev_30d',
    # Общие поломочные (4)
    'episodes_prev_7d', 'episodes_prev_30d',
    'fault_channels_prev_1d', 'fault_events_prev_1d',
    # Пер-типовые (4)
    'pump_eps_30d', 'fan_eps_30d', 'ups_eps_30d', 'phase_eps_30d',
    # Свежесть и хроничность (3)
    'days_since_last_episode', 'max_channel_eps_30d', 'repeat_channels_30d',
]

TARGET = 'will_fail_next_24h'

# ============================================================
# ЗАГРУЗКА
# ============================================================
print("=" * 80)
print("📂 ЗАГРУЗКА ДАННЫХ (fault_dataset_v2)")
print("=" * 80)

df = pd.read_parquet(DATA)
df['day'] = pd.to_datetime(df['day'])
df['year'] = df['day'].dt.year

print(f"\n✅ Загружено {len(df):,} строк")
print(f"   Баланс классов: {df[TARGET].value_counts().to_dict()}")
print(f"   Доля позитивных: {df[TARGET].mean():.4f}")
print(f"   Объектов: {df['ид_объект'].nunique()}")
print(f"   Период: {df['day'].min().date()} → {df['day'].max().date()}")
print(f"\n✅ Используем {len(FEATURES)} фичей")

# ============================================================
# СПЛИТ
# ============================================================
print(f"\n📈 Временной сплит (граница {SPLIT_YEAR}):")
train_mask = df['year'] < SPLIT_YEAR - 1
validation_mask = df['year'] == SPLIT_YEAR - 1
test_mask = df['year'] >= SPLIT_YEAR
if not train_mask.any() or not validation_mask.any() or not test_mask.any():
    raise ValueError("dataset must contain separate train, validation and test years")

X_train = df.loc[train_mask, FEATURES].fillna(0)
X_val = df.loc[validation_mask, FEATURES].fillna(0)
X_test = df.loc[test_mask, FEATURES].fillna(0)
y_train = df.loc[train_mask, TARGET]
y_val = df.loc[validation_mask, TARGET]
y_test = df.loc[test_mask, TARGET]

print(f"   Train: {len(X_train):,} записей ({y_train.mean():.4f} позитивных)")
print(f"   Validation: {len(X_val):,} записей ({y_val.mean():.4f} позитивных)")
print(f"   Test:  {len(X_test):,} записей ({y_test.mean():.4f} позитивных)")
print(f"   Позитивных в тесте: {y_test.sum():,}")
print(f"   Негативных в тесте: {(1 - y_test).sum():,}")

scale_pos_weight = (1 - y_train.mean()) / y_train.mean()
print(f"\n⚖️ scale_pos_weight: {scale_pos_weight:.2f}")

# ============================================================
# ОБУЧЕНИЕ КАНДИДАТОВ
# ============================================================
def evaluate(name, model):
    print(f"\n🚀 {name}...")
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_val)[:, 1]
    ap = average_precision_score(y_val, proba)
    auc = roc_auc_score(y_val, proba)
    print(f"   PR-AUC: {ap:.4f}  |  ROC-AUC: {auc:.4f}")
    return model, proba, ap, auc

print("\n" + "=" * 80)
print("🌳 ОБУЧЕНИЕ КАНДИДАТОВ")
print("=" * 80)

candidates = {}

candidates['RF balanced'] = evaluate(
    "Random Forest (balanced)",
    RandomForestClassifier(n_estimators=400, max_depth=11, min_samples_leaf=10,
                           class_weight='balanced', random_state=42, n_jobs=-1)
)

candidates['CatBoost'] = evaluate(
    "CatBoost (balanced)",
    CatBoostClassifier(iterations=600, learning_rate=0.05, depth=7,
                       auto_class_weights='Balanced', random_seed=42, verbose=0)
)

candidates['LightGBM'] = evaluate(
    "LightGBM (scale_pos_weight)",
    lgb.LGBMClassifier(n_estimators=600, learning_rate=0.05, max_depth=7,
                       min_child_samples=10, subsample=0.8, colsample_bytree=0.8,
                       scale_pos_weight=scale_pos_weight, random_state=42,
                       n_jobs=-1, verbose=-1)
)

# ============================================================
# ВЫБОР ЛУЧШЕЙ
# ============================================================
print("\n" + "=" * 80)
print("🏆 ВЫБОР ЛУЧШЕЙ МОДЕЛИ")
print("=" * 80)

results = pd.DataFrame([
    {'Модель': name, 'PR_AUC': round(ap, 4), 'ROC_AUC': round(auc, 4)}
    for name, (_, _, ap, auc) in candidates.items()
]).sort_values('PR_AUC', ascending=False).reset_index(drop=True)

print("\n" + results.to_string())
best_name = results.iloc[0]['Модель']
best_model, proba, ap, auc = candidates[best_name]
base = y_train.mean()
print(f"\n🏆 Лучшая модель: {best_name}")
print(f"   PR-AUC: {ap:.4f} | ROC-AUC: {auc:.4f}")
print(f"   Lift над baseline: {ap / base:.2f}x")

# ============================================================
# ПОРОГ И МЕТРИКИ НА ТЕСТЕ
# ============================================================
print("\n" + "=" * 80)
print(f"📈 МЕТРИКИ НА ТЕСТЕ ({best_name})")
print("=" * 80)

baseline_ap = y_train.mean()
print(f"   PR-AUC:  {ap:.4f}")
print(f"   ROC-AUC: {auc:.4f}")
print(f"   Бейзлайн (частота в трейне): {baseline_ap:.4f}")
print(f"   Lift PR-AUC над бейзлайном: {ap / baseline_ap:.2f}x")

print(f"\n🎯 СТРАТЕГИИ ВЫБОРА ПОРОГА:")
print(f"{'Стратегия':<30} {'Порог':>8} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Алертов':>9}")
print("-" * 80)

prec_arr, rec_arr, thr_arr = precision_recall_curve(y_val, proba)
f1_arr = np.array([f1_score(y_val, (proba >= t).astype(int), zero_division=0)
                   for t in thr_arr])

strategies = {}
# Макс F1
i = int(np.argmax(f1_arr))
strategies['Макс F1'] = thr_arr[i]
# Топ-10% рискованных
strategies['Топ-10% рискованных'] = np.percentile(proba, 90)
# Recall >= 70%
idx_r70 = np.where(rec_arr[:-1] >= 0.70)[0]
strategies['Recall >= 70%'] = thr_arr[idx_r70[np.argmax(f1_arr[idx_r70])]] if len(idx_r70) > 0 else 0.5

best_strat = None
best_f1 = -1
for strat, thr in strategies.items():
    y_pred = (proba >= thr).astype(int)
    p = precision_score(y_val, y_pred, zero_division=0)
    r = recall_score(y_val, y_pred, zero_division=0)
    f1 = f1_score(y_val, y_pred, zero_division=0)
    alerts = int(y_pred.sum())
    print(f"{strat:<30} {thr:>8.4f} {p:>10.3f} {r:>8.3f} {f1:>8.3f} {alerts:>9,}")
    if f1 > best_f1:
        best_f1 = f1
        best_strat = strat
        best_threshold = thr

print(f"\n🎯 ИТОГ ({best_strat}, порог {best_threshold:.4f}):")
proba = best_model.predict_proba(X_test)[:, 1]
ap = average_precision_score(y_test, proba)
auc = roc_auc_score(y_test, proba)
y_pred = (proba >= best_threshold).astype(int)
p = precision_score(y_test, y_pred, zero_division=0)
r = recall_score(y_test, y_pred, zero_division=0)
f1 = f1_score(y_test, y_pred, zero_division=0)
print(f"   Precision: {p:.3f}")
print(f"   Recall:    {r:.3f}")
print(f"   F1:        {f1:.3f}")
print(f"   PR-AUC:    {ap:.4f}")
print(f"   ROC-AUC:   {auc:.4f}")
print(f"   Алертов:   {y_pred.sum():,}")

cm = confusion_matrix(y_test, y_pred)
print(f"\n📊 Confusion Matrix:")
print(f"   TN={cm[0, 0]:,}  FP={cm[0, 1]:,}")
print(f"   FN={cm[1, 0]:,}  TP={cm[1, 1]:,}")

# ============================================================
# ТОП ФИЧЕЙ
# ============================================================
print("\n" + "=" * 80)
print("🔝 ВАЖНОСТЬ ФИЧЕЙ")
print("=" * 80)

if hasattr(best_model, 'feature_importances_'):
    imp = pd.DataFrame({'feature': FEATURES, 'importance': best_model.feature_importances_})
elif hasattr(best_model, 'coef_'):
    imp = pd.DataFrame({'feature': FEATURES, 'importance': np.abs(best_model.coef_[0])})
else:
    imp = None

if imp is not None:
    imp = imp.sort_values('importance', ascending=False).reset_index(drop=True)
    imp['importance'] = imp['importance'].astype(float)
    total = imp['importance'].sum()
    imp['pct'] = (imp['importance'] / total * 100).round(2)

    print("\nТоп-15 фичей:")
    print(f"{'#':>3} {'feature':<30} {'importance':>12} {'доля':>8}")
    print("-" * 60)
    for i, row in imp.head(15).iterrows():
        print(f"{i + 1:>3} {row['feature']:<30} {row['importance']:>12.4f} {row['pct']:>7.2f}%")

    # Нулевая важность
    zero_imp = imp[imp['importance'] == 0]['feature'].tolist()
    if zero_imp:
        print(f"\n⚠️ Фичи с нулевой важностью: {zero_imp}")

# ============================================================
# РАСПРЕДЕЛЕНИЕ ПРЕДСКАЗАНИЙ
# ============================================================
print("\n" + "=" * 80)
print("📊 РАСПРЕДЕЛЕНИЕ ПРЕДСКАЗАНИЙ")
print("=" * 80)
print(f"   Min:           {proba.min():.4f}")
print(f"   10% квантиль:  {np.percentile(proba, 10):.4f}")
print(f"   Медиана:       {np.median(proba):.4f}")
print(f"   90% квантиль:  {np.percentile(proba, 90):.4f}")
print(f"   Max:           {proba.max():.4f}")

# ============================================================
# СОХРАНЕНИЕ
# ============================================================
print("\n" + "=" * 80)
print("💾 СОХРАНЕНИЕ АРТЕФАКТОВ")
print("=" * 80)

joblib.dump(best_model, MODEL_DIR / 'fault_model.joblib')
joblib.dump(float(best_threshold), MODEL_DIR / 'fault_threshold.joblib')
joblib.dump(FEATURES, MODEL_DIR / 'fault_features.joblib')

print(f"\nСохранено в {MODEL_DIR}:")
print(f"   - fault_model.joblib ({best_name})")
print(f"   - fault_threshold.joblib ({best_threshold:.4f})")
print(f"   - fault_features.joblib ({len(FEATURES)} фичей)")

print("\n" + "=" * 80)
print("✅ ОБУЧЕНИЕ МОДЕЛИ ПОЛОМОК ЗАВЕРШЕНО")
print("=" * 80)
