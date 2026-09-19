import pandas as pd
import numpy as np
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
import lightgbm as lgb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import joblib
import warnings
warnings.filterwarnings('ignore')

# Попытка импорта продвинутых библиотек
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

try:
    from imblearn.over_sampling import SMOTE
    from imblearn.ensemble import BalancedRandomForestClassifier
    HAS_IMBLEARN = True
except ImportError:
    HAS_IMBLEARN = False
    print("⚠️  imbalanced-learn не установлен: pip install imbalanced-learn")

# ============================================================
# КОНФИГ
# ============================================================
DATA_PATH = Path.cwd() / 'dataset/parquets/unac/unac_risk_dataset.parquet'
MODEL_DIR = Path.cwd() / 'models/unac/saved'
MODEL_DIR.mkdir(exist_ok=True)

FEATURES = [
    'nsd_prev_1d', 'nsd_prev_7d', 'nsd_prev_30d',
    'dow', 'month', 'is_weekend',
    'failures_prev_7d', 'failures_prev_30d',
    'off_guard_prev_7d', 'off_guard_prev_30d'
]
TARGET = 'is_nsd_day'
SPLIT_YEAR = 2024
RANDOM_STATE = 42

# ============================================================
# ЗАГРУЗКА
# ============================================================
print("📂 Загрузка данных риск-скоринга...")
df = pd.read_parquet(DATA_PATH)
df['day'] = pd.to_datetime(df['day'])
df['year'] = df['day'].dt.year

print(f"✅ Загружено {len(df):,} строк")
print(f"   Баланс: {df[TARGET].value_counts().to_dict()}")
print(f"   Доля позитивных: {df[TARGET].mean():.4f}")

# Временной сплит
train_mask = df['year'] < SPLIT_YEAR
test_mask = df['year'] >= SPLIT_YEAR

X_train = df.loc[train_mask, FEATURES].fillna(0)
y_train = df.loc[train_mask, TARGET].astype(int)
X_test = df.loc[test_mask, FEATURES].fillna(0)
y_test = df.loc[test_mask, TARGET].astype(int)

print(f"\n📈 Сплит (граница {SPLIT_YEAR}):")
print(f"   Train: {len(X_train):,} ({y_train.mean():.4f} позитивных)")
print(f"   Test:  {len(X_test):,} ({y_test.mean():.4f} позитивных)")

# Масштабирование для линейных моделей и KNN
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# SMOTE для балансировки (если доступна)
if HAS_IMBLEARN:
    print("\n🔄 Применяем SMOTE для балансировки трейна...")
    smote = SMOTE(random_state=RANDOM_STATE, k_neighbors=5)
    X_train_smote, y_train_smote = smote.fit_resample(X_train, y_train)
    print(f"   После SMOTE: {len(X_train_smote):,} ({y_train_smote.mean():.4f} позитивных)")
else:
    X_train_smote, y_train_smote = X_train, y_train
    print("\n⚠️  SMOTE недоступен, используем несбалансированные данные")

pos_ratio = y_train.mean()
spw = (1 - pos_ratio) / max(pos_ratio, 0.01)

# ============================================================
# ФУНКЦИЯ ОЦЕНКИ
# ============================================================
def evaluate_model(model, X_tr, y_tr, X_te, y_te, name, es=None):
    """Обучает и оценивает модель."""
    try:
        if es == 'lgb':
            model.fit(X_tr, y_tr, eval_X=X_te, eval_y=y_te,
                      eval_metric='average_precision',
                      callbacks=[lgb.early_stopping(100, verbose=False)])
        elif es == 'cat':
            model.fit(X_tr, y_tr, eval_set=(X_te, y_te),
                      early_stopping_rounds=100, verbose=0)
        elif es == 'xgb':
            model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)],
                      early_stopping_rounds=100, verbose=False)
        else:
            model.fit(X_tr, y_tr)
    except Exception as e:
        print(f"    ❌ Ошибка обучения: {e}")
        return None

    try:
        y_proba = model.predict_proba(X_te)[:, 1]
    except Exception as e:
        print(f"    ❌ Ошибка предсказания: {e}")
        return None

    ap = average_precision_score(y_te, y_proba)
    try:
        auc = roc_auc_score(y_te, y_proba)
    except Exception:
        auc = 0.0

    precision, recall, thresholds = precision_recall_curve(y_te, y_proba)
    
    # Макс F1
    f1_scores = [f1_score(y_te, (y_proba >= t).astype(int), zero_division=0) for t in thresholds]
    best_f1_idx = int(np.argmax(f1_scores))
    best_thr = thresholds[best_f1_idx] if best_f1_idx < len(thresholds) else 0.5
    
    y_pred = (y_proba >= best_thr).astype(int)
    p = precision_score(y_te, y_pred, zero_division=0)
    r = recall_score(y_te, y_pred, zero_division=0)
    f1 = f1_score(y_te, y_pred, zero_division=0)
    
    tn, fp, fn, tp = confusion_matrix(y_te, y_pred).ravel()

    return {
        'Модель': name,
        'PR-AUC': round(ap, 4),
        'ROC-AUC': round(auc, 4),
        'Precision': round(p, 4),
        'Recall': round(r, 4),
        'F1': round(f1, 4),
        'Порог': round(best_thr, 4),
        'TP': int(tp), 'FP': int(fp), 'FN': int(fn), 'TN': int(tn)
    }

# ============================================================
# СПИСОК МОДЕЛЕЙ
# ============================================================
results = []

# --- Линейные модели ---
print("\n" + "="*70)
print("📏 ЛИНЕЙНЫЕ МОДЕЛИ")
print("="*70)

print("[1] Logistic Regression (balanced)...")
lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=RANDOM_STATE)
res = evaluate_model(lr, X_train_scaled, y_train, X_test_scaled, y_test, 'LogReg (balanced)')
if res: results.append(res)

print("[2] LDA...")
lda = LinearDiscriminantAnalysis()
res = evaluate_model(lda, X_train_scaled, y_train, X_test_scaled, y_test, 'LDA')
if res: results.append(res)

print("[3] QDA...")
qda = QuadraticDiscriminantAnalysis(reg_param=0.1)
res = evaluate_model(qda, X_train_scaled, y_train, X_test_scaled, y_test, 'QDA')
if res: results.append(res)

# --- KNN ---
print("\n" + "="*70)
print("🔵 K-NEAREST NEIGHBORS")
print("="*70)

for k in [5, 15, 50]:
    print(f"[{4 + [5,15,50].index(k)}] KNN (k={k})...")
    knn = KNeighborsClassifier(n_neighbors=k, n_jobs=-1)
    res = evaluate_model(knn, X_train_scaled, y_train, X_test_scaled, y_test, f'KNN (k={k})')
    if res: results.append(res)

# --- Ансамбли ---
print("\n" + "="*70)
print("🌳 АНСАМБЛИ")
print("="*70)

print("[7] Random Forest (balanced)...")
rf = RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=10,
                            class_weight='balanced', random_state=RANDOM_STATE, n_jobs=-1)
res = evaluate_model(rf, X_train, y_train, X_test, y_test, 'RF (balanced)')
if res: results.append(res)

if HAS_IMBLEARN:
    print("[8] Balanced Random Forest (SMOTE)...")
    brf = BalancedRandomForestClassifier(n_estimators=300, max_depth=10,
                                          random_state=RANDOM_STATE, n_jobs=-1)
    res = evaluate_model(brf, X_train, y_train, X_test, y_test, 'BalancedRF')
    if res: results.append(res)

# --- Градиентные бустинги (с разными настройками) ---
print("\n" + "="*70)
print("🚀 ГРАДИЕНТНЫЕ БУСТИНГИ")
print("="*70)

# LightGBM с SMOTE
if HAS_IMBLEARN:
    print("[9] LightGBM + SMOTE...")
    lgbm_smote = lgb.LGBMClassifier(
        n_estimators=1000, learning_rate=0.05, max_depth=6, num_leaves=31,
        min_child_samples=5, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=0.1,
        random_state=RANDOM_STATE, n_jobs=-1, verbose=-1
    )
    res = evaluate_model(lgbm_smote, X_train_smote, y_train_smote, X_test, y_test, 'LightGBM+SMOTE', es='lgb')
    if res: results.append(res)

# LightGBM с агрессивным scale_pos_weight
print("[10] LightGBM (агрессивный weight)...")
lgbm_agg = lgb.LGBMClassifier(
    n_estimators=1000, learning_rate=0.05, max_depth=6, num_leaves=31,
    min_child_samples=5, subsample=0.8, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=0.1, scale_pos_weight=spw*2,  # удваиваем
    random_state=RANDOM_STATE, n_jobs=-1, verbose=-1
)
res = evaluate_model(lgbm_agg, X_train, y_train, X_test, y_test, 'LightGBM (2x weight)', es='lgb')
if res: results.append(res)

# CatBoost
if HAS_CATBOOST:
    print("[11] CatBoost (balanced)...")
    cat = CatBoostClassifier(iterations=1000, learning_rate=0.05, depth=6,
                             auto_class_weights='Balanced',
                             random_seed=RANDOM_STATE, verbose=0)
    res = evaluate_model(cat, X_train, y_train, X_test, y_test, 'CatBoost', es='cat')
    if res: results.append(res)

# XGBoost
if HAS_XGBOOST:
    print("[12] XGBoost (balanced)...")
    xgb = XGBClassifier(n_estimators=1000, learning_rate=0.05, max_depth=6,
                        scale_pos_weight=spw, subsample=0.8, colsample_bytree=0.8,
                        random_state=RANDOM_STATE, n_jobs=-1)
    res = evaluate_model(xgb, X_train, y_train, X_test, y_test, 'XGBoost', es='xgb')
    if res: results.append(res)

# ============================================================
# ИТОГОВАЯ ТАБЛИЦА
# ============================================================
results_df = pd.DataFrame(results).sort_values('PR-AUC', ascending=False).reset_index(drop=True)

print("\n" + "="*120)
print("📊 ИТОГОВОЕ СРАВНЕНИЕ МОДЕЛЕЙ РИСК-СКОРИНГА")
print("="*120)
print(results_df[['Модель', 'PR-AUC', 'ROC-AUC', 'Precision', 'Recall', 'F1', 'Порог']].to_string(index=True))
print("="*120)

baseline = y_train.mean()
best = results_df.iloc[0]
print(f"\n🏆 Лучшая модель: {best['Модель']}")
print(f"   PR-AUC: {best['PR-AUC']} (baseline: {baseline:.4f}, lift: {best['PR-AUC']/baseline:.2f}x)")
print(f"   Precision: {best['Precision']} | Recall: {best['Recall']} | F1: {best['F1']}")

# ============================================================
# ГРАФИК
# ============================================================
fig, ax = plt.subplots(figsize=(14, 7))
x = np.arange(len(results_df))
width = 0.25
ax.bar(x - width, results_df['PR-AUC'], width, label='PR-AUC', color='steelblue')
ax.bar(x,         results_df['F1'],     width, label='F1', color='coral')
ax.bar(x + width, results_df['Recall'], width, label='Recall', color='green')
ax.axhline(y=baseline, color='red', linestyle='--', linewidth=2, label=f'Baseline {baseline:.4f}')
ax.set_xticks(x)
ax.set_xticklabels(results_df['Модель'], rotation=35, ha='right', fontsize=9)
ax.set_ylabel('Метрика')
ax.set_title('Риск-скоринг НСД: сравнение моделей', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')
ax.set_ylim([0, max(results_df['PR-AUC']) * 1.2])
plt.tight_layout()
plt.savefig(MODEL_DIR / 'risk_model_comparison.png', dpi=150, bbox_inches='tight')
print(f"\n📈 График: {MODEL_DIR / 'risk_model_comparison.png'}")

print("\n✅ Сравнение завершено")