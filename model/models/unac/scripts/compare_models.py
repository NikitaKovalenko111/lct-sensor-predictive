import pandas as pd
import numpy as np
import lightgbm as lgb
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.neighbors import KNeighborsClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    precision_recall_curve, average_precision_score,
    roc_auc_score, confusion_matrix
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import joblib
import warnings
warnings.filterwarnings('ignore')

try:
    from catboost import CatBoostClassifier
    HAS_CATBOOST = True
except ImportError:
    HAS_CATBOOST = False
    print("⚠️  CatBoost не установлен: pip install catboost")

try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    print("⚠️  XGBoost не установлен: pip install xgboost")

# ============================================================
# КОНФИГ
# ============================================================
DATA_PATH = Path.cwd() / 'dataset/parquets/unac/unac_dataset_v3.parquet'
MODEL_DIR = Path.cwd() / 'models/unac/saved'
MODEL_DIR.mkdir(exist_ok=True)
RANDOM_STATE = 42
TEST_SIZE = 0.3
TARGET_COL = 'is_nsd_clean'

BASE_FEATURES = [
    'sensor_type_code',
    'hour', 'dow', 'month', 'is_off_hours',
    'motion_before_30min',
    'cascade_openings_10min'
]
EXTENDED_FEATURES = BASE_FEATURES + ['failures_14d', 'failures_30d']

# ============================================================
# ФУНКЦИЯ ОЦЕНКИ
# ============================================================
def evaluate_model(model, X_train, y_train, X_test, y_test, name, es=None):
    """es: None | 'lgb' | 'cat' | 'xgb' — тип early stopping."""
    if es == 'lgb':
        model.fit(X_train, y_train, eval_X=X_test, eval_y=y_test,
                  eval_metric='average_precision',
                  callbacks=[lgb.early_stopping(100, verbose=False)])
    elif es == 'cat':
        model.fit(X_train, y_train, eval_set=(X_test, y_test),
                  early_stopping_rounds=100, verbose=0)
    elif es == 'xgb':
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)],
                  eval_metric='logloss', early_stopping_rounds=100, verbose=False)
    else:
        model.fit(X_train, y_train)

    y_proba = model.predict_proba(X_test)[:, 1]

    precision, recall, thresholds = precision_recall_curve(y_test, y_proba)
    f1_scores = []
    for t in thresholds:
        yp = (y_proba >= t).astype(int)
        p_t = precision_score(y_test, yp, zero_division=0)
        r_t = recall_score(y_test, yp, zero_division=0)
        f1_scores.append(2*p_t*r_t/(p_t+r_t) if (p_t+r_t) > 0 else 0)

    best_idx = int(np.argmax(f1_scores))
    best_threshold = thresholds[best_idx] if best_idx < len(thresholds) else 0.5

    y_pred = (y_proba >= best_threshold).astype(int)
    test_p = precision_score(y_test, y_pred, zero_division=0)
    test_r = recall_score(y_test, y_pred, zero_division=0)
    test_f1 = f1_score(y_test, y_pred, zero_division=0)
    ap = average_precision_score(y_test, y_proba)
    try:
        auc = roc_auc_score(y_test, y_proba)
    except Exception:
        auc = 0.0

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()

    return {
        'Модель': name,
        'PR-AUC': round(ap, 4),
        'ROC-AUC': round(auc, 4),
        'Precision': round(test_p, 4),
        'Recall': round(test_r, 4),
        'F1': round(test_f1, 4),
        'Порог': round(best_threshold, 4),
        'TP': int(tp), 'FP': int(fp), 'FN': int(fn), 'TN': int(tn),
        'Фильтр ложных': f"{100*tn/(tn+fp):.1f}%" if (tn+fp) > 0 else "N/A"
    }

# ============================================================
# ЗАГРУЗКА ДАННЫХ
# ============================================================
print("📂 Загрузка данных НСД...")
df = pd.read_parquet(DATA_PATH)
print(f"✅ Загружено {len(df):,} строк, баланс: {df[TARGET_COL].value_counts().to_dict()}")

has_failures = 'failures_14d' in df.columns
FEATURES = EXTENDED_FEATURES if has_failures else BASE_FEATURES
print(f"✅ Фичей: {len(FEATURES)} {'(с поломками)' if has_failures else '(базовые)'}")

X = df[FEATURES].fillna(0).astype(float)
y = df[TARGET_COL].astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
)
print(f"Train: {len(X_train):,} | Test: {len(X_test):,}")

pos_ratio = y_train.mean()
spw = (1 - pos_ratio) / max(pos_ratio, 0.01)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

# ============================================================
# СПИСОК МОДЕЛЕЙ: (имя, фабрика, масштабирование?, early stopping?)
# ============================================================
models_to_test = [
    # --- Линейные / дискриминантные ---
    ("Logistic Regression", lambda: LogisticRegression(class_weight='balanced',
        max_iter=1000, random_state=RANDOM_STATE), True, None),
    ("LDA", lambda: LinearDiscriminantAnalysis(), True, None),
    ("QDA", lambda: QuadraticDiscriminantAnalysis(reg_param=0.1), True, None),

    # --- KNN (три варианта k) ---
    ("KNN (k=5)",  lambda: KNeighborsClassifier(n_neighbors=5,  n_jobs=-1), True, None),
    ("KNN (k=15)", lambda: KNeighborsClassifier(n_neighbors=15, n_jobs=-1), True, None),
    ("KNN (k=50)", lambda: KNeighborsClassifier(n_neighbors=50, n_jobs=-1), True, None),

    # --- Ансамбли ---
    ("Random Forest", lambda: RandomForestClassifier(n_estimators=300, max_depth=10,
        min_samples_leaf=20, class_weight='balanced',
        random_state=RANDOM_STATE, n_jobs=-1), False, None),
    ("Gradient Boosting", lambda: GradientBoostingClassifier(n_estimators=200,
        learning_rate=0.05, max_depth=5, subsample=0.8,
        random_state=RANDOM_STATE), False, None),

    # --- Градиентные бустинги ---
    ("LightGBM", lambda: lgb.LGBMClassifier(n_estimators=1000, learning_rate=0.05,
        max_depth=6, num_leaves=31, min_child_samples=10, subsample=0.8,
        colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
        scale_pos_weight=spw, random_state=RANDOM_STATE, n_jobs=-1, verbose=-1),
        False, 'lgb'),
]

if HAS_CATBOOST:
    models_to_test.append(("CatBoost", lambda: CatBoostClassifier(iterations=1000,
        learning_rate=0.05, depth=6, auto_class_weights='Balanced',
        random_seed=RANDOM_STATE, verbose=0), False, 'cat'))

if HAS_XGBOOST:
    models_to_test.append(("XGBoost", lambda: XGBClassifier(n_estimators=1000,
        learning_rate=0.05, max_depth=6, scale_pos_weight=spw, subsample=0.8,
        colsample_bytree=0.8, random_state=RANDOM_STATE, n_jobs=-1), False, 'xgb'))

# ============================================================
# ПРОГОН ВСЕХ МОДЕЛЕЙ
# ============================================================
results = []
trained = {}

for i, (name, factory, use_scaled, es) in enumerate(models_to_test, 1):
    print(f"\n[{i}/{len(models_to_test)}] {name}...")
    try:
        model = factory()
        Xtr = X_train_s if use_scaled else X_train
        Xte = X_test_s if use_scaled else X_test
        res = evaluate_model(model, Xtr, y_train, Xte, y_test, name, es=es)
        results.append(res)
        trained[name] = model
        print(f"    PR-AUC={res['PR-AUC']:.4f}  P={res['Precision']:.3f}  R={res['Recall']:.3f}  F1={res['F1']:.3f}")
    except Exception as e:
        print(f"    ❌ Ошибка: {e}")

# ============================================================
# ИТОГОВАЯ ТАБЛИЦА
# ============================================================
results_df = pd.DataFrame(results).sort_values('PR-AUC', ascending=False).reset_index(drop=True)

print("\n" + "="*120)
print("📊 ИТОГОВОЕ СРАВНЕНИЕ МОДЕЛЕЙ НСД (11 моделей)")
print("="*120)
print(results_df[['Модель', 'PR-AUC', 'ROC-AUC', 'Precision', 'Recall', 'F1',
                  'Порог', 'Фильтр ложных']].to_string(index=True))
print("="*120)

best = results_df.iloc[0]
print(f"\n🏆 Лучшая модель: {best['Модель']}")
print(f"   PR-AUC: {best['PR-AUC']} | P: {best['Precision']} | R: {best['Recall']} | F1: {best['F1']}")

# ============================================================
# ВАЖНОСТЬ ФИЧЕЙ (LightGBM)
# ============================================================
if 'LightGBM' in trained:
    importance = pd.DataFrame({
        'feature': FEATURES,
        'importance': trained['LightGBM'].feature_importances_
    }).sort_values('importance', ascending=False)
    print(f"\n🔝 Важность фичей (LightGBM):")
    print(importance.to_string(index=False))

# ============================================================
# ГРАФИК
# ============================================================
fig, ax = plt.subplots(figsize=(14, 7))
x = np.arange(len(results_df))
width = 0.25
ax.bar(x - width, results_df['PR-AUC'], width, label='PR-AUC', color='steelblue')
ax.bar(x,         results_df['F1'],     width, label='F1', color='coral')
ax.bar(x + width, results_df['Precision'], width, label='Precision', color='green')
ax.set_xticks(x)
ax.set_xticklabels(results_df['Модель'], rotation=35, ha='right', fontsize=9)
ax.set_ylabel('Метрика')
ax.set_title('НСД: сравнение 11 моделей (с признаками поломок)', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')
ax.set_ylim([0, 1.05])
plt.tight_layout()
plt.savefig(MODEL_DIR / 'nsd_model_comparison_full.png', dpi=150, bbox_inches='tight')
print(f"\n📈 График: {MODEL_DIR / 'nsd_model_comparison_full.png'}")

# ============================================================
# СОХРАНЕНИЕ ЛУЧШЕЙ МОДЕЛИ
# ============================================================
best_name = best['Модель']
if best_name in trained:
    joblib.dump(trained[best_name], MODEL_DIR / 'nsd_best_model.joblib')
    joblib.dump(FEATURES, MODEL_DIR / 'nsd_best_features.joblib')
    print(f"💾 Лучшая модель ({best_name}) сохранена")

print("\n✅ Сравнение завершено")