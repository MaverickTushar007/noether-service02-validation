"""Test audit rules with synthetic fixtures and validate every saved snapshot."""
import json

import pandas as pd
import pytest
import yaml

from src.acquire import REQUIRED, ROOT, audit, normalize, sha256


@pytest.fixture
def example():
    return pd.DataFrame(
        [[100, 101, 99, 100, 99, 1000, 0, 0],
         [99, 100, 98, 99, 99, 1200, 1, 0]],
        columns=REQUIRED,
        dtype=float,
        index=pd.to_datetime(["2011-01-03T05:00Z", "2011-01-04T05:00Z"], utc=True),
    )


def test_schema_and_exchange_dates(example):
    dated = normalize(example)
    assert list(dated.columns) == REQUIRED
    assert list(dated.index) == ["2011-01-03", "2011-01-04"]
    assert dated.iloc[1]["Dividends"] == 1
    example.index = example.index - pd.Timedelta(hours=1)
    assert normalize(example).index[0] == "2011-01-02"
    with pytest.raises(ValueError, match="Volume"):
        normalize(example.drop(columns="Volume"))
    example.index = example.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize(example)


def test_sessions_and_dividend_adjustment(example):
    results = audit(normalize(example))
    assert results["expected_session_count"] == 3020
    assert results["missing_expected_sessions"][0] == "2011-01-05"
    assert "2012-10-29" not in results["missing_expected_sessions"]
    assert results["missing_expected_sessions"][-1] == "2022-12-30"
    assert not results["complete"]
    assert not results["adjustment_review_dates"]


def test_duplicates_order_and_bad_values(example):
    frame = normalize(example)
    frame.loc["2011-01-04", ["Open", "Close", "Adj Close", "Volume"]] = [110, 0, float("inf"), -1]
    frame.loc["2011-01-03", "Low"] = float("nan")
    results = audit(pd.concat([frame.iloc[::-1], frame.iloc[[0]]]))
    assert not results["chronologically_ordered"]
    assert results["duplicate_dates"] == ["2011-01-03"]
    assert results["missing_values"]["Low"] == ["2011-01-03", "2011-01-03"]
    assert results["nonpositive_prices"]["Close"] == ["2011-01-04"]
    assert results["nonfinite_prices"]["Adj Close"] == ["2011-01-04"]
    assert results["ohlc_inconsistency_dates"] == ["2011-01-04"]
    assert results["negative_volume_dates"] == ["2011-01-04"]


MANIFESTS = sorted(ROOT.glob("evidence/*/manifest.json"))
COMPLETE = [path for path in MANIFESTS if json.loads(path.read_text())["status"] == "complete"]


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda path: path.parent.name)
def test_manifest_checksums(path):
    manifest = json.loads(path.read_text())
    assert manifest["files"]
    for relative_path, expected in manifest["files"].items():
        assert sha256(ROOT / relative_path) == expected
    if manifest["status"] == "failed":
        assert manifest["error"]
        assert not (ROOT / "data" / "analysis" / manifest["snapshot"]).exists()


@pytest.mark.parametrize("path", COMPLETE, ids=lambda path: path.parent.name)
def test_saved_dataset(path):
    snapshot = path.parent.name
    raw = pd.read_csv(ROOT / "data" / "raw" / snapshot / "spy.csv", index_col=0, float_precision="round_trip")
    raw.index = pd.to_datetime(raw.index, utc=True)
    saved = pd.read_csv(ROOT / "data" / "analysis" / snapshot / "spy.csv", index_col=0, float_precision="round_trip")
    pd.testing.assert_frame_equal(normalize(raw), saved, check_exact=True)
    findings = audit(saved)
    assert findings["complete"]
    assert findings["observation_count"] == 3020
    assert not findings["duplicate_dates"]
    assert not any(findings["nonfinite_prices"].values())
    assert not any(findings["nonpositive_prices"].values())
    assert not findings["ohlc_inconsistency_dates"]
    assert not findings["negative_volume_dates"]
    assert not findings["nonfinite_volume_dates"]
    persisted = json.loads((path.parent / "audit.json").read_text())
    assert persisted == findings


def test_research_control():
    spec = yaml.safe_load((ROOT / "config" / "research_spec.yaml").read_text())
    assert spec["asset"] == "SPY"
    assert spec["sma"] == {"fast": 21, "slow": 50}
    assert spec["analysis_frequencies"] == ["daily", "weekly", "monthly"]
    assert spec["development"]["end"] < spec["holdout"]["start"]
