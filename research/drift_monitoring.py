"""
DRIFT MONITORING - Master Prompt V4, Part XIX + XX.

PSI, KS-like drift checks, champion-challenger. Retraining policy.
"""
import numpy as np
import pandas as pd


def calculate_psi(expected, actual, num_buckets=10):
    percentiles = np.linspace(0, 100, num_buckets + 1)
    buckets = np.unique(np.percentile(expected, percentiles))
    if len(buckets) < 2:
        return 0.0
    e, _ = np.histogram(expected, bins=buckets)
    a, _ = np.histogram(actual, bins=buckets)
    ep = np.where(e == 0, 0.0001, e) / len(expected)
    ap = np.where(a == 0, 0.0001, a) / len(actual)
    return float(np.sum((ap - ep) * np.log(ap / ep)))


def drift_report(train_df, test_df, cols, threshold_stable=0.1, threshold_drift=0.25):
    rows = []
    for c in cols:
        psi = calculate_psi(train_df[c].values, test_df[c].values)
        status = "Stable" if psi < threshold_stable else ("Moderate" if psi < threshold_drift else "Significant")
        rows.append({"feature": c, "psi": round(psi, 5), "drift_status": status})
    return pd.DataFrame(rows)
