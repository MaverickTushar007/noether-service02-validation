"""Reviewer arithmetic transcribed from the written strategy specification."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from statistics import mean, stdev

ZERO = Decimal(0)
ONE = Decimal(1)
STARTING_CASH = Decimal("100000")
FEE = Decimal("0.0005")
SESSIONS_PER_YEAR = 252


@dataclass(frozen=True)
class Session:
    date: str
    opening: Decimal
    closing: Decimal
    dividend: Decimal = ZERO
    capital_gain: Decimal = ZERO
    split: Decimal = ZERO


def read_session(row):
    try:
        bar = Session(row["trading_date"], *(Decimal(row[key]) for key in
                      ("Open", "Close", "Dividends", "Capital Gains", "Stock Splits")))
    except (KeyError, TypeError, InvalidOperation) as error:
        raise ValueError(f"Missing or invalid observation on {row.get('trading_date')}") from error
    return bar


def reproduce(bars, expected_dates, *, fast=21, slow=50, initial=STARTING_CASH, fee=FEE):
    dates = [bar.date for bar in bars]
    if not dates or dates != sorted(set(dates)) or dates != list(expected_dates):
        raise ValueError("Missing, extra, duplicate, or out-of-order session")
    for bar in bars:
        if any(not price.is_finite() or price <= 0 for price in (bar.opening, bar.closing)):
            raise ValueError(f"Missing or invalid price on {bar.date}")
        if any(not amount.is_finite() or amount < 0 for amount in (bar.dividend, bar.capital_gain)):
            raise ValueError(f"Invalid distribution on {bar.date}")
        if bar.split != ZERO:
            raise ValueError(f"Unspecified split basis on {bar.date}")

    with localcontext(prec=40):
        closes = [bar.closing for bar in bars]
        signals, trades, ledger = [], [], []
        previous_target = False
        for index, close in enumerate(closes):
            end = index + 1
            fast_total = sum(closes[end - fast:end]) if end >= fast else None
            slow_total = sum(closes[end - slow:end]) if end >= slow else None
            # Compare the finite decimal sums by cross multiplication before dividing.
            target = slow_total is not None and fast_total * slow > slow_total * fast
            signals.append({
                "trading_date": dates[index], "close": close,
                "sma_fast": "" if fast_total is None else fast_total / fast,
                "sma_slow": "" if slow_total is None else slow_total / slow,
                "ready": slow_total is not None, "target_long": target,
                "crossover": ("ENTER" if target else "EXIT") if target != previous_target else "",
            })
            previous_target = target

        cash, units = initial, ZERO
        last_open_target = False
        for index, bar in enumerate(bars):
            open_target = index > 0 and signals[index - 1]["target_long"]
            prior_cash, prior_units = cash, units
            dividend_cash = units * bar.dividend
            capital_cash = units * bar.capital_gain
            available = cash + dividend_cash + capital_cash
            cash = available
            cost = net = delta = ZERO
            if open_target != last_open_target:
                if open_target:
                    gross = available / (ONE + fee)
                    units = gross / bar.opening
                    delta = units
                    cost = available - gross
                    net, cash = -available, ZERO
                else:
                    gross = units * bar.opening
                    delta, units = -units, ZERO
                    cost = gross * fee
                    net = gross - cost
                    cash = available + net
                trades.append({
                    "signal_date": dates[index - 1], "trade_date": bar.date,
                    "side": "BUY" if open_target else "SELL", "price": bar.opening,
                    "shares_delta": delta, "notional": gross, "cost": cost,
                    "cash_before_fill": available, "net_trade_cash": net, "cash_after_fill": cash,
                })
            position = units * bar.closing
            equity = cash + position
            previous_close = closes[index - 1] if index else bar.opening
            previous_equity = ledger[-1]["equity"] if ledger else initial
            overnight = prior_units * (bar.opening - previous_close)
            intraday = units * (bar.closing - bar.opening)
            ledger.append({
                "trading_date": bar.date, "open": bar.opening, "close": bar.closing,
                "prior_cash": prior_cash, "prior_shares": prior_units, "dividend_cash": dividend_cash,
                "capital_gain_cash": capital_cash, "net_trade_cash": net, "trade_cost": cost,
                "shares_delta": delta, "cash": cash, "shares": units, "position_value": position,
                "equity": equity, "overnight_pnl": overnight, "intraday_pnl": intraday,
                "cash_residual": cash - available - net,
                "shares_residual": units - prior_units - delta,
                "equity_bridge_residual": equity - (
                    previous_equity + overnight + intraday + dividend_cash + capital_cash - cost
                ),
            })
            last_open_target = open_target
        return signals, trades, ledger


def metrics(equity, initial=STARTING_CASH, annual_sessions=SESSIONS_PER_YEAR):
    """Calculate metrics from positive closing equity and a pre-first-session baseline."""
    with localcontext(prec=40):
        returns = []
        previous = peak = initial
        worst = ZERO
        for value in equity:
            returns.append(value / previous - ONE)
            peak = max(peak, value)
            worst = max(worst, ONE - value / peak)
            previous = value
        sigma = stdev(returns)
        scale = Decimal(annual_sessions).sqrt()
        return {
            "total_return": previous / initial - ONE,
            "annualized_return": (previous / initial) ** (Decimal(annual_sessions) / len(returns)) - ONE,
            "annualized_volatility": sigma * scale,
            "annualized_sharpe": mean(returns) * scale / sigma if sigma else None,
            "max_drawdown": worst,
        }
