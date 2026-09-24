import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (average_precision_score, roc_auc_score,
                             precision_recall_curve, f1_score,
                             precision_score, recall_score, confusion_matrix)
from imblearn.over_sampling import SMOTE, ADASYN, BorderlineSMOTE, RandomOverSampler
from imblearn.under_sampling import RandomUnderSampler, TomekLinks
from imblearn.combine import SMOTETomek, SMOTEENN
import warnings
warnings.filterwarnings('ignore')

DATA = Path('dataset/parquets/fault_risk/fault_dataset_v2.parquet')
TARGET = 'will_fail_next_24h'
FEATURES = [
    'nsd_prev_1d', 'nsd_prev_7d', 'nsd_prev_30d',
    'dow', 'month', 'is_weekend',
    'failures_prev_7d', 'failures_prev_30d',
    'off_guard_prev_7d', 'off_guard_prev_30d',
    'episodes_prev_7d', 'episodes_prev_30d',
    'fault_channels_prev_1d', 'fault_events_prev_1d',
    'pump_eps_30d', 'fan_eps_30d', 'ups_eps_30d', 'phase_eps_30d',
    'days_since_last_episode', 'max_channel_eps_30d', 'repeat_channels_30d',
]

df = pd.read_parquet(DATA)
df['day'] = pd.to_datetime(df['day'])
df['year'] = df['day'].dt.year

X = df[FEATURES].fillna(0)
y = df[TARGET].astype(int)

tr = df['year'] < 2024
te = df['year'] >= 2024
X_train, X_test = X[tr], X[te]
y_train, y_test = y[tr], y[te]

print(f"📊 Баланс в трейне: {y_train.value_counts().to_dict()}")
print(f"📊 Баланс в тесте:  {y_test.value_counts().to_dict()}\n")

# Стратегии ресемплинга
strategies = {
    'Baseline (class_weight)': ('class_weight', None),
    'RandomUnderSampler': ('undersample', RandomUnderSampler(random_state=42)),
    'TomekLinks': ('undersample', TomekLinks()),
    'RandomOverSampler': ('oversample', RandomOverSampler(random_state=42)),
    'SMOTE': ('oversample', SMOTE(random_state=42, k_neighbors=5)),
    'BorderlineSMOTE': ('oversample', BorderlineSMOTE(random_state=42, k_neighbors=5)),
    'ADASYN': ('oversample', ADASYN(random_state=42)),
    'SMOTETomek': ('combine', SMOTETomek(random_state=42)),
    'SMOTEENN': ('combine', SMOTEENN(random_state=42)),
}

results = []

for name, (method, sampler) in strategies.items():
    print(f"🚀 {name}...")
    
    # Подготовка данных
    if method == 'class_weight':
        X_res, y_res = X_train, y_train
        rf = RandomForestClassifier(n_estimators=400, max_depth=11, min_samples_leaf=10,
                                    class_weight='balanced', random_state=42, n_jobs=-1)
    elif method == 'undersample':
        X_res, y_res = sampler.fit_resample(X_train, y_train)
        rf = RandomForestClassifier(n_estimators=400, max_depth=11, min_samples_leaf=10,
                                    random_state=42, n_jobs=-1)
    else:  # oversample или combine
        X_res, y_res = sampler.fit_resample(X_train, y_train)
        rf = RandomForestClassifier(n_estimators=400, max_depth=11, min_samples_leaf=10,
                                    random_state=42, n_jobs=-1)
    
    # Обучение
    rf.fit(X_res, y_res)
    proba = rf.predict_proba(X_test)[:, 1]
    
    # Метрики
    ap = average_precision_score(y_test, proba)
    auc = roc_auc_score(y_test, proba)
    
    # Порог по макс F1
    prec, rec, thr = precision_recall_curve(y_test, proba)
    f1s = [f1_score(y_test, (proba >= t).astype(int), zero_division=0) for t in thr]
    i = int(np.argmax(f1s))
    t = thr[i]
    yp = (proba >= t).astype(int)
    P = precision_score(y_test, yp, zero_division=0)
    R = recall_score(y_test, yp, zero_division=0)
    F1 = f1_score(y_test, yp, zero_division=0)
    
    print(f"   Тренировочный баланс: {y_res.value_counts().to_dict()}")
    print(f"   PR-AUC={ap:.4f}  ROC={auc:.4f}  P={P:.3f}  R={R:.3f}  F1={F1:.3f}\n")
    
    results.append({
        'Стратегия': name,
        'PR_AUC': round(ap, 4),
        'ROC_AUC': round(auc, 4),
        'Precision': round(P, 3),
        'Recall': round(R, 3),
        'F1': round(F1, 3),
        'Порог': round(float(t), 4)
    })

# Итоговая таблица
res = pd.DataFrame(results).sort_values('PR_AUC', ascending=False).reset_index(drop=True)
print("=" * 100)
print(res.to_string())
print(f"\nBaseline (частота трейна): {y_train.mean():.4f}")
print(f"Lift лучшей: {res.PR_AUC[0] / y_train.mean():.2f}x")