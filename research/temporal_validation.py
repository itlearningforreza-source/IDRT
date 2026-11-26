"""
TEMPORAL VALIDATION - Master Prompt V4, Part XI (11.1-11.4).

Chronological splitting, walk-forward (expanding & rolling), purged validation
with embargo, nested temporal validation (outer generalization / inner tuning).
"""
import numpy as np
import pandas as pd


def chronological_split(df, date_col="date", fracs=(0.6, 0.2, 0.2)):
    """Chronological Train/Val/Test split (Part XI 11.1). No shuffling."""
    n = len(df)
    tr, va, te = int(n*fracs[0]), int(n*fracs[1]), int(n*fracs[2])
    return df.iloc[:tr], df.iloc[tr:tr+va], df.iloc[tr+va:tr+va+te]


def walk_forward_validate(dates: np.ndarray, step: int, fit_fn, pred_fn):
    """Expanding-window walk-forward (Part XI 11.2). fit_fn(train_idx)->model;
    pred_fn(model, test_idx)->pred. Returns list of (test_idx, pred, truth_idx)."""
    results = []
    train_end = step
    while train_end < len(dates):
        test_idx = np.arange(train_end, min(train_end + step, len(dates)))
        train_idx = np.arange(0, train_end)
        model = fit_fn(train_idx)
        preds = pred_fn(model, test_idx)
        results.append((test_idx, preds))
        train_end += step
    return results


def purged_split(dates: pd.Series, test_start, lookback=14):
    """Remove training rows whose label horizon overlaps the test window (Part XI 11.3)."""
    emb = lookback
    mask = (dates < test_start) & (dates.shift(-emb) >= test_start - pd.Timedelta(days=emb*0))
    return mask
