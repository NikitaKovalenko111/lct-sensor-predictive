import pandas as pd, numpy as np, warnings
from pathlib import Path
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.neighbors import KNeighborsClassifier
from sklearn.ensemble import RandomForestClassifier
from imblearn.ensemble import BalancedRandomForestClassifier
from imblearn.over_sampling import SMOTE
from catboost import CatBoostClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import (average_precision_score, roc_auc_score,
                             precision_recall_curve, precision_score, recall_score, f1_score)
warnings.filterwarnings('ignore')

DATA = Path('dataset/parquets/fault_risk/fault_dataset.parquet')
TARGET = 'will_fail_next_24h'
FEATURES = [
    'nsd_prev_1d', 'nsd_prev_7d', 'nsd_prev_30d',
    'dow', 'month', 'is_weekend',
    'failures_prev_7d', 'failures_prev_30d',
    'off_guard_prev_7d', 'off_guard_prev_30d',
    'episodes_prev_7d', 'episodes_prev_30d',
    'fault_channels_prev_1d', 'fault_events_prev_1d',
]

df = pd.read_parquet(DATA)
df['day'] = pd.to_datetime(df['day']); df['year'] = df['day'].dt.year
X = df[FEATURES].fillna(0); y = df[TARGET].astype(int)
tr, te = df['year'] < 2024, df['year'] >= 2024
X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]
spw = (1 - y_tr.mean()) / y_tr.mean()
print(f"Train {len(X_tr):,} ({y_tr.mean():.4f}) | Test {len(X_te):,} ({y_te.mean():.4f})\n")

rows = []
def evaluate(name, model, use_smote=False):
    Xs, ys = SMOTE(random_state=42).fit_resample(X_tr, y_tr) if use_smote else (X_tr, y_tr)
    model.fit(Xs, ys)
    p = model.predict_proba(X_te)[:, 1]
    ap, auc = average_precision_score(y_te, p), roc_auc_score(y_te, p)
    prec, rec, thr = precision_recall_curve(y_te, p)
    f1s = np.nan_to_num([f1_score(y_te, (p >= t).astype(int), zero_division=0) for t in thr])
    i = int(np.argmax(f1s)); t = float(thr[i])
    P = precision_score(y_te, (p >= t).astype(int), zero_division=0)
    R = recall_score(y_te, (p >= t).astype(int), zero_division=0)
    rows.append(dict(Модель=name, PR_AUC=round(ap, 4), ROC_AUC=round(auc, 4),
                     Precision=round(P, 3), Recall=round(R, 3), F1=round(float(f1s[i]), 3),
                     Порог=round(t, 4)))
    print(f"{name:26s} PR-AUC={ap:.4f}  ROC={auc:.4f}  P={P:.3f}  R={R:.3f}  F1={f1s[i]:.3f}")

print("=" * 100)
print("📏 ЛИНЕЙНЫЕ")
evaluate('LogReg (balanced)', make_pipeline(StandardScaler(),
         LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42)))
evaluate('LDA', make_pipeline(StandardScaler(), LinearDiscriminantAnalysis()))
evaluate('QDA', QuadraticDiscriminantAnalysis())

print("🔵 KNN")
evaluate('KNN (k=50)',  make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=50)))
evaluate('KNN (k=200)', make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=200)))

print("🌳 АНСАМБЛИ")
evaluate('RF (balanced)', RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=10,
         class_weight='balanced', random_state=42, n_jobs=-1))
evaluate('BalancedRF', BalancedRandomForestClassifier(n_estimators=300, max_depth=10,
         random_state=42, n_jobs=-1))

print("🚀 БУСТИНГИ")
evaluate('LightGBM+SMOTE', lgb.LGBMClassifier(n_estimators=500, learning_rate=0.05, max_depth=6,
         min_child_samples=10, subsample=0.8, colsample_bytree=0.8,
         random_state=42, n_jobs=-1, verbose=-1), use_smote=True)
evaluate('LightGBM (spw)', lgb.LGBMClassifier(n_estimators=500, learning_rate=0.05, max_depth=6,
         min_child_samples=10, subsample=0.8, colsample_bytree=0.8, scale_pos_weight=spw,
         random_state=42, n_jobs=-1, verbose=-1))
evaluate('CatBoost (balanced)', CatBoostClassifier(iterations=500, learning_rate=0.05, depth=6,
         auto_class_weights='Balanced', random_state=42, verbose=0))
evaluate('XGBoost (spw)', XGBClassifier(n_estimators=500, learning_rate=0.05, max_depth=6,
         subsample=0.8, colsample_bytree=0.8, scale_pos_weight=spw,
         random_state=42, n_jobs=-1, eval_metric='auc'))   # без early_stopping в fit — обходим старый баг

res = pd.DataFrame(rows).sort_values('PR_AUC', ascending=False).reset_index(drop=True)
print("\n" + "=" * 100)
print(res.to_string())
base = y_tr.mean()
print(f"\nBaseline (частота трейна): {base:.4f} | Lift лучшей: {res.PR_AUC[0] / base:.2f}x")