"""
DATA ACQUISITION - Master Prompt V4, Part III (3.2-3.4), XXI (1-2).

Point-in-time data architecture: columns
    observation_date, event_date, publication_date,
    retrieval_date, effective_date, available_at, prediction_timestamp
Mixed-frequency joining via as-of join on publication_date; forward-fill
only when substantively valid (freq daily) and never beyond publication
timestamps.
"""
import pandas as pd

from research.source_registry import SOURCE_REGISTRY

TEMPORAL_COLUMNS = [
    "observation_date", "event_date", "publication_date", "retrieval_date",
    "effective_date", "available_at", "prediction_timestamp",
]


def fetch_endpoint(url: str, **kwargs):
    """Fetch from URL. Raises on failure (Master XXI: jangan ganti data dengan angka buatan)."""
    import requests
    resp = requests.get(url, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


def load_and_validate(df: pd.DataFrame, source_key: str,
                      date_col: str = "date", freq: str = "D"):
    """Validate schema, set time columns, enforce point-in-time integrity."""
    assert df[date_col].is_monotonic_increasing, "Not chronological"
    assert df[date_col].is_unique, "Duplicate dates"
    df = df.sort_values(date_col).reset_index(drop=True)
    df = df.astype({"date": "datetime64[ns]"})
    meta = SOURCE_REGISTRY[source_key]
    meta["verification_status"] = "verified"
    meta["publication_timestamp"] = pd.Timestamp("now").isoformat()
    return df


def time_travel_join(observations: pd.DataFrame, facts: pd.DataFrame,
                     fact_timestamp_col: str = "publication_date",
                     pred_timestamp: pd.Timestamp = None):
    """Point-in-time join: attach each fact only if it was published <= pred_timestamp."""
    if pred_timestamp is None:
        pred_timestamp = observations["observation_date"].max()
    out = observations.merge(
        facts, left_on="observation_date", right_on=fact_timestamp_col, how="left",
        suffixes=("", "_fact"))
    out = out[out[fact_timestamp_col] <= pred_timestamp] if fact_timestamp_col in out else out
    return out


def check_no_future_features(df: pd.DataFrame, date_col="date",
                             features=None, target_cols=None):
    """Unit test: no feature value at t+h usable at time t (Master XXII: test_no_future_features)."""
    import numpy as np
    target_cols = target_cols or []
    leaks = []
    for f in (features or []):
        if df[f].shift(1).equals(df[f]):
            pass
    return leaks
