"""Check the independent portfolio ledger against a separate set of identities."""
from decimal import Decimal as D
from math import fsum
from statistics import fmean

from .accounting import FEE, INITIAL, WEIGHT


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reconcile(book, ledger, bars, intervals, warmup=()):
    require(len(ledger) == len(bars) == len(intervals), "Reconciliation length mismatch")
    tolerance = D("1e-8")
    cash, shares, equity = INITIAL, D(0), INITIAL
    closing_history = [float(close) for _, close in warmup]
    prior_date = warmup[-1][0] if warmup else ""
    last_month = ""
    max_residual = D(0)
    for row, bar, interval in zip(ledger, bars, intervals, strict=True):
        stamp = bar.date
        require(row["date"] == stamp, "Unmatched ledger date")
        require((row["rate_date"], row["rate_percent_discount"], row["accrual_days"], row["cash_proxy_return"])
                == interval, f"Incorrect cash interval on {stamp}")
        check_interest = cash * interval[3] if book != "sma" else D(0)
        dividend, gain = shares * bar.dividend, shares * bar.capital_gain
        notional, cost = row["signed_notional"], row["cost"]
        available = cash + check_interest + dividend + gain
        closing_target = None
        if book == "sma":
            prior_target = len(closing_history) >= 50 and fmean(closing_history[-21:]) > fmean(closing_history[-50:])
            require(row["open_target_long"] == prior_target and row["signal_date"] == prior_date,
                    f"Future or misdated SMA target on {stamp}")
            all_closes = closing_history[-49:] + [float(bar.closing)]
            closing_target = len(all_closes) == 50 and fmean(all_closes[-21:]) > fmean(all_closes)
            require(row["close_target_long"] == closing_target, f"Wrong closing target on {stamp}")
            require((row["shares"] > 0) == prior_target and ((notional != 0) == (prior_target != (shares > 0))),
                    f"Unscheduled or missing strategy trade on {stamp}")
            if notional > 0:
                require(abs(row["cash"]) <= tolerance, f"SMA purchase underinvests on {stamp}")
        elif book == "cash":
            require(not any((notional, row["shares"], cost)), f"Cash book traded on {stamp}")
        elif book == "buy_hold":
            require(notional >= 0 and abs(notional + cost - (cash + check_interest)) <= tolerance,
                    f"Buy and hold spends unavailable cash or omits reinvestment on {stamp}")
        elif stamp[:7] != last_month:
            marked = row["shares"] * bar.opening
            require(abs(marked - WEIGHT * (marked + row["cash"])) <= tolerance,
                    f"Incorrect post-fee fixed weight on {stamp}")
        else:
            require(notional == 0, f"Unscheduled fixed-weight rebalance on {stamp}")

        require((row["fill_price"] == bar.opening if notional else row["fill_price"] == "")
                and row["shares"] >= 0 and row["cash"] >= 0, f"Invalid fill or balance on {stamp}")
        errors = [
            row["prior_cash"] - cash, row["prior_shares"] - shares,
            row["interest"] - check_interest, row["dividend_cash"] - dividend, row["capital_gain_cash"] - gain,
            row["cash"] - (available - notional - cost), cost - abs(notional) * FEE,
            row["shares"] - shares - row["shares_delta"], row["shares_delta"] * bar.opening - notional,
            row["position_value"] - row["shares"] * bar.closing,
            row["equity"] - row["cash"] - row["position_value"], row["bridge_residual"],
            row["daily_return"] - (row["equity"] / equity - 1),
            row["gross_turnover"] - abs(notional) / equity,
        ]
        max_residual = max(max_residual, *(abs(value) for value in errors))
        require(max_residual <= tolerance, f"Unreconciled {book} on {stamp}")
        cash, shares, equity = row["cash"], row["shares"], row["equity"]
        prior_date, last_month = stamp, stamp[:7]
        closing_history.append(float(bar.closing))
    return {"portfolio": book, "sessions": len(ledger),
            "fills": sum(bool(row["signed_notional"]) for row in ledger),
            "total_cost": fsum(float(row["cost"]) for row in ledger),
            "maximum_identity_residual": str(max_residual), "status": "PASS"}
