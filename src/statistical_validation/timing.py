"""Exchange-session timing, regime labels and deliberate lookahead challenges."""
from collections import defaultdict
from dataclasses import replace

import pandas as pd

from src.independent_validation.reproduction import reproduce


def development_rows(rows, start, end):
    for row in rows:
        date = row["trading_date"]
        if date > end:
            break
        if date >= start:
            yield row


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit_orders(signals, fills, ledger, bars, dates):
    require([row["trading_date"] for row in signals] == dates, "Signal dates differ from development calendar")
    require([row["trading_date"] for row in ledger] == dates, "Ledger dates differ from development calendar")
    target = [row["target_long"] for row in signals]
    pending = False
    expected = []
    for index, (wanted, daily) in enumerate(zip([False, *target[:-1]], ledger, strict=True)):
        if wanted != pending:
            expected.append((dates[index - 1], dates[index], "BUY" if wanted else "SELL", bars[index].opening))
        require((daily["shares"] > 0) == wanted, f"Position precedes or lags closing target on {dates[index]}")
        pending = wanted
    actual = [(row["signal_date"], row["trade_date"], row["side"], row["price"]) for row in fills]
    require(actual == expected, "A fill differs from the eligible next-session open")
    return len(expected)


def period_key(date, frequency):
    timestamp = pd.Timestamp(date)
    if frequency == "daily":
        return date
    if frequency == "weekly":
        return (timestamp - pd.Timedelta(days=timestamp.weekday())).strftime("%Y-%m-%d")
    if frequency == "monthly":
        return date[:7]
    raise ValueError(f"Unknown frequency: {frequency}")


def completed_periods(frequency, observed, schedule):
    grouped = defaultdict(list)
    for date in schedule:
        grouped[period_key(date, frequency)].append(date)
    return {key: dates[-1] for key, dates in grouped.items() if all(date in observed for date in dates)}


def build_regime(frequency, closes, schedule, fast=21, slow=50):
    dates = list(closes)
    following = dict(zip(dates, dates[1:]))
    period_ends = completed_periods(frequency, closes, schedule)
    values = [closes[date] for date in period_ends.values()]
    rows = []
    prior = False
    for index, (period, date) in enumerate(period_ends.items(), 1):
        fast_sum = sum(values[index-fast:index]) if index >= fast else None
        slow_sum = sum(values[index-slow:index]) if index >= slow else None
        ready = slow_sum is not None
        target = ready and fast_sum * slow > slow_sum * fast
        rows.append({
            "frequency": frequency, "period": period, "close_date": date,
            "next_open_date": following.get(date, ""), "close": closes[date],
            "sma_fast": fast_sum / fast if fast_sum is not None else "",
            "sma_slow": slow_sum / slow if ready else "", "ready": ready,
            "label": ("LONG" if target else "CASH") if ready else "WARMUP",
            "transition": ("ENTER" if target else "EXIT") if target != prior else "",
        })
        prior = target
    return rows


def audit_regime(rows, observed, schedule, frequency):
    """Check completeness by scanning calendar boundaries independently of grouping."""
    observed = set(observed)
    candidates = []
    period = []
    for index, date in enumerate(schedule):
        period.append(date)
        if index + 1 == len(schedule) or period_key(date, frequency) != period_key(schedule[index+1], frequency):
            if observed.issuperset(period):
                release = schedule[index+1] if index + 1 < len(schedule) and schedule[index+1] in observed else ""
                candidates.append((date, release))
            period = []
    require([(row["close_date"], row["next_open_date"]) for row in rows] == candidates,
            "Period uses an incomplete close or an ineligible release")


def summarize_regime(rows):
    ready = [row for row in rows if row["ready"]]
    return {
        "frequency": rows[0]["frequency"], "completed_bars": len(rows), "warmup_bars": len(rows) - len(ready),
        "ready_labels": len(ready), "long_labels": sum(r["label"] == "LONG" for r in ready),
        "cash_labels": sum(r["label"] == "CASH" for r in ready),
        "enter_transitions": sum(r["transition"] == "ENTER" for r in ready),
        "exit_transitions": sum(r["transition"] == "EXIT" for r in ready),
        "ready_labels_released_in_development": sum(bool(r["next_open_date"]) for r in ready),
        "first_ready_close": ready[0]["close_date"] if ready else "",
        "last_ready_close": ready[-1]["close_date"] if ready else "",
    }


def prefix_check(bars, dates):
    # Fixed midpoint. Amplify all later prices to detect future dependence.
    cut = len(bars) // 2
    original = reproduce(bars[:cut], dates[:cut])
    stressed = [*bars[:cut], *(replace(bar, closing=bar.closing * 7, opening=bar.opening * 2)
                              for bar in bars[cut:])]
    signals, fills, daily = reproduce(stressed, dates)
    return (signals[:cut], [trade for trade in fills if trade["trade_date"] <= dates[cut-1]],
            daily[:cut]) == original
