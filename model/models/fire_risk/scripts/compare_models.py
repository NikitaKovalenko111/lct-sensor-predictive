import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    precision_recall_curve, confusion_matrix,
    average_precision_score, roc_auc_score
)
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import joblib
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# ОПЦИОНАЛЬНЫЕ ИМПОРТЫ
# ============================================================
try:
    from catboost import CatBoostClassifier
    HAS_CATBOOST = True
except ImportError:
    HAS_CATBOOST = False
    print("⚠️  CatBoost не установлен: pip install catboost")

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("⚠️  XGBoost не установлен: pip install xgboost")

# ============================================================
# ПУТИ И КОНФИГ
# ============================================================
DATA_PATH = Path.cwd() / 'dataset/parquets/fire_risk/fire_risk_dataset_v2.parquet'
MODEL_DIR = Path.cwd() / 'models'
MODEL_DIR.mkdir(exist_ok=True)

TARGET_PRECISION = 0.7
TARGET_RECALL = 0.5

# ============================================================
# ФИЧИ
# ============================================================
# ПОЛНЫЙ НАБОР (47) — для baseline-сравнения
FULL_FEATURES = [
    'alarms_1h', 'alarms_3h', 'alarms_6h', 'alarms_12h', 'alarms_24h',
    'alarm_channels_24h', 'alarm_types_24h',
    'baseline_alarms_1h', 'baseline_alarms_6h', 'baseline_alarms_24h',
    'ratio_1h', 'ratio_6h', 'ratio_24h',
    'log_ratio_1h', 'log_ratio_6h', 'log_ratio_24h',
    'motion_1h', 'motion_6h', 'motion_24h',
    'total_events_1h', 'total_events_24h',
    'baseline_motion_1h', 'baseline_motion_6h', 'baseline_motion_24h',
    'motion_ratio_1h', 'motion_ratio_6h', 'motion_ratio_24h',
    'temp_avg_6h', 'temp_max_6h', 'temp_avg_24h', 'temp_max_24h',
    'baseline_temp_6h', 'baseline_temp_24h',
    'temp_diff_6h', 'temp_max_diff_6h',
    'flood_24h', 'flood_6h', 'hatch_24h', 'glass_24h',
    'fan_24h', 'door_24h', 'pump_24h',
    'hour', 'dow', 'month', 'is_night', 'is_weekend'
]

# МИНИМАЛЬНЫЙ НАБОР (34) — БЕЗ baseline, БЕЗ ratio, БЕЗ линейных комбинаций
# Только: абсолюты + log_ratio + предвестники + время
MINIMAL_FEATURES = [
    # Тревоги (абсолюты)
    'alarms_1h', 'alarms_3h', 'alarms_6h', 'alarms_12h', 'alarms_24h',
    'alarm_channels_24h', 'alarm_types_24h',
    # Отношения (ТОЛЬКО логарифмы)
    'log_ratio_1h', 'log_ratio_6h', 'log_ratio_24h',
    # Движение (абсолюты + отношения)
    'motion_1h', 'motion_6h', 'motion_24h',
    'total_events_1h', 'total_events_24h',
    'motion_ratio_1h', 'motion_ratio_6h', 'motion_ratio_24h',
    # Температура (только абсолюты, БЕЗ baseline и разностей)
    'temp_avg_6h', 'temp_max_6h', 'temp_avg_24h', 'temp_max_24h',
    # Предвестники
    'flood_24h', 'flood_6h', 'hatch_24h', 'glass_24h',
    'fan_24h', 'door_24h', 'pump_24h',
    # Временные
    'hour', 'dow', 'month', 'is_night', 'is_weekend'
]

# ============================================================
# ЗАГРУЗКА ДАННЫХ
# ============================================================
print("📂 Загрузка данных...")
df = pd.read_parquet(DATA_PATH)
df['ts'] = pd.to_datetime(df['ts'])
print(f"✅ Загружено {len(df):,} строк")
print(f"   Баланс: {df['is_incident'].value_counts().to_dict()}")

# Проверяем, что все минимальные фичи есть
missing_minimal = [f for f in MINIMAL_FEATURES if f not in df.columns]
if missing_minimal:
    print(f"\n⚠️  Отсутствуют в минимальном наборе: {missing_minimal}")
    print("   (возможно, нужно пересоздать датасет)")

X_full = df[FULL_FEATURES].fillna(0).astype(float)
X_min = df[MINIMAL_FEATURES].fillna(0).astype(float)
y = df['is_incident'].astype(int)

# ============================================================
# СПЛИТ (один общий, стратифицированный)
# ============================================================
Xf_train, Xf_test, y_train, y_test = train_test_split(
    X_full, y, test_size=0.3, random_state=42, stratify=y
)
Xm_train, Xm_test, _, _ = train_test_split(
    X_min, y, test_size=0.3, random_state=42, stratify=y
)

print(f"\n📈 Стратифицированный сплит:")
print(f"   Train: {len(Xf_train):,} ({y_train.mean():.4f} позитивных)")
print(f"   Test:  {len(Xf_test):,} ({y_test.mean():.4f} позитивных)")
print(f"   Позитивных в тесте: {y_test.sum()}")
print(f"   Негативных в тесте: {(y_test == 0).sum()}")

pos_ratio = y_train.mean()
scale_pos_weight = (1 - pos_ratio) / max(pos_ratio, 0.01)
print(f"\n⚖️ scale_pos_weight: {scale_pos_weight:.2f}")

# ============================================================
# ФУНКЦИЯ ОЦЕНКИ
# ============================================================
def evaluate_model(model, X_test, y_test, model_name):
    y_proba = model.predict_proba(X_test)[:, 1]
    ap = average_precision_score(y_test, y_proba)
    try:
        auc = roc_auc_score(y_test, y_proba)
    except Exception:
        auc = 0.0

    precision, recall, thresholds = precision_recall_curve(y_test, y_proba)
    valid = [(p, r, t) for p, r, t in zip(precision, recall, thresholds)
             if p >= TARGET_PRECISION and r >= TARGET_RECALL]

    if valid:
        best_p, best_r, best_t = max(valid, key=lambda x: x[1])
    else:
        dist = [(p - TARGET_PRECISION)**2 + (r - TARGET_RECALL)**2
                for p, r in zip(precision, recall)]
        idx = int(np.argmin(dist))
        best_t = thresholds[idx] if idx < len(thresholds) else 0.5
        best_p = precision[idx]
        best_r = recall[idx]

    y_pred = (y_proba >= best_t).astype(int)
    p = precision_score(y_test, y_pred, zero_division=0)
    r = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred)
    tn = cm[0][0]
    total_neg = (y_test == 0).sum()
    spec = tn / total_neg if total_neg > 0 else 0

    return {
        'Model': model_name,
        'PR-AUC': round(ap, 4),
        'ROC-AUC': round(auc, 4),
        'Precision': round(p, 4),
        'Recall': round(r, 4),
        'F1': round(f1, 4),
        'Specificity': round(spec, 4),
        'Threshold': round(best_t, 4),
        'Passed': '✅' if p > TARGET_PRECISION and r > TARGET_RECALL else '❌',
        '_proba': y_proba,
        '_threshold': best_t
    }

results = []

# ============================================================
# 1. LightGBM (полный набор, 47 фичей)
# ============================================================
print("\n🌲 [1/6] LightGBM (full 47)...")
lgb_full = lgb.LGBMClassifier(
    n_estimators=1000, learning_rate=0.05, max_depth=6, num_leaves=31,
    min_child_samples=10, subsample=0.8, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=0.1, scale_pos_weight=scale_pos_weight,
    random_state=42, n_jobs=-1, verbose=-1
)
lgb_full.fit(Xf_train, y_train, eval_X=Xf_test, eval_y=y_test,
             eval_metric='average_precision',
             callbacks=[lgb.early_stopping(100, verbose=False)])
print(f"   итераций: {lgb_full.best_iteration_}")
results.append(evaluate_model(lgb_full, Xf_test, y_test, 'LightGBM (full 47)'))

# ============================================================
# 2. LightGBM (минимальный набор, 34 фичи)
# ============================================================
print("\n🌲 [2/6] LightGBM (minimal 34)...")
lgb_min = lgb.LGBMClassifier(
    n_estimators=1000, learning_rate=0.05, max_depth=6, num_leaves=31,
    min_child_samples=10, subsample=0.8, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=0.1, scale_pos_weight=scale_pos_weight,
    random_state=42, n_jobs=-1, verbose=-1
)
lgb_min.fit(Xm_train, y_train, eval_X=Xm_test, eval_y=y_test,
            eval_metric='average_precision',
            callbacks=[lgb.early_stopping(100, verbose=False)])
print(f"   итераций: {lgb_min.best_iteration_}")
results.append(evaluate_model(lgb_min, Xm_test, y_test, 'LightGBM (minimal 34)'))

# ============================================================
# 3. CatBoost (минимальный набор)
# ============================================================
if HAS_CATBOOST:
    print("\n🐱 [3/6] CatBoost (minimal 34)...")
    cat_model = CatBoostClassifier(
        iterations=1000, learning_rate=0.05, depth=6,
        auto_class_weights='Balanced',
        random_seed=42, verbose=0, early_stopping_rounds=100
    )
    cat_model.fit(Xm_train, y_train, eval_set=(Xm_test, y_test), verbose=0)
    print(f"   итераций: {cat_model.best_iteration_}")
    results.append(evaluate_model(cat_model, Xm_test, y_test, 'CatBoost (minimal 34)'))

# ============================================================
# 4. XGBoost (минимальный набор)
# ============================================================
if HAS_XGB:
    print("\n⚡ [4/6] XGBoost (minimal 34)...")
    xgb_model = XGBClassifier(
        n_estimators=1000, learning_rate=0.05, max_depth=6,
        scale_pos_weight=scale_pos_weight,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1,
        random_state=42, n_jobs=-1,
        eval_metric='aucpr', early_stopping_rounds=100
    )
    xgb_model.fit(Xm_train, y_train, eval_set=[(Xm_test, y_test)], verbose=False)
    print(f"   итераций: {xgb_model.best_iteration}")
    results.append(evaluate_model(xgb_model, Xm_test, y_test, 'XGBoost (minimal 34)'))

# ============================================================
# 5. Random Forest (минимальный набор)
# ============================================================
print("\n🌳 [5/6] RandomForest (minimal 34)...")
rf_model = RandomForestClassifier(
    n_estimators=500, max_depth=10, min_samples_leaf=10,
    class_weight='balanced', random_state=42, n_jobs=-1
)
rf_model.fit(Xm_train, y_train)
results.append(evaluate_model(rf_model, Xm_test, y_test, 'RandomForest (minimal 34)'))

# ============================================================
# 6. Logistic Regression (минимальный набор)
# ============================================================
print("\n📏 [6/6] Logistic Regression (minimal 34)...")
scaler = StandardScaler()
Xm_train_scaled = scaler.fit_transform(Xm_train)
Xm_test_scaled = scaler.transform(Xm_test)
lr_model = LogisticRegression(
    class_weight='balanced', max_iter=1000, random_state=42
)
lr_model.fit(Xm_train_scaled, y_train)
results.append(evaluate_model(lr_model, Xm_test_scaled, y_test, 'LogReg (minimal 34)'))

# ============================================================
# ИТОГОВАЯ ТАБЛИЦА
# ============================================================
results_df = pd.DataFrame([{
    k: v for k, v in r.items() if not k.startswith('_')
} for r in results])
results_df = results_df.sort_values('PR-AUC', ascending=False)

print("\n" + "="*100)
print("📊 СРАВНЕНИЕ МОДЕЛЕЙ")
print("="*100)
print(results_df.to_string(index=False))
print("="*100)

# ============================================================
# ВАЖНОСТЬ ФИЧЕЙ — сравнение full vs minimal
# ============================================================
imp_full = pd.DataFrame({
    'feature': FULL_FEATURES,
    'importance': lgb_full.feature_importances_
}).sort_values('importance', ascending=False)

imp_min = pd.DataFrame({
    'feature': MINIMAL_FEATURES,
    'importance': lgb_min.feature_importances_
}).sort_values('importance', ascending=False)

print("\n🔝 Топ-15 фичей (LightGBM full 47):")
print(imp_full.head(15).to_string(index=False))

print("\n🔝 Топ-15 фичей (LightGBM minimal 34):")
print(imp_min.head(15).to_string(index=False))

# Фичи с нулевой важностью
zero_imp = imp_full[imp_full['importance'] == 0]['feature'].tolist()
if zero_imp:
    print(f"\n⚠️  Фичи с нулевой важностью в full ({len(zero_imp)}):")
    for f in zero_imp:
        marker = "🗑️" if f not in MINIMAL_FEATURES else "⚠️"
        print(f"   {marker} {f}")
    print("   🗑️ — НЕ в минимальном наборе (правильно убраны)")
    print("   ⚠️ — В минимальном наборе, но бесполезны (можно убрать)")

# ============================================================
# ГРАФИК 1: Сравнение моделей (bar chart)
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(18, 7))

# Bar chart: PR-AUC vs ROC-AUC
x_pos = range(len(results_df))
width = 0.35
bars1 = axes[0].bar([i - width/2 for i in x_pos], results_df['PR-AUC'],
                    width, label='PR-AUC', color='steelblue')
bars2 = axes[0].bar([i + width/2 for i in x_pos], results_df['ROC-AUC'],
                    width, label='ROC-AUC', color='coral')
axes[0].set_xticks(x_pos)
axes[0].set_xticklabels(results_df['Model'], rotation=35, ha='right', fontsize=9)
axes[0].set_ylabel('Score')
axes[0].set_title('Качество моделей: PR-AUC и ROC-AUC', fontweight='bold')
axes[0].legend()
axes[0].grid(True, alpha=0.3, axis='y')
axes[0].set_ylim([0, 1.05])
for bar in bars1:
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f'{bar.get_height():.3f}', ha='center', fontsize=8)
for bar in bars2:
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f'{bar.get_height():.3f}', ha='center', fontsize=8)

# Precision vs Recall vs F1
metrics = ['Precision', 'Recall', 'F1']
x_pos2 = range(len(results_df))
width2 = 0.25
colors = ['steelblue', 'coral', 'green']
for i, (metric, color) in enumerate(zip(metrics, colors)):
    bars = axes[1].bar([x + i*width2 for x in x_pos2], results_df[metric],
                       width2, label=metric, color=color)
axes[1].set_xticks([x + width2 for x in x_pos2])
axes[1].set_xticklabels(results_df['Model'], rotation=35, ha='right', fontsize=9)
axes[1].set_ylabel('Score')
axes[1].set_title('Precision / Recall / F1', fontweight='bold')
axes[1].legend()
axes[1].grid(True, alpha=0.3, axis='y')
axes[1].set_ylim([0, 1.05])

plt.tight_layout()
plt.savefig(MODEL_DIR / 'model_comparison.png', dpi=150, bbox_inches='tight')
print(f"\n📈 График 1: {MODEL_DIR / 'model_comparison.png'}")

# ============================================================
# ГРАФИК 2: Feature Importance full vs minimal
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(18, 8))

axes[0].barh(imp_full['feature'][:15][::-1],
             imp_full['importance'][:15][::-1], color='steelblue')
axes[0].set_xlabel('Importance')
axes[0].set_title('Top-15 (LightGBM full 47)', fontweight='bold')

axes[1].barh(imp_min['feature'][:15][::-1],
             imp_min['importance'][:15][::-1], color='coral')
axes[1].set_xlabel('Importance')
axes[1].set_title('Top-15 (LightGBM minimal 34)', fontweight='bold')

plt.tight_layout()
plt.savefig(MODEL_DIR / 'feature_importance_comparison.png', dpi=150, bbox_inches='tight')
print(f"📈 График 2: {MODEL_DIR / 'feature_importance_comparison.png'}")

# ============================================================
# ВЫБОР И СОХРАНЕНИЕ ЛУЧШЕЙ МОДЕЛИ
# ============================================================
best_model_name = results_df.iloc[0]['Model']
best_model_info = next(r for r in results if r['Model'] == best_model_name)

print(f"\n🏆 Лучшая модель: {best_model_name}")
print(f"   PR-AUC:    {best_model_info['PR-AUC']}")
print(f"   Precision: {best_model_info['Precision']}")
print(f"   Recall:    {best_model_info['Recall']}")
print(f"   F1:        {best_model_info['F1']}")

# Определяем, какой набор фичей использовать
if 'minimal' in best_model_name.lower() or 'minimal' in best_model_name:
    final_features = MINIMAL_FEATURES
    features_label = "minimal_34"
else:
    final_features = FULL_FEATURES
    features_label = "full_47"

# Определяем, какую модель сохранять
if 'LightGBM' in best_model_name and 'full' in best_model_name:
    best_model_obj = lgb_full
elif 'LightGBM' in best_model_name:
    best_model_obj = lgb_min
elif HAS_CATBOOST and 'CatBoost' in best_model_name:
    best_model_obj = cat_model
elif HAS_XGB and 'XGBoost' in best_model_name:
    best_model_obj = xgb_model
elif 'RandomForest' in best_model_name:
    best_model_obj = rf_model
else:
    best_model_obj = lr_model

# Сохранение
joblib.dump(best_model_obj, MODEL_DIR / 'best_model.joblib')
joblib.dump(best_model_info['_threshold'], MODEL_DIR / 'best_threshold.joblib')
joblib.dump(final_features, MODEL_DIR / 'best_features.joblib')

print(f"\n💾 Сохранено в {MODEL_DIR}:")
print(f"   - best_model.joblib")
print(f"   - best_threshold.joblib ({best_model_info['_threshold']:.4f})")
print(f"   - best_features.joblib ({features_label}, {len(final_features)} фичей)")

# ============================================================
# СВОДКА: сравнение full vs minimal для LightGBM
# ============================================================
lgb_full_res = next(r for r in results if r['Model'] == 'LightGBM (full 47)')
lgb_min_res = next(r for r in results if r['Model'] == 'LightGBM (minimal 34)')

print("\n" + "="*100)
print("🔍 СРАВНЕНИЕ: full 47 vs minimal 34 (LightGBM)")
print("="*100)
print(f"{'Метрика':<20} {'Full (47)':<15} {'Minimal (34)':<15} {'Δ':<15}")
print("-"*100)
for m in ['PR-AUC', 'ROC-AUC', 'Precision', 'Recall', 'F1', 'Specificity']:
    v_full = lgb_full_res[m]
    v_min = lgb_min_res[m]
    delta = v_min - v_full
    sign = '+' if delta >= 0 else ''
    print(f"{m:<20} {v_full:<15.4f} {v_min:<15.4f} {sign}{delta:<15.4f}")
print("="*100)

if all(abs(lgb_min_res[m] - lgb_full_res[m]) < 0.01 for m in ['PR-AUC', 'ROC-AUC']):
    print("\n✅ МИНИМАЛЬНЫЙ НАБОР РАБОТАЕТ НЕ ХУЖЕ!")
    print("   → Рекомендуем использовать 34 фичи в продакшене")
else:
    print("\n⚠️  Есть заметная разница — выбирайте по балансу метрик и сложности")

print("\n✅ Сравнение завершено")