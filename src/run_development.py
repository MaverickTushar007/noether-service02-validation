"""Run the Phase 2 development demonstration using the verified local snapshot."""
import argparse
import csv
import hashlib
import io
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import yaml

from src.portfolio import BAR_COLUMNS, simulate
from src.signals import daily_signals

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "20261126T193506990307Z"
RAW = f"data/raw/{SNAPSHOT}/spy.csv"
ANALYSIS = f"data/analysis/{SNAPSHOT}/spy.csv"
RAW_HASH = "fc1ae03b018d63b75fa01f9f2163d3c17577a1d2370b7572e0b2c422b415e577"
ANALYSIS_HASH = "6a15b1c2c2a308922c7d9ad30942ba09c17ca29a3dc9e4452210db4d0af6dfa9"
START, END = "2011-01-01", "2018-12-31"
STARTING_CASH, COST_RATE = 100_000, 0.0005


def digest(content):
    return hashlib.sha256(content).hexdigest()


def load_development(root):
    manifest = json.loads((root / "evidence" / SNAPSHOT / "manifest.json").read_text())
    if (manifest["status"], manifest["snapshot"], manifest["symbol"], manifest["price_currency"]) != (
        "complete", SNAPSHOT, "SPY", "USD"
    ):
        raise ValueError("Unexpected frozen manifest")
    for relative, pinned in [(RAW, RAW_HASH), (ANALYSIS, ANALYSIS_HASH)]:
        content = (root / relative).read_bytes()
        if digest(content) != pinned or manifest["files"][relative] != pinned:
            raise ValueError(f"Frozen dataset hash mismatch: {relative}")

    # The last verified byte buffer is the exact analysis CSV parsed below.
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    if not {"trading_date", *BAR_COLUMNS}.issubset(reader.fieldnames or []):
        raise ValueError("Unexpected frozen CSV schema")
    rows = []
    for row in reader:
        date = row["trading_date"]
        if date > END:
            break
        if date >= START:
            rows.append({"trading_date": date, **{column: float(row[column]) for column in BAR_COLUMNS}})
    return pd.DataFrame(rows).set_index("trading_date")


def run(output):
    spec_path = ROOT / "config/research_spec.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    if spec["asset"] != "SPY" or spec["development"] != {"start": START, "end": END}:
        raise ValueError("Unexpected development specification")
    if spec["sma"] != {"fast": 21, "slow": 50}:
        raise ValueError("Unexpected SMA lookbacks")

    bars = load_development(ROOT)
    signals = daily_signals(bars["Close"], **spec["sma"])
    trades, ledger = simulate(bars, signals["target_long"], STARTING_CASH, COST_RATE)
    final = ledger.iloc[-1]
    distributions = ledger[["dividend_cash", "capital_gain_cash"]].sum()
    totals = {
        "sessions": len(ledger),
        "first_session": ledger.index[0],
        "last_session": ledger.index[-1],
        "first_ready_signal": signals.index[signals["ready"]][0],
        "fills": len(trades),
        "ending_cash": float(final.cash),
        "ending_shares": float(final.shares),
        "ending_position_value": float(final.position_value),
        "ending_equity": float(final.equity),
        "unfilled_final_target_change": bool(signals.iloc[-1].target_long) != bool(final.shares),
        "dividend_cash": float(distributions.dividend_cash),
        "capital_gain_cash": float(distributions.capital_gain_cash),
        "development_capital_gain_events": int(bars["Capital Gains"].ne(0).sum()),
        "net_trade_cash": float(ledger["net_trade_cash"].sum()),
        "trading_cost": float(ledger["trade_cost"].sum()),
        "max_abs_cash_residual": float(ledger["cash_residual"].abs().max()),
        "max_abs_equity_bridge_residual": float(ledger["equity_bridge_residual"].abs().max()),
    }

    output.mkdir(parents=True, exist_ok=False)
    signals.to_csv(output / "signals.csv")
    trades.to_csv(output / "trades.csv", index=False)
    ledger.to_csv(output / "daily_equity.csv")
    inputs = [spec_path, ROOT / "reports/strategy-spec.md", ROOT / "requirements-lock.txt",
              ROOT / "evidence" / SNAPSHOT / "manifest.json", Path(__file__),
              ROOT / "src/signals.py", ROOT / "src/portfolio.py"]
    record = {
        "command_arguments": [sys.executable, *sys.orig_argv[1:]],
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("pandas", "numpy", "PyYAML", "yfinance")},
        "frozen_input": {RAW: RAW_HASH, ANALYSIS: ANALYSIS_HASH},
        "source_sha256": {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in inputs},
        "parameters": {
            "symbol": spec["asset"], "development_start": START, "development_end": END,
            "sma": spec["sma"], "starting_cash": STARTING_CASH, "currency": "USD",
            "cost_rate": COST_RATE, "idle_cash_interest_rate": 0,
        },
        "accounting": totals,
        "output_sha256": {name: digest((output / name).read_bytes())
                          for name in ("signals.csv", "trades.csv", "daily_equity.csv")},
    }
    (output / "run.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    print(f"{totals['sessions']} development sessions, {totals['fills']} fills. Evidence: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/phase2-development")
    run(parser.parse_args().output)
