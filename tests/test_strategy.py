"""Hand-calculated fixtures for the client strategy and execution model."""
import json

import pandas as pd
import pytest

from src import run_development
from src.portfolio import BAR_COLUMNS, simulate
from src.signals import daily_signals


def make_bars(rows):
    dates = pd.date_range("2018-01-02", periods=len(rows), freq="B")
    return pd.DataFrame(rows, columns=BAR_COLUMNS, index=dates)


def test_sma_warmup_and_equality():
    close = pd.Series([10.0] * 50 + [20.0])
    result = daily_signals(close)
    assert result.iloc[:49]["sma_slow"].isna().all()
    assert result.iloc[:20]["sma_fast"].isna().all()
    assert not result.iloc[:50]["target_long"].any()
    assert result.iloc[49]["ready"]
    assert result.iloc[49]["sma_fast"] == result.iloc[49]["sma_slow"] == 10
    assert result.iloc[50]["sma_fast"] == pytest.approx(220 / 21)
    assert result.iloc[50]["sma_slow"] == pytest.approx(510 / 50)
    assert result.iloc[50]["target_long"]


def test_close_crossovers_fill_next_open_with_costs_and_distributions():
    bars = make_bars([
        (10, 10, 0, 0, 0),
        (10, 10, 0, 0, 0),
        (10, 13, 0, 0, 0),
        (10, 15, 2, 0, 0),        # Buyer at this open receives none.
        (14, 5, 1, 0.25, 0),     # Still long at close; target just turned cash.
        (12, 20, 2, 0, 0),       # Seller at this open receives the distribution.
    ])
    signals = daily_signals(bars["Close"], fast=2, slow=3)
    assert signals["target_long"].tolist() == [False, False, True, True, False, False]
    trades, ledger = simulate(bars, signals["target_long"], starting_cash=1010, cost_rate=0.01)
    assert trades["signal_date"].tolist() == [bars.index[2], bars.index[4]]
    assert trades["trade_date"].tolist() == [bars.index[3], bars.index[5]]
    assert trades["price"].tolist() == [10, 12]
    assert trades["shares_delta"].tolist() == [100, -100]
    assert trades["notional"].tolist() == [1000, 1200]
    assert trades["cost"].tolist() == [10, 12]
    assert ledger["dividend_cash"].tolist() == [0, 0, 0, 0, 100, 200]
    assert ledger["capital_gain_cash"].tolist() == [0, 0, 0, 0, 25, 0]
    assert ledger["cash"].tolist() == [1010, 1010, 1010, 0, 125, 1513]
    assert ledger["shares"].tolist() == [0, 0, 0, 100, 100, 0]
    assert ledger["equity"].tolist() == [1010, 1010, 1010, 1500, 625, 1513]
    assert ledger["cash_residual"].eq(0).all()
    assert ledger["equity_bridge_residual"].eq(0).all()


def test_default_cost_fractional_fill_and_no_forced_exit():
    bars = make_bars([(10, 10, 0, 0, 0), (12, 14, 0, 0, 0)])
    targets = pd.Series([True, False], index=bars.index)
    trades, ledger = simulate(bars, targets)
    expected_shares = 100_000 / (12 * 1.0005)
    assert len(trades) == 1
    assert trades.iloc[0]["cost"] == pytest.approx(expected_shares * 12 * 0.0005)
    assert ledger.iloc[-1]["cash"] == 0
    assert ledger.iloc[-1]["shares"] == pytest.approx(expected_shares)
    assert ledger.iloc[-1]["equity"] == pytest.approx(expected_shares * 14)


def test_future_bars_cannot_change_completed_signals_or_fills():
    bars = make_bars([(10, close, 0, 0, 0) for close in [10, 10, 13, 15, 5, 20]])
    past = bars.iloc[:4]
    past_signals = daily_signals(past["Close"], 2, 3)
    past_trades, past_ledger = simulate(past, past_signals["target_long"])
    bars.loc[bars.index[4:], ["Open", "Close", "Dividends"]] = [100, 900, 100]
    extended_signals = daily_signals(bars["Close"], 2, 3)
    extended_trades, extended_ledger = simulate(bars, extended_signals["target_long"])
    pd.testing.assert_frame_equal(past_signals, extended_signals.loc[past.index])
    pd.testing.assert_frame_equal(past_ledger, extended_ledger.loc[past.index])
    pd.testing.assert_frame_equal(past_trades, extended_trades.iloc[:len(past_trades)])


def test_split_fails_closed():
    bars = make_bars([(10, 10, 0, 0, 2)])
    with pytest.raises(ValueError, match="Split"):
        simulate(bars, pd.Series([False], index=bars.index))


def test_verified_loader_excludes_holdout_and_rejects_changed_bytes(tmp_path, monkeypatch):
    raw = tmp_path / run_development.RAW
    analysis = tmp_path / run_development.ANALYSIS
    manifest = tmp_path / "evidence" / run_development.SNAPSHOT / "manifest.json"
    for file in [raw, analysis, manifest]:
        file.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"raw fixture")
    analysis.write_text(
        "trading_date,Open,Close,Dividends,Capital Gains,Stock Splits\n"
        "2018-12-31,10,11,0,0,0\n"
        "2019-01-02,unused,unused,unused,unused,unused\n"
    )
    raw_hash = run_development.digest(raw.read_bytes())
    analysis_hash = run_development.digest(analysis.read_bytes())
    monkeypatch.setattr(run_development, "RAW_HASH", raw_hash)
    monkeypatch.setattr(run_development, "ANALYSIS_HASH", analysis_hash)
    manifest.write_text(json.dumps({
        "status": "complete", "snapshot": run_development.SNAPSHOT, "symbol": "SPY",
        "price_currency": "USD",
        "files": {run_development.RAW: raw_hash, run_development.ANALYSIS: analysis_hash},
    }))
    assert run_development.load_development(tmp_path).index.tolist() == ["2018-12-31"]
    analysis.write_bytes(analysis.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        run_development.load_development(tmp_path)
