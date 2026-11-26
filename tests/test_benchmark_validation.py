"""Toy accounting, timeline and paired-performance challenges."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from src.independent_validation.reproduction import Session
from src.benchmark_validation.accounting import FEE, INITIAL, WEIGHT, cash_intervals, parse_rates, simulate
from src.benchmark_validation.metrics import measures, paired, primary_judgment
from src.benchmark_validation.reconcile import reconcile


DATES = ["2019-01-04", "2019-01-07", "2019-01-08"]


def fixture():
    bars = [Session(d, D(100), D(100), D(1) if i == 1 else D(0)) for i, d in enumerate(DATES)]
    rates = list(cash_intervals(DATES, {"2019-01-03": D("3.60"), "2019-01-04": D(90), "2019-01-07": D(80)}))
    return bars, rates


def test_cash_funding_lag_and_calendar_days():
    bars, rates = fixture()
    assert rates[1][:3] == ("2019-01-03", D("3.60"), 3)
    assert rates[2][:3] == ("2019-01-04", D(90), 1)
    expected = (1 - 0.036 * 91 / 360) ** (-3 / 91) - 1
    assert float(rates[1][3]) == pytest.approx(expected)
    rows = simulate("cash", bars, rates)
    assert float(rows[1]["interest"]) == pytest.approx(100000 * expected)
    assert measures("cash", rows)["excess_sharpe"] == ""
    bad = [*rows[:1], {**rows[1], "rate_date": DATES[0]}, rows[2]]
    with pytest.raises(ValueError, match="Incorrect cash interval"):
        reconcile("cash", bad, bars, rates)
    with pytest.raises(ValueError, match="Stale"):
        list(cash_intervals(DATES, {"2018-12-01": D(1)}))
    assert parse_rates([{"observation_date": "2019-01-02", "DTB3": "."}]) == {}


def test_buy_hold_reinvestment_waits_and_fees_reconcile():
    bars, rates = fixture()
    rows = simulate("buy_hold", bars, rates)
    buy = INITIAL / (1 + FEE)
    assert float(rows[0]["signed_notional"]) == pytest.approx(float(buy))
    assert rows[0]["cash"] == 0
    assert rows[1]["signed_notional"] == 0
    assert rows[1]["dividend_cash"] == rows[0]["shares"]
    assert rows[2]["trade_reason"] == "distribution_reinvestment"
    assert reconcile("buy_hold", rows, bars, rates)["status"] == "PASS"
    bad = [{**rows[0], "cost": D(0)}, *rows[1:]]
    with pytest.raises(ValueError, match="spends unavailable cash"):
        reconcile("buy_hold", bad, bars, rates)
    bad = [rows[0], {**rows[1], "signed_notional": D(100)}, rows[2]]
    with pytest.raises(ValueError, match="spends unavailable cash"):
        reconcile("buy_hold", bad, bars, rates)
    bad = [rows[0], {**rows[1], "dividend_cash": rows[1]["dividend_cash"] * 2}, rows[2]]
    with pytest.raises(ValueError, match="Unreconciled"):
        reconcile("buy_hold", bad, bars, rates)


def test_fixed_weight_is_after_cost_and_rebalances_only_monthly():
    bars, rates = fixture()
    rows = simulate("fixed_mix", bars, rates)
    assert float(rows[0]["open_position_value"] / rows[0]["equity"]) == pytest.approx(float(WEIGHT))
    assert rows[1]["signed_notional"] == rows[2]["signed_notional"] == 0
    assert reconcile("fixed_mix", rows, bars, rates)["status"] == "PASS"
    second_month = replace(bars[-1], date="2019-02-01", opening=D(150))
    sale = simulate("fixed_mix", [*bars[:2], second_month], rates)[-1]
    assert sale["signed_notional"] < 0
    assert float(sale["open_position_value"] / (sale["open_position_value"] + sale["cash"])) == pytest.approx(float(WEIGHT))


def test_sma_carry_in_and_future_price_challenge():
    bars, rates = fixture()
    from datetime import date, timedelta
    warmup = [((date(2018, 11, 11) + timedelta(days=i)).isoformat(), D(i + 1)) for i in range(50)]
    rows = simulate("sma", bars, rates, warmup)
    assert rows[0]["open_target_long"] and rows[0]["signed_notional"] > 0
    assert rows[0]["signal_date"] == warmup[-1][0]
    assert rows[0]["dividend_cash"] == 0
    assert all(row["interest"] == 0 for row in rows)
    changed = simulate("sma", [*bars[:2], replace(bars[-1], closing=D(1000))], rates, warmup)
    assert changed[:2] == rows[:2]
    assert reconcile("sma", rows, bars, rates, warmup)["status"] == "PASS"
    bad = [{**rows[0], "signal_date": DATES[0]}, *rows[1:]]
    with pytest.raises(ValueError, match="Future or misdated"):
        reconcile("sma", bad, bars, rates, warmup)


def test_paired_dates_and_primary_threshold():
    row = {"date": "2019-01-01"}
    with pytest.raises(ValueError, match="Unpaired"):
        paired("cash", [row], [{"date": "2019-01-02"}])
    common = {"daily_ci_lower": 0.01, "daily_ci_upper": 0.1, "compounded_total_return_gap": 0.03}
    assert primary_judgment(common) == "PASS"
    assert primary_judgment({**common, "daily_ci_lower": -0.02}) == "INCONCLUSIVE"
    assert primary_judgment(dict(daily_ci_lower=-0.1, daily_ci_upper=-0.01,
                                 compounded_total_return_gap=-0.03)) == "FAIL"
