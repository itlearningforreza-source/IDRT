import numpy as np
"""
ENSEMBLE & CALIBRATION - Master Prompt V4, Part XIV + XIII.

Validation-weighted ensemble + Platt scaling (LogisticRegression multiclass),
calibrated on out-of-fold predictions separate from final test.
"""
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss


def fit_platt_multiclass(raw_probs, y):
    cal = LogisticRegression(C=1.0, solver="lbfgs", multi_class="multinomial", random_state=42)
    cal.fit(raw_probs, y)
    return cal


def brier_multiclass(y, prob):
    oh = np.eye(prob.shape[1])[np.asarray(y, dtype=int)]
    return float(np.mean(np.sum((prob - oh) ** 2, axis=1)))
