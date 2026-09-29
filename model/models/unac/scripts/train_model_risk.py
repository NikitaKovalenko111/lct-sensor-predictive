import pandas as pd, numpy as np, joblib
from pathlib import Path
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (average_precision_score, roc_auc_score, precision_recall_curve,
                             precision_score, recall_score, f1_score, confusion_matrix)
import warnings; warnings.filterwarnings('ignore')

DATA = Path(os.environ.get('TRAIN_DATA_ROOT', Path(__file__).resolve().parents[3] / 'dataset/parquets')) / 'unac/unac_risk_dataset.parquet'
MODEL_DIR = Path(os.environ.get('TRAIN_OUTPUT_ROOT', Path(__file__).resolve().parents[3] / 'models')) / 'unac/saved'
MODEL_DIR.mkdir(parents=True, exist_ok=True)
TARGET = 'is_nsd_day'

FEATURES = ['nsd_prev_1d', 'nsd_prev_7d', 'nsd_prev_30d',
            'dow', 'month', 'is_weekend',
            'failures_prev_7d', 'failures_prev_30d',
            'off_guard_prev_7d', 'off_guard_prev_30d']

df = pd.read_parquet(DATA)
df['day'] = pd.to_datetime(df['day']); df['year'] = df['day'].dt.year
X = df[FEATURES].fillna(0); y = df[TARGET].astype(int)
tr, te = df['year'] < 2024, df['year'] >= 2024

m = RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=10,
                           class_weight='balanced', random_state=42, n_jobs=-1)
m.fit(X[tr], y[tr])

p = m.predict_proba(X[te])[:, 1]
ap = average_precision_score(y[te], p); auc = roc_auc_score(y[te], p)
prec, rec, thr = precision_recall_curve(y[te], p)
f1s = [f1_score(y[te], (p >= t).astype(int), zero_division=0) for t in thr]
i = int(np.argmax(f1s))
yp = (p >= thr[i]).astype(int)

print(f"PR-AUC={ap:.4f}  ROC-AUC={auc:.4f}")
print(f"P={precision_score(y[te], yp):.3f}  R={recall_score(y[te], yp):.3f}  F1={f1s[i]:.3f}  thr={thr[i]:.4f}")
print(confusion_matrix(y[te], yp))
print(pd.DataFrame({'f': FEATURES, 'imp': m.feature_importances_}
                   ).sort_values('imp', ascending=False).to_string(index=False))

joblib.dump(m, MODEL_DIR / 'nsd_risk_model.joblib')
joblib.dump(FEATURES, MODEL_DIR / 'nsd_risk_features.joblib')
joblib.dump(float(thr[i]), MODEL_DIR / 'nsd_risk_threshold.joblib')
print("💾 Артефакты финальной риск-модели сохранены")
