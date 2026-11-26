"""Aligned performance measures and paired development/holdout inference."""
import numpy as np

from src.statistical_validation.statistics import block_means
from .accounting import INITIAL

ANNUAL = 252
WINDOWS = (
    ("2019 calendar year", "2019-01-01", "2019-12-31"),
    ("2020 selloff", "2020-02-19", "2020-03-23"),
    ("2020 rebound", "2020-03-24", "2020-12-31"),
    ("2022 calendar year", "2022-01-01", "2022-12-31"),
)


def drawdowns(equity):
    balances = np.r_[float(INITIAL), equity]
    return (1 - balances / np.maximum.accumulate(balances))[1:]


def measures(book, ledger):
    eq = np.array([float(row["equity"]) for row in ledger])
    daily = np.array([float(row["daily_return"]) for row in ledger])
    risk_free = np.array([float(row["cash_proxy_return"]) for row in ledger])
    excess = daily - risk_free
    sigma = excess.std(ddof=1)
    growth = eq[-1] / float(INITIAL)
    dd = drawdowns(eq)
    longest = current = 0
    for depth in dd:
        current = current + 1 if depth > 0 else 0
        longest = max(longest, current)
    gross = sum(float(row["gross_turnover"]) for row in ledger)
    return {
        "portfolio": book, "sessions": len(ledger), "start": ledger[0]["date"], "end": ledger[-1]["date"],
        "ending_equity": float(eq[-1]), "cumulative_return": float(growth - 1),
        "cagr": float(growth ** (ANNUAL / len(ledger)) - 1),
        "annualized_volatility": float(daily.std(ddof=1) * np.sqrt(ANNUAL)),
        "excess_sharpe": float(excess.mean() / sigma * np.sqrt(ANNUAL)) if book != "cash" and sigma > 0 else "",
        "maximum_drawdown": float(max(dd)), "longest_underwater_sessions": longest,
        "mean_invested_weight": float(np.mean([float(row["position_value"]) for row in ledger] / eq)),
        "fraction_long_closes": float(np.mean([row["shares"] > 0 for row in ledger])),
        "gross_turnover": gross, "annualized_gross_turnover": gross * ANNUAL / len(ledger),
        "fills": sum(bool(row["signed_notional"]) for row in ledger),
        "modeled_cost_usd": sum(float(row["cost"]) for row in ledger),
        "dividends_usd": sum(float(row["dividend_cash"]) for row in ledger),
        "capital_gains_usd": sum(float(row["capital_gain_cash"]) for row in ledger),
        "cash_interest_usd": sum(float(row["interest"]) for row in ledger),
    }


def paired(bench, strategy, benchmark):
    if [row["date"] for row in strategy] != [row["date"] for row in benchmark]:
        raise ValueError("Unpaired return dates")
    spreads = np.array([float(a["daily_return"] - b["daily_return"])
                        for a, b in zip(strategy, benchmark, strict=True)])
    lower, upper = np.quantile(block_means(spreads, 20, 20_000, 20261127), [0.025, 0.975], method="linear")
    gap = float((strategy[-1]["equity"] - benchmark[-1]["equity"]) / INITIAL)
    return {
        "benchmark": bench, "sessions": len(spreads), "mean_daily_gap": float(spreads.mean()),
        "daily_ci_lower": float(lower), "daily_ci_upper": float(upper),
        "annualized_arithmetic_gap": float(spreads.mean() * ANNUAL),
        "annualized_ci_lower": float(lower * ANNUAL), "annualized_ci_upper": float(upper * ANNUAL),
        "compounded_total_return_gap": gap,
    }


def primary_judgment(row):
    if row["daily_ci_lower"] > 0 and row["compounded_total_return_gap"] > 0:
        return "PASS"
    if row["daily_ci_upper"] < 0 and row["compounded_total_return_gap"] < 0:
        return "FAIL"
    return "INCONCLUSIVE"


def descriptive_windows(books):
    return [
        {"window": name, "portfolio": book, "start": selected[0]["date"], "end": selected[-1]["date"],
         "sessions": len(selected),
         "cumulative_return": float(np.prod([1 + float(row["daily_return"]) for row in selected]) - 1)}
        for name, start, end in WINDOWS for book, ledger in books.items()
        if (selected := [row for row in ledger if start <= row["date"] <= end])
    ]
