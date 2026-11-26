"""Controlled mathematical challenges. No SPY or client outputs are used here."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from src.independent_validation.comparison import CASH, METRIC, SHARES, compare
from src.independent_validation.reproduction import Session, metrics, read_session, reproduce

DATES = ["2018-01-02", "2018-01-03", "2018-01-04", "2018-01-05", "2018-01-08", "2018-01-09"]


def toy():
    bars = [Session(date, D(opening), D(closing), D(dividend), D(gain))
            for date, (opening, closing, dividend, gain) in zip(DATES, [
                (10, 10, 0, 0), (10, 10, 0, 0), (10, 13, 0, 0),
                (20, 15, 2, 0), (14, 5, 1, 0), (12, 20, 2, "0.25"),
            ], strict=True)]
    return reproduce(bars, DATES, fast=2, slow=3, initial=D("2001"))


def rejected(submitted, reviewer, field, tolerance):
    result, = compare("synthetic", [submitted], [reviewer], {field: tolerance}, "date")
    assert result["status"] == "FAIL"
    assert result["mismatches"] == 1


def test_challenge_impossible_same_close_fill():
    _, trades, daily = toy()
    buy = trades[0]
    assert (buy["signal_date"], buy["trade_date"], buy["price"]) == (DATES[2], DATES[3], D(20))
    assert daily[2]["shares"] == 0
    rejected({**buy, "trade_date": DATES[2], "price": 13}, buy, "trade_date", None)


def test_challenge_omitted_fees():
    _, trades, daily = toy()
    buy, sell = trades
    # 2001 buys 100 shares at 20 inclusive of a 1 USD fee.
    assert (buy["shares_delta"], buy["notional"], buy["cost"]) == (D(100), D(2000), D(1))
    assert sell["cost"] == D("0.60")
    assert daily[-1]["cash"] == D("1524.40")  # 325 distribution cash + 1200 - 0.60.
    rejected({**sell, "cost": 0}, sell, "cost", CASH)
    rejected({"cash": D(1525)}, daily[-1], "cash", CASH)


def test_challenge_double_counting_distributions():
    _, trades, daily = toy()
    # Buyers on the ex-date get zero. Prior holders get 100 and then 200 even when selling.
    assert [row["dividend_cash"] for row in daily] == [0, 0, 0, 0, 100, 200]
    assert daily[-1]["capital_gain_cash"] == D(25)
    assert daily[4]["equity"] == D(600)  # 100 shares at 5 plus 100 cash.
    assert trades[1]["cash_before_fill"] == D(325)
    rejected({"equity": D(700)}, daily[4], "equity", CASH)  # A second 100 credit.


def test_challenge_incomplete_sma_warmup():
    signals, _, _ = toy()
    assert signals[0]["sma_fast"] == signals[1]["sma_slow"] == ""
    assert signals[1]["sma_fast"] == D(10)
    assert signals[2]["sma_fast"] == D("11.5")
    assert signals[2]["sma_slow"] == D(11)
    assert signals[2]["ready"] and not signals[1]["ready"]
    rejected({"ready": True}, signals[1], "ready", None)
    dates = [f"{i:03}" for i in range(51)]
    bars = [Session(date, D(10), D(10 if i < 50 else 20)) for i, date in enumerate(dates)]
    full, _, _ = reproduce(bars, dates)
    assert full[19]["sma_fast"] == full[48]["sma_slow"] == ""
    assert full[49]["sma_fast"] == full[49]["sma_slow"] == 10
    assert not full[49]["target_long"] and full[50]["target_long"]


def test_challenge_one_session_signal_misalignment():
    signals, trades, _ = toy()
    assert [(row["trading_date"], row["crossover"]) for row in signals if row["crossover"]] == [
        (DATES[2], "ENTER"), (DATES[4], "EXIT"),
    ]
    assert trades[1]["signal_date"] == DATES[4] and trades[1]["trade_date"] == DATES[5]
    rejected({"signal_date": DATES[3]}, trades[1], "signal_date", None)
    rejected({"shares_delta": 0}, trades[1], "shares_delta", SHARES)


def test_challenge_drawdown_uses_the_running_peak():
    result = metrics([D(120), D(90), D(110)], initial=D(100))
    assert result["max_drawdown"] == D("0.25")
    rejected({"max_drawdown": D("0.10")}, result, "max_drawdown", METRIC)
    example = metrics([D(110), D(99)], initial=D(100), annual_sessions=2)
    assert abs(example.pop("annualized_volatility") - D("0.2")) < D("1e-38")
    assert example == {"total_return": D("-0.01"), "annualized_return": D("-0.01"),
                       "annualized_sharpe": D(0), "max_drawdown": D("0.1")}


@pytest.mark.parametrize("bad", [D("NaN"), D("Infinity"), D(0), D(-1)])
def test_challenge_invalid_open_or_close(bad):
    bar = Session(DATES[0], D(10), D(10))
    for field in ("opening", "closing"):
        with pytest.raises(ValueError, match=f"invalid price on {DATES[0]}"):
            reproduce([replace(bar, **{field: bad})], DATES[:1])


def test_challenge_missing_observation_and_missing_session():
    with pytest.raises(ValueError, match="Missing or invalid observation"):
        read_session({"trading_date": DATES[0], "Open": "", "Close": "10"})
    bars = [Session(date, D(10), D(10)) for date in DATES[:2]]
    with pytest.raises(ValueError, match="Missing, extra"):
        reproduce(bars, DATES[:3])


def test_comparison_detects_missing_row_and_reports_roundoff():
    client = [{"date": "first", "cash": "100"}, {"date": "second", "cash": "99"}]
    reviewer = [{"date": "first", "cash": D("100.000000001")}]
    date_result, money_result = compare("synthetic", client, reviewer, {"date": None, "cash": CASH}, "date")
    assert date_result["mismatches"] == money_result["mismatches"] == 1
    assert money_result["max_abs_difference"] == D("1e-9")
    assert money_result["max_rel_difference"] == D("1e-11")
    assert money_result["first_mismatch_key"] == "second"
