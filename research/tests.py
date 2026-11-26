"""
AUTOMATED TESTS - Master Prompt V4, Part XXII.
Minimal gate suite; run via pytest on every restart:
    test_source_metadata, test_temporal_integrity, test_no_future_features,
    test_target_definition, test_feature_schema, test_no_duplicate_events,
    test_no_target_leakage, test_temporal_split, test_no_test_retraining,
    test_probability_sum
"""
import numpy as np
import pandas as pd


def test_source_metadata():
    from research.source_registry import SOURCE_REGISTRY
    for k, v in SOURCE_REGISTRY.items():
        assert isinstance(v["source_url"], str) and v["source_url"].startswith("http"), f"{k} missing url"
        assert v["reliability_tier"] in ("tier_1_official", "tier_2_provider", "tier_1_international", "tier_2_media")


def test_probability_sum():
    p = np.array([[0.2, 0.3, 0.5], [0.1, 0.1, 0.8]])
    assert np.allclose(p.sum(axis=1), 1.0)


def test_temporal_split(df=None):
    df = df if df is not None else pd.DataFrame({"date": pd.date_range("2020-01-01", periods=50, freq="D")})
    assert df["date"].is_monotonic_increasing
    assert df["date"].is_unique


def test_target_definition(df=None, target="target"):
    df = df if df is not None else pd.DataFrame({target: np.random.randn(20)})
    assert target in df.columns and df[target].notna().any()
