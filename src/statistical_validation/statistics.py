"""Return, turnover and uncertainty calculations for the frozen development ledger."""
import numpy as np

ANNUAL_SESSIONS = 252
LENGTHS = (20, 10, 40)
REPLICATIONS = 20_000
SEED = 20261127
INITIAL = 100_000.0


def ledger_metrics(equity, position, shares, notional):
    equity, position, shares, notional = map(lambda v: np.asarray(v, dtype=float),
                                             (equity, position, shares, notional))
    if (not len(equity) or len({len(equity), len(position), len(shares), len(notional)}) != 1
            or not np.isfinite([equity, position, shares, notional]).all()
            or (equity <= 0).any() or (position < 0).any() or (position > equity).any()
            or (shares < 0).any() or (notional < 0).any()):
        raise ValueError("Invalid ledger vectors")
    balances = np.r_[INITIAL, equity]
    returns = balances[1:] / balances[:-1] - 1
    gross = notional / balances[:-1]
    metrics = {
        "sessions": len(returns), "long_closes": int(np.count_nonzero(shares)),
        "fraction_long_closes": float(np.mean(shares > 0)),
        "mean_close_invested_weight": float(np.mean(position / equity)),
        "gross_turnover": float(gross.sum()),
        "annualized_gross_turnover": float(gross.mean() * ANNUAL_SESSIONS),
        "ending_equity": float(equity[-1]),
        "total_return": float(equity[-1] / INITIAL - 1),
        "annualized_arithmetic_mean": float(returns.mean() * ANNUAL_SESSIONS),
        "cagr": float((equity[-1] / INITIAL) ** (ANNUAL_SESSIONS / len(returns)) - 1),
        "max_drawdown": float(np.max(1 - balances / np.maximum.accumulate(balances))),
    }
    return metrics, returns, gross


def block_means(returns, length, replications=REPLICATIONS, seed=SEED):
    values = np.asarray(returns, dtype=float)
    n = len(values)
    if values.ndim != 1 or not 1 <= length <= n or replications < 1 or not np.isfinite(values).all():
        raise ValueError("Invalid moving-block bootstrap inputs")
    full, remainder = divmod(n, length)
    blocks = np.lib.stride_tricks.sliding_window_view(values, length)
    starts = np.random.Generator(np.random.PCG64(seed)).integers(
        len(blocks), size=(replications, full + bool(remainder))
    )
    total = blocks.sum(axis=1)[starts[:, :full]].sum(axis=1)
    if remainder:
        total += blocks[:, :remainder].sum(axis=1)[starts[:, -1]]
    return total / n


def intervals(returns):
    rows = []
    for length in LENGTHS:
        lower, upper = np.quantile(block_means(returns, length), [0.025, 0.975], method="linear")
        daily = float(np.mean(returns))
        rows.append({
            "block_sessions": length, "primary": length == LENGTHS[0], "sample_sessions": len(returns),
            "overlapping_blocks": len(returns) - length + 1, "replications": REPLICATIONS, "seed": SEED,
            "mean_daily": daily, "daily_lower": float(lower), "daily_upper": float(upper),
            "annualized_mean": daily * ANNUAL_SESSIONS, "annualized_lower": float(lower * ANNUAL_SESSIONS),
            "annualized_upper": float(upper * ANNUAL_SESSIONS),
            "zero_excluded": bool(lower > 0 or upper < 0),
        })
    return rows


def positive_mean_status(rows):
    if rows[0]["daily_upper"] < 0:
        return "FAIL"
    if all(row["daily_lower"] > 0 for row in rows):
        return "PASS"
    return "INCONCLUSIVE"
