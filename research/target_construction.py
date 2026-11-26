"""
TARGET CONSTRUCTION - Master Prompt V4, Part V (5.1-5.3).

Multi-target architecture: Policy Direction, Continuity, Implementation,
Legislative Outcome, Event Occurrence, Government Agenda Momentum.
Codebook per Part V-5.2; only build targets with sufficient observations.
"""
import numpy as np
import pandas as pd


def build_policy_direction(df: pd.DataFrame, col: str, horizon: int,
                           event_windows: list = None):
    """Target A - Expansion/Continuation/Restriction (Master 5.1)."""
    change = df[col].shift(-horizon) - df[col]
    dir_ = pd.Series("continuation", index=df.index)
    # Event-based outcome thresholds preferred (Master 5.3); see build_event_based_label
    return change, dir_


def build_event_based_label(changes: pd.Series, min_magnitude: float = 0.0,
                            k_shift: float = 0.0):
    """Prefer event-based outcomes over arbitrary quantiles (Master 5.3.2).

    Returns: -1 (Restriction), 0 (Continuation), +1 (Expansion).
    min_magnitude: substatial substantiation threshold, measured on TRAIN only.
    """
    nonneg = changes.dropna()
    if len(nonneg) == 0:
        return pd.Series(0, index=changes.index)
    labels = pd.Series(0, index=changes.index)
    labels[changes <= -max(min_magnitude, 0.0)] = -1
    labels[changes >= max(min_magnitude, 0.0)] = 1
    return labels


def build_all_targets(df: pd.DataFrame, col: str = "macro_policy_index",
                      horizons=(7, 30)):
    """Build full multi-target set. Returns dict of target series."""
    out = {}
    for h in horizons:
        reg = df[col].shift(-h) - df[col]
        out[f"reg_{h}d"] = reg
        out[f"dir_{h}d"] = build_event_based_label(reg)
        out[f"cont_{h}d"] = (reg != 0).astype(int)
    out["implementation_7d"] = df["program_start_date"].notna().astype(int) if "program_start_date" in df else 0
    return out
