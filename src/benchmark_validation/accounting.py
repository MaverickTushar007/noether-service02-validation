"""Independent portfolio arithmetic and historical cash conventions."""
from bisect import bisect_left
from collections import deque
from datetime import date
from decimal import Decimal as D, localcontext

ZERO, ONE = D(0), D(1)
INITIAL, FEE, WEIGHT = D(100000), D("0.0005"), D("0.6658769500542819")
PORTFOLIOS = ("sma", "buy_hold", "cash", "fixed_mix")


def parse_rates(rows):
    previous = ""
    rates = {}
    for row in rows:
        stamp, rate = row["observation_date"], row["DTB3"]
        date.fromisoformat(stamp)
        if stamp <= previous:
            raise ValueError("Duplicated or unordered DTB3 observation")
        previous = stamp
        if rate not in ("", "."):
            number = D(rate)
            if not number.is_finite() or ONE - number * 91 / 36000 <= 0:
                raise ValueError(f"Invalid bank-discount rate on {stamp}")
            rates[stamp] = number
    return rates


def cash_intervals(dates, rates):
    rate_dates = sorted(rates)
    yield "", "", 0, ZERO
    for previous, current in zip(dates, dates[1:]):
        index = bisect_left(rate_dates, previous) - 1
        if index < 0:
            raise ValueError(f"No eligible DTB3 observation for {previous}")
        stamp = rate_dates[index]
        before = date.fromisoformat(previous)
        if (before - date.fromisoformat(stamp)).days > 10:
            raise ValueError(f"Stale DTB3 rate on {previous}")
        days = (date.fromisoformat(current) - before).days
        quote = rates[stamp]
        with localcontext(prec=40):
            bill_price = ONE - quote * 91 / 36000
            accrual = bill_price ** (-D(days) / 91) - ONE
        yield stamp, quote, days, accrual


def target(closes):
    return len(closes) == 50 and sum(list(closes)[-21:]) * 50 > sum(closes) * 21


def fixed_notional(cash, position):
    drift = WEIGHT * (cash + position) - position
    sign = ONE if drift >= 0 else -ONE
    return drift / (ONE + sign * WEIGHT * FEE)


def simulate(book, bars, intervals, warmup=()):
    if book not in PORTFOLIOS or not bars or len(bars) != len(intervals) or len(warmup) not in (0, 50):
        raise ValueError("Invalid portfolio inputs")
    if warmup and (sorted(set(day for day, _ in warmup)) != [day for day, _ in warmup]
                   or warmup[-1][0] >= bars[0].date
                   or any(not close.is_finite() or close <= 0 for _, close in warmup)):
        raise ValueError("Invalid SMA carry-in history")
    dates = [bar.date for bar in bars]
    if dates != sorted(set(dates)):
        raise ValueError("Unordered portfolio bars")
    for bar in bars:
        if (any(not p.is_finite() or p <= 0 for p in (bar.opening, bar.closing))
                or any(not d.is_finite() or d < 0 for d in (bar.dividend, bar.capital_gain))
                or bar.split != 0):
            raise ValueError(f"Invalid bar or unsupported split on {bar.date}")

    with localcontext(prec=40):
        closes = deque((close for _, close in warmup), maxlen=50)
        previous_date = warmup[-1][0] if warmup else ""
        cash, shares = INITIAL, ZERO
        previous_equity, previous_close = INITIAL, ZERO
        ledger = []
        for i, (bar, (rate_date, rate, days, cash_return)) in enumerate(zip(bars, intervals, strict=True)):
            date_label = bar.date
            start_cash, start_shares = cash, shares
            interest = start_cash * cash_return if book != "sma" else ZERO
            dividend_cash = shares * bar.dividend
            gain_cash = shares * bar.capital_gain
            distribution = dividend_cash + gain_cash
            before_fill = cash + interest + distribution
            prior_target = target(closes) if book == "sma" else None
            reason, notional = "", ZERO
            month_open = i == 0 or date_label[:7] != bars[i-1].date[:7]
            if book == "sma":
                if prior_target and not shares:
                    reason, notional = "signal_entry", before_fill / (ONE + FEE)
                elif not prior_target and shares:
                    reason, notional = "signal_exit", -shares * bar.opening
            elif book == "buy_hold" and (i == 0 or start_cash > 0):
                reason = "initial_buy" if i == 0 else "distribution_reinvestment"
                notional = (cash + interest) / (ONE + FEE)
            elif book == "fixed_mix" and month_open:
                reason, notional = "monthly_rebalance", fixed_notional(before_fill, shares * bar.opening)

            fees = abs(notional) * FEE
            delta = notional / bar.opening
            cash, shares = before_fill - notional - fees, shares + delta
            if abs(cash) < D("1e-30"):
                cash = ZERO
            if abs(shares) < D("1e-30"):
                shares = ZERO
            position = shares * bar.closing
            equity = cash + position
            closes.append(bar.closing)
            ledger.append({
                "date": date_label, "open": bar.opening, "close": bar.closing,
                "rate_date": rate_date, "rate_percent_discount": rate, "accrual_days": days,
                "cash_proxy_return": cash_return, "prior_cash": start_cash, "prior_shares": start_shares,
                "interest": interest, "dividend_cash": dividend_cash, "capital_gain_cash": gain_cash,
                "signal_date": previous_date if book == "sma" else "",
                "open_target_long": prior_target if book == "sma" else "",
                "close_target_long": target(closes) if book == "sma" else "",
                "trade_reason": reason if notional else "", "fill_price": bar.opening if notional else "",
                "shares_delta": delta, "signed_notional": notional, "cost": fees,
                "open_position_value": shares * bar.opening, "cash": cash, "shares": shares,
                "position_value": position, "equity": equity,
                "daily_return": equity / previous_equity - ONE,
                "gross_turnover": abs(notional) / previous_equity,
                "bridge_residual": equity - (previous_equity + start_shares * (bar.opening - previous_close)
                                            + shares * (bar.closing - bar.opening) + interest + distribution - fees),
            })
            previous_date, previous_equity, previous_close = date_label, equity, bar.closing
        return ledger
