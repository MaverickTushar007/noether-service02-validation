"""Chronological next-open fills and close accounting for a binary SPY target."""
from math import isclose, isfinite

import numpy as np
import pandas as pd

BAR_COLUMNS = ["Open", "Close", "Dividends", "Capital Gains", "Stock Splits"]
TRADE_COLUMNS = [
    "signal_date", "trade_date", "side", "price", "shares_delta", "notional", "cost",
    "cash_before_fill", "net_trade_cash", "cash_after_fill",
]
TOLERANCE = 1e-8


def simulate(
    bars: pd.DataFrame, targets: pd.Series, starting_cash: float = 100_000,
    cost_rate: float = 0.0005,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not isfinite(starting_cash) or starting_cash <= 0 or not 0 <= cost_rate < 1:
        raise ValueError("Require positive starting cash and a finite cost rate in [0, 1)")
    if (bars.empty or not bars.index.is_unique or not bars.index.is_monotonic_increasing
            or not bars.index.equals(targets.index)):
        raise ValueError("Require nonempty matching, unique, chronological session indexes")
    if not pd.api.types.is_bool_dtype(targets.dtype) or targets.isna().any():
        raise ValueError("Targets must be nonmissing booleans")
    values = bars[BAR_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, :2] <= 0).any() or (values[:, 2:4] < 0).any():
        raise ValueError("Require positive finite prices and finite nonnegative distributions")
    if (values[:, 4] != 0).any():
        raise ValueError("Split events require an explicit share and price basis")

    cash, shares = starting_cash, 0.0
    previous_close, previous_equity = 0.0, starting_cash
    previous_date, pending_long = None, False
    trades, ledger = [], []
    for date, bar in zip(bars.index, values, strict=True):
        opening, closing, dividend, capital_gain, _ = map(float, bar)
        prior_cash, prior_shares = cash, shares
        dividend_cash = prior_shares * dividend
        capital_gain_cash = prior_shares * capital_gain
        distributions = dividend_cash + capital_gain_cash
        cash += distributions

        signed_shares = trade_cash = cost = 0.0
        if pending_long != (shares > 0):
            cash_before_fill = cash
            if pending_long:
                signed_shares = cash / (opening * (1 + cost_rate))
            else:
                signed_shares = -shares
            notional = abs(signed_shares) * opening
            cost = notional * cost_rate
            trade_cash = -(signed_shares * opening) - cost
            cash += trade_cash
            if pending_long and abs(cash) <= TOLERANCE:
                cash = 0.0  # All available cash was budgeted for this fill.
            shares += signed_shares
            trades.append(dict(zip(TRADE_COLUMNS, (
                previous_date, date, "BUY" if pending_long else "SELL", opening,
                signed_shares, notional, cost, cash_before_fill, trade_cash, cash,
            ), strict=True)))

        equity = cash + shares * closing
        overnight_pnl = prior_shares * (opening - previous_close)
        intraday_pnl = shares * (closing - opening)
        cash_residual = cash - (prior_cash + distributions + trade_cash)
        bridge_residual = equity - (
            previous_equity + overnight_pnl + intraday_pnl + distributions - cost
        )
        if (cash < 0 or shares < 0 or not isclose(cash_residual, 0, abs_tol=TOLERANCE)
                or not isclose(bridge_residual, 0, abs_tol=TOLERANCE)):
            raise ArithmeticError(f"Portfolio failed to reconcile on {date}")
        ledger.append({
            "trading_date": date, "open": opening, "close": closing,
            "prior_cash": prior_cash, "prior_shares": prior_shares,
            "dividend_cash": dividend_cash, "capital_gain_cash": capital_gain_cash,
            "net_trade_cash": trade_cash, "trade_cost": cost, "shares_delta": signed_shares,
            "cash": cash, "shares": shares, "position_value": shares * closing, "equity": equity,
            "overnight_pnl": overnight_pnl, "intraday_pnl": intraday_pnl,
            "cash_residual": cash_residual, "equity_bridge_residual": bridge_residual,
        })

        # Release the closing signal only after today's open fill and close mark.
        previous_date, pending_long = date, bool(targets.at[date])
        previous_close, previous_equity = closing, equity

    return pd.DataFrame(trades, columns=TRADE_COLUMNS), pd.DataFrame(ledger).set_index("trading_date")
