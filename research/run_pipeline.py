"""
RUN PIPELINE - Master Prompt V4, Phases 2-18.

End-to-end real-data empirical pipeline. Real data acquisition (Phase 3)
must succeed first: otherwise this raises a RuntimeError rather than
training on fallback/synthetic data.
"""
import numpy as np
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, accuracy_score

from research.source_registry import SOURCE_REGISTRY
from research.data_acquisition import load_and_validate
from research.target_construction import build_all_targets
from research.temporal_validation import chronological_split
from research.models import baselines, optuna_search_lgb, train_final, SEED
from research.ensemble_calibration import fit_platt_multiclass, brier_multiclass
from research.drift_monitoring import drift_report


def run(df: pd.DataFrame, col="macro_policy_index"):
    df = load_and_validate(df, "bi_databank_inflation_gdp")
    targets = build_all_targets(df, col=col)

    tr, va, te = chronological_split(df)
    X = df.drop(columns=[c for c in ["date"] if c in df.columns])
    idx = {k: v.index for k, v in [("train", tr), ("val", va), ("test", te)]}

    metrics = {}
    for h in (7, 30):
        y_train = targets[f"dir_{h}d"].reindex(tr.index)
        y_val = targets[f"dir_{h}d"].reindex(va.index)
        y_test = targets[f"dir_{h}d"].reindex(te.index)
        y_cls_tr = pd.Series(pd.factorize(y_train.fillna(0).astype(float).astype(int))[0], index=y_train.index)  # Part IX multiclass

        m = baselines(y_train.dropna(), y_val.dropna())
        metrics[f"baseline_{h}d"] = m

        # Optuna (validation set only - never test)
        params = optuna_search_lgb(X.loc[tr.index].dropna(), y_train.dropna(), X.loc[va.index].dropna(), y_val.dropna(), n_trials=15)

        # Ensemble calibration on out-of-fold val predictions
        xgb = train_final(__import__("xgboost").XGBClassifier(random_state=SEED), X.loc[tr.index].dropna(), y_cls_tr.dropna())
        raw = xgb.predict_proba(X.loc[va.index].dropna()); 
        cal = fit_platt_multiclass(raw, y_val.dropna())
        metrics[f"xgb_cal_{h}d"] = {"val_brier": brier_multiclass(y_val.dropna(), cal.predict_proba(raw))}

    drift = drift_report(tr, te, [col])
    return {"targets": targets, "metrics": metrics, "drift": drift, "splits": idx}
