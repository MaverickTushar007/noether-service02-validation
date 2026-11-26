"""Deterministic Phase 4 arithmetic and timing challenges."""
from decimal import Decimal as D

import numpy as np
import pytest

from src.independent_validation.reproduction import Session
from src.statistical_validation.statistics import block_means, ledger_metrics, positive_mean_status
from src.statistical_validation.timing import audit_orders, audit_regime, build_regime, development_rows, prefix_check


def test_bootstrap_matches_explicit_blocks_and_truncates():
    values = np.array([0.01, -0.02, 0.03, 0.04, -0.01])
    starts = np.random.Generator(np.random.PCG64(123)).integers(4, size=(12, 3))
    expected = [np.concatenate([values[i:i+2] for i in row])[:5].mean() for row in starts]
    actual = block_means(values, 2, 12, seed=123)
    np.testing.assert_allclose(actual, expected, atol=1e-16, rtol=0)
    np.testing.assert_array_equal(actual, block_means(values, 2, 12, seed=123))
    np.testing.assert_allclose(block_means(values, 5, 3), [values.mean()] * 3, atol=1e-16)
    with pytest.raises(ValueError, match="Invalid"):
        block_means([float("nan")], 1)


def test_ledger_arithmetic_uses_initial_equity_and_gross_notional():
    stats, returns, turn = ledger_metrics([110000, 99000], [110000, 0], [10, 0], [100000, 99000])
    np.testing.assert_allclose(returns, [0.1, -0.1], atol=1e-15)
    np.testing.assert_allclose(turn, [1, 0.9], atol=1e-15)
    assert stats["fraction_long_closes"] == stats["mean_close_invested_weight"] == 0.5
    assert stats["annualized_gross_turnover"] == pytest.approx(239.4)
    assert stats["total_return"] == pytest.approx(-0.01)


@pytest.mark.parametrize("bounds, expected", [
    ([(1, 3), (1, 2), (1, 3)], "PASS"),
    ([(-3, -1), (-3, 1), (-3, 1)], "FAIL"),
    ([(0, 3), (1, 2), (1, 2)], "INCONCLUSIVE"),
    ([(1, 3), (-1, 2), (1, 2)], "INCONCLUSIVE"),
])
def test_prespecified_mean_decision(bounds, expected):
    assert positive_mean_status([{"daily_lower": lo, "daily_upper": hi} for lo, hi in bounds]) == expected


def test_order_audit_rejects_same_close_and_wrong_open():
    dates = ["2018-01-05", "2018-01-08"]
    bars = [Session(dates[0], D(10), D(12)), Session(dates[1], D(20), D(21))]
    signals = [{"trading_date": date, "target_long": True} for date in dates]
    ledger = [{"trading_date": date, "shares": index} for index, date in enumerate(dates)]
    fill = {"signal_date": dates[0], "trade_date": dates[1], "side": "BUY", "price": D(20)}
    assert audit_orders(signals, [fill], ledger, bars, dates) == 1
    for change in ({"trade_date": dates[0]}, {"price": D(12)}):
        with pytest.raises(ValueError, match="eligible next-session"):
            audit_orders(signals, [{**fill, **change}], ledger, bars, dates)


@pytest.mark.parametrize("frequency", ["weekly", "monthly"])
def test_period_audit_rejects_premature_label_and_excludes_partial_period(frequency):
    # Fixtures supply a schedule with a shortened first week and a further month-end session.
    if frequency == "weekly":
        schedule = ["2018-03-28", "2018-03-29", "2018-04-02", "2018-04-06"]
    else:
        schedule = ["2018-03-27", "2018-03-29", "2018-04-02", "2018-04-30"]
    closes = {date: D(i) for i, date in enumerate(schedule[:3], 1)}
    labels = build_regime(frequency, closes, schedule, fast=1, slow=2)
    assert [(r["close_date"], r["next_open_date"]) for r in labels] == [(schedule[1], schedule[2])]
    audit_regime(labels, closes, schedule, frequency)
    for changed in ({"close_date": schedule[0]}, {"next_open_date": schedule[1]}):
        with pytest.raises(ValueError, match="incomplete close or an ineligible release"):
            audit_regime([{**labels[0], **changed}], closes, schedule, frequency)


def test_development_boundary_never_reads_later_price_fields():
    def source():
        yield {"trading_date": "2018-12-31", "Close": "2"}
        yield {"trading_date": "2019-01-02", "Close": "not a numeric observation"}
        raise AssertionError("Reader continued beyond the first excluded row")
    kept = list(development_rows(source(), "2011-01-01", "2018-12-31"))
    assert [D(row["Close"]) for row in kept] == [D(2)]


def test_future_perturbation_leaves_ready_signal_prefix_and_fills_unchanged():
    dates = [f"{i:03}" for i in range(120)]
    bars = [Session(d, D(10), D(i + 10)) for i, d in enumerate(dates)]
    assert prefix_check(bars, dates)
