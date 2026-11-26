"""Daily close-only SMA target generation."""
import pandas as pd


def daily_signals(close: pd.Series, fast: int = 21, slow: int = 50) -> pd.DataFrame:
    if not 0 < fast < slow:
        raise ValueError("Require 0 < fast < slow")
    if not close.index.is_unique or not close.index.is_monotonic_increasing:
        raise ValueError("Closes must be uniquely dated and chronological")

    sma_fast = close.rolling(fast, min_periods=fast).mean()
    sma_slow = close.rolling(slow, min_periods=slow).mean()
    return pd.DataFrame({
        "close": close,
        "sma_fast": sma_fast,
        "sma_slow": sma_slow,
        "ready": sma_slow.notna(),
        "target_long": sma_fast.gt(sma_slow),
    })
