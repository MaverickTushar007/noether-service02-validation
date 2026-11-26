"""Acquire and audit one immutable SPY snapshot."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "SPY"
TIMEZONE = "America/New_York"
REQUEST = dict(start="2011-01-01", end="2023-01-01", interval="1d",
               auto_adjust=False, actions=True, repair=False, keepna=True)
PRICES = ["Open", "High", "Low", "Close", "Adj Close"]
REQUIRED = [*PRICES, "Volume", "Dividends", "Stock Splits"]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(raw):
    if not set(REQUIRED).issubset(raw.columns):
        raise ValueError(f"Missing provider columns: {sorted(set(REQUIRED) - set(raw.columns))}")
    if not raw.columns.is_unique:
        raise ValueError("Duplicate provider columns")
    if not isinstance(raw.index, pd.DatetimeIndex) or raw.index.tz is None or raw.index.hasnans:
        raise ValueError("Expected timezone-aware provider timestamps with no missing dates")
    dated = raw.copy()
    dated.index = dated.index.tz_convert(TIMEZONE).strftime("%Y-%m-%d")
    dated.index.name = "trading_date"
    return dated


def audit(frame):
    dates = pd.DatetimeIndex(frame.index)
    last = pd.Timestamp(REQUEST["end"]) - pd.Timedelta(days=1)
    calendar = xcals.get_calendar("XNYS", start=REQUEST["start"], end=last)
    expected = calendar.sessions
    if expected.tz is not None:
        expected = expected.tz_localize(None)

    def labels(index):
        return pd.DatetimeIndex(index).strftime("%Y-%m-%d").tolist()

    def flagged(mask):
        return labels(dates[mask.fillna(False).to_numpy(dtype=bool)])

    prices = frame[PRICES]
    volume = frame["Volume"]
    close = frame["Close"]
    dividends = frame["Dividends"]
    splits = frame["Stock Splits"]
    ratio = frame["Adj Close"] / close
    ratio_change = ratio / ratio.shift()
    implied_change = 1 / (1 - dividends / close.shift())
    ohlc_violation = ((frame["High"] < frame[["Open", "Low", "Close"]].max(axis=1)) |
                      (frame["Low"] > frame[["Open", "High", "Close"]].min(axis=1)))
    findings = {
        "observation_count": len(frame),
        "first_date": dates.min().strftime("%Y-%m-%d"),
        "last_date": dates.max().strftime("%Y-%m-%d"),
        "expected_session_count": len(expected),
        "missing_expected_sessions": labels(expected.difference(dates)),
        "unexpected_sessions": labels(dates.difference(expected)),
        "duplicate_dates": labels(dates[dates.duplicated(keep=False)].unique()),
        "chronologically_ordered": bool(dates.is_monotonic_increasing),
        "missing_values": {column: flagged(frame[column].isna()) for column in REQUIRED},
        "nonfinite_prices": {column: flagged(~np.isfinite(prices[column])) for column in PRICES},
        "nonpositive_prices": {column: flagged(prices[column] <= 0) for column in PRICES},
        "ohlc_inconsistency_dates": flagged(ohlc_violation),
        "negative_volume_dates": flagged(volume < 0),
        "nonfinite_volume_dates": flagged(~np.isfinite(volume)),
        "large_close_returns": {
            date: float(value) for date, value in close.pct_change(fill_method=None).items()
            if np.isfinite(value) and abs(value) > 0.08
        },
        "dividend_events": {date: float(value) for date, value in dividends.dropna().items()
                            if np.isfinite(value) and value != 0},
        "split_events": {date: float(value) for date, value in splits.dropna().items()
                         if np.isfinite(value) and value != 0},
        "adjustment_review_dates": flagged(
            ((ratio_change - implied_change).abs() > 0.0005) & splits.eq(0)),
        "split_dates_excluded_from_dividend_factor_check": flagged(splits.notna() & splits.ne(0)),
        "invalid_adjustment_ratio_dates": flagged(~np.isfinite(ratio) | ratio.le(0)),
    }
    findings["complete"] = not (
        findings["missing_expected_sessions"] or findings["unexpected_sessions"]
        or findings["duplicate_dates"] or not findings["chronologically_ordered"]
        or any(findings["missing_values"].values())
        or any(findings["nonfinite_prices"].values()) or findings["nonfinite_volume_dates"]
    )
    return findings


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_report(path, snapshot, results):
    lines = [f"# SPY data quality audit · {snapshot}", "",
             "XNYS scheduled sessions exclude weekends and exchange holidays. Review flags are observations. "
             "No independent source reconciliation was performed.", "",
             "Close-to-close moves above 8% in absolute value are flagged. The dividend factor check "
             "flags deviations above 0.0005 (5 basis points of the factor). It uses the previous close "
             "and omits split dates and the first row.", ""]
    for key, value in results.items():
        lines.extend([f"## {key.replace('_', ' ').capitalize()}", "",
                      "```json", json.dumps(value, indent=2), "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def acquire(root):
    started = datetime.now(timezone.utc)
    snapshot = started.strftime("%Y%m%dT%H%M%S%fZ")
    evidence = root / "evidence" / snapshot
    evidence.mkdir(parents=True, exist_ok=False)
    manifest = {
        "snapshot": snapshot,
        "started_utc": started.isoformat(),
        "provider": "Yahoo Finance via yfinance.Ticker.history",
        "yfinance_version": yf.__version__,
        "exchange_calendars_version": xcals.__version__,
        "symbol": SYMBOL,
        "request": REQUEST,
        "yfinance_hide_exceptions": False,
        "trading_timezone": TIMEZONE,
        "calendar": "XNYS (US equity session proxy)",
        "source_limitations": "Vendor data are subject to revisions and are not exchange-certified. "
                              "Adjusted close is not an executable transaction price.",
        "files": {},
    }

    def record(path):
        manifest["files"][str(path.relative_to(root))] = sha256(path)

    try:
        yf.config.debug.hide_exceptions = False
        ticker = yf.Ticker(SYMBOL)
        raw = ticker.history(**REQUEST)
        manifest["retrieved_utc"] = datetime.now(timezone.utc).isoformat()
        raw_dir = root / "data" / "raw" / snapshot
        raw_dir.mkdir(parents=True, exist_ok=False)
        raw_path = raw_dir / "spy.csv"
        raw.to_csv(raw_path)
        record(raw_path)
        if raw.empty:
            raise ValueError("Provider returned no observations")
        manifest["price_currency"] = ticker.history_metadata.get("currency")
        manifest["provider_exchange_timezone"] = ticker.history_metadata.get("exchangeTimezoneName")
        frame = normalize(raw)
        results = audit(frame)
        summary = evidence / "audit.json"
        write_json(summary, results)
        record(summary)
        report_dir = root / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report = report_dir / f"{snapshot}.md"
        write_report(report, snapshot, results)
        record(report)
        if not results["complete"]:
            raise ValueError("Incomplete provider series. See audit.json for details")
        if manifest["provider_exchange_timezone"] != TIMEZONE:
            raise ValueError("Provider did not confirm the expected New York exchange time zone")
        if manifest["price_currency"] != "USD":
            raise ValueError("Provider did not confirm expected USD currency")
        analysis_dir = root / "data" / "analysis" / snapshot
        analysis_dir.mkdir(parents=True, exist_ok=False)
        analysis = analysis_dir / "spy.csv"
        frame.to_csv(analysis)
        record(analysis)
        manifest["status"] = "complete"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        report_dir = root / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report = report_dir / f"{snapshot}.md"
        if not report.exists():
            report.write_text(f"# SPY snapshot failure · {snapshot}\n\n"
                              f"{manifest['error']}\n\n"
                              "No analysis-ready dataset was published. See the manifest for available evidence.\n",
                              encoding="utf-8")
            record(report)
        print(f"{manifest['error']} — {evidence / 'manifest.json'}")
        return 1
    finally:
        write_json(evidence / "manifest.json", manifest)
    print(f"Snapshot {snapshot} — {len(frame)} observations, {frame.index.min()} through {frame.index.max()}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(acquire(ROOT))
