"""Produce the prespecified Phase 4 development-only evidence."""
import argparse
import csv
import hashlib
import io
import json
import platform
import sys
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

import exchange_calendars
import numpy as np
import pandas as pd

from src.independent_validation.reproduction import read_session, reproduce
from src.portfolio import simulate
from src.signals import daily_signals

from .statistics import INITIAL, LENGTHS, REPLICATIONS, SEED, block_means, intervals, ledger_metrics, positive_mean_status
from .timing import audit_orders, audit_regime, build_regime, development_rows, prefix_check, require, summarize_regime

ROOT = Path(__file__).resolve().parents[2]
CLIENT = "evidence/phase2-development"
REVIEW = "evidence/phase3-review"
SNAPSHOT = "20261126T193506990307Z"
ANALYSIS = f"data/analysis/{SNAPSHOT}/spy.csv"
PROTOCOL = "reports/statistical-protocol.md"
PROTOCOL_HASH = "c21c654781bcfc753354dacca7797ee78c51579e7ef16b65a5abfe1fd1ed6434"
START, END = "2011-01-01", "2018-12-31"
CASES = [(18, 45, 5), (21, 50, 5), (24, 55, 5), (21, 50, 10), (21, 50, 20)]


def sha(content):
    return hashlib.sha256(content).hexdigest()


def verified_inputs():
    hashes, contents = {}, {}
    references = {
        "evidence/20261126T193436807402Z/manifest.json": ["files"],
        f"evidence/{SNAPSHOT}/manifest.json": ["files"],
        f"{CLIENT}/run.json": ["frozen_input", "source_sha256", "output_sha256"],
        f"{REVIEW}/evidence_manifest.json": ["input_sha256", "reviewer_source_sha256", "output_sha256"],
    }
    for name, sections in references.items():
        manifest = (ROOT / name).read_bytes()
        hashes[name] = sha(manifest)
        document = json.loads(manifest)
        for section in sections:
            for path, expected in document[section].items():
                key = str(Path(name).parent / path) if section == "output_sha256" else path
                if key not in contents:
                    contents[key] = (ROOT / key).read_bytes()
                require(sha(contents[key]) == expected, f"Frozen hash mismatch: {key}")
                hashes[key] = expected
    require(set(contents).issuperset([ANALYSIS, f"{CLIENT}/daily_equity.csv"]), "Incomplete hash references")
    protocol = sha((ROOT / PROTOCOL).read_bytes())
    require(protocol == PROTOCOL_HASH, "Protocol differs from its pre-calculation hash")
    hashes[PROTOCOL] = protocol
    return hashes, contents


def rows(content):
    return csv.DictReader(io.StringIO(content.decode("utf8")))


def records(content, integer_booleans=(), decimal_fields=()):
    result = list(rows(content))
    for row in result:
        for field in integer_booleans:
            require(row[field] in {"True", "False"}, f"Invalid boolean {field}")
            row[field] = row[field] == "True"
        for field in decimal_fields:
            row[field] = Decimal(row[field])
    return result


def statistics_for(ledger, trades):
    by_date = {row["trade_date"]: float(row["notional"]) for row in trades}
    require(len(by_date) == len(trades), "More than one fill on a strategy session")
    return ledger_metrics(
        [row["equity"] for row in ledger],
        [row["position_value"] for row in ledger],
        [row["shares"] for row in ledger],
        [by_date.get(row["trading_date"], 0) for row in ledger],
    )


def independent_agreement(client, review, fields):
    require(len(client) == len(review), "Independent paths have different row counts")
    for field in fields:
        left = [r[field] for r in client]
        right = [r[field] for r in review]
        if field.endswith("date") or field in {"side", "target_long"}:
            require(left == right, f"Independent paths differ on {field}")
        else:
            atol = 1e-9 if "shares" in field else 1e-8
            require(np.allclose(np.asarray(left, float), np.asarray(right, float), rtol=1e-12, atol=atol),
                    f"Independent paths differ on {field}")


def diagnostics(bars, dates, client_ledger, client_trades):
    frame = pd.DataFrame({
        "Open": [float(b.opening) for b in bars], "Close": [float(b.closing) for b in bars],
        "Dividends": [float(b.dividend) for b in bars], "Capital Gains": [float(b.capital_gain) for b in bars],
        "Stock Splits": [float(b.split) for b in bars],
    }, index=pd.Index(dates, name="trading_date"))
    cases = []
    for fast, slow, bps in CASES:
        rate = Decimal(bps) / 10_000
        signals, trades, ledger = reproduce(bars, dates, fast=fast, slow=slow, fee=rate)
        client_signals = daily_signals(frame["Close"], fast, slow)
        client_signal_rows = client_signals.reset_index().to_dict("records")
        independent_agreement(client_signal_rows, signals, ("trading_date", "target_long"))
        fills, daily = simulate(frame, client_signals["target_long"], cost_rate=float(rate))
        fill_rows = fills.to_dict("records")
        daily_rows = daily.reset_index().to_dict("records")
        trade_fields = ("signal_date", "trade_date", "side", "price", "shares_delta", "notional", "cost")
        ledger_fields = ("trading_date", "cash", "shares", "equity", "dividend_cash", "capital_gain_cash")
        independent_agreement(fill_rows, trades, trade_fields)
        independent_agreement(daily_rows, ledger, ledger_fields)
        if (fast, slow, bps) == (21, 50, 5):
            independent_agreement(client_trades, trades, trade_fields)
            independent_agreement(client_ledger, ledger, ledger_fields)
        require(audit_orders(signals, trades, ledger, bars, dates) == len(trades), "Diagnostic timing failed")
        residual = max(abs(row["equity_bridge_residual"]) for row in ledger)
        require(residual <= Decimal("1e-8") and all(row["cash"] >= 0 and row["shares"] >= 0
                                                  for row in ledger), "Diagnostic reconciliation failed")
        stats, _, _ = statistics_for(ledger, trades)
        cases.append({"fast": fast, "slow": slow, "cost_bps_per_fill": bps,
                      "fills": len(trades), "total_cost_usd": float(sum(row["cost"] for row in trades)),
                      "max_equity_bridge_residual_usd": float(residual), **stats})
    return cases


def save_csv(path, data):
    with path.open("x", newline="", encoding="utf8") as fh:
        writer = csv.DictWriter(fh, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)


def run(output):
    hashes, content = verified_inputs()
    bars = [read_session(row) for row in development_rows(rows(content[ANALYSIS]), START, END)]
    market_calendar = exchange_calendars.get_calendar("XNYS", start="2010-12-20", end="2019-01-10")
    schedule = market_calendar.sessions.strftime("%Y-%m-%d").tolist()
    dates = [day for day in schedule if START <= day <= END]
    require([b.date for b in bars] == dates, "Missing or out-of-scope market data")

    ledger = records(content[f"{CLIENT}/daily_equity.csv"], decimal_fields=("shares",))
    trades = records(content[f"{CLIENT}/trades.csv"], decimal_fields=("price",))
    signal = records(content[f"{CLIENT}/signals.csv"], integer_booleans=("target_long",))
    fills = audit_orders(signal, trades, ledger, bars, dates)
    require(prefix_check(bars, dates), "Future prices changed prior signals, fills or equity")
    stats, returns, turnover = statistics_for(ledger, trades)
    reviewer_ledger = records(content[f"{REVIEW}/reviewer_daily_equity.csv"])
    client_path, frozen_path = [r["trading_date"] for r in ledger], [r["trading_date"] for r in reviewer_ledger]
    require(client_path == frozen_path, "Frozen equity dates disagree")
    review_eq = np.asarray([INITIAL, *(float(row["equity"]) for row in reviewer_ledger)])
    require(np.allclose(returns, np.diff(review_eq) / review_eq[:-1], rtol=1e-12, atol=1e-12),
            "Independent frozen return vectors disagree")

    bounds = intervals(returns)
    # Independently concatenate explicit sampled blocks for the first three draws at each length.
    for length in LENGTHS:
        starts = np.random.Generator(np.random.PCG64(SEED)).integers(
            len(returns) - length + 1, size=(3, (len(returns) + length - 1) // length)
        )
        literal = [np.concatenate([returns[start:start+length] for start in row])[:len(returns)].mean()
                   for row in starts]
        require(np.allclose(literal, block_means(returns, length, 3), rtol=0, atol=1e-14),
                "Explicit block concatenation disagrees")

    cases = diagnostics(bars, dates, ledger, trades)
    closes = {b.date: b.closing for b in bars}
    labels, regimes = [], []
    for frequency in ("daily", "weekly", "monthly"):
        regime = build_regime(frequency, closes, schedule)
        audit_regime(regime, dates, schedule, frequency)
        if frequency == "daily":
            require([r["label"] == "LONG" for r in regime] == [r["target_long"] for r in signal],
                    "Daily descriptive regimes differ from frozen targets")
        labels += regime
        regimes.append(summarize_regime(regime))

    findings = [
        ("P401", "PASS", "Integrity and scope", "Phase 1–3 references and protocol verified. Development rows matched the calendar."),
        ("P402", "PASS", "Timing and code-level leakage", f"Checked {fills} fills and closing exposure. A future-price perturbation preserved the development prefix."),
        ("P403", "PASS", "Uncertainty calculation", "Ledger returns matched the reviewer ledger. Explicit block concatenation and deterministic benchmark tests check the sampler."),
        ("P404", positive_mean_status(bounds), "Positive development-period mean", "Protocol requires strictly positive lower bounds for all block lengths. See bootstrap.csv."),
        ("P405", "PASS", "Exploratory parameter and cost diagnostics", "Two independent calculation paths agreed. This checks implementation."),
        ("P406", "PASS", "Descriptive period timing", "Complete exchange periods and next-open release checked for each frequency."),
        ("P407", "INCONCLUSIVE", "Predictive reliability and incremental value", "No untouched evaluation, risk comparison or benchmark test."),
        ("P408", "INCONCLUSIVE", "Historical selection and implementation bias", "No selection provenance, publication latency, actual fills or payment-date cash records."),
    ]
    daily = [{"trading_date": date, "return": float(ret), "gross_turnover": float(turn),
              "shares": str(row["shares"]), "close_invested_weight": float(row["position_value"]) / float(row["equity"])}
             for date, ret, turn, row in zip(dates, returns, turnover, ledger, strict=True)]
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [
        ("ledger_statistics.csv", [stats]), ("daily_returns.csv", daily), ("bootstrap.csv", bounds),
        ("parameter_sensitivity.csv", [row for row in cases if row["cost_bps_per_fill"] == 5]),
        ("cost_sensitivity.csv", [row for row in cases if (row["fast"], row["slow"]) == (21, 50)]),
        ("regime_labels.csv", labels), ("regime_summary.csv", regimes),
        ("findings.csv", [dict(zip(("id", "status", "criterion", "evidence"), row, strict=True)) for row in findings]),
    ]:
        save_csv(output / name, data)

    from .report import write_figures, write_report
    write_figures(output, bounds, cases)
    write_report(output, dates, stats, bounds, cases, regimes, findings)
    sources = [*sorted(Path(__file__).parent.glob("*.py")), ROOT / "tests/test_statistical_validation.py"]
    manifest = {
        "command": [sys.executable, *sys.orig_argv[1:]],
        "test_command": [".venv/bin/python", "-m", "pytest", "-q", "-rs"],
        "execution_log": "evidence/phase4-run.txt",
        "python": platform.python_version(),
        "packages": {p: version(p) for p in ("numpy", "pandas", "matplotlib", "exchange-calendars", "pytest")},
        "parameters": {"start": START, "end": END, "cases": CASES, "blocks": LENGTHS,
                       "replications": REPLICATIONS, "seed": SEED, "rng": "PCG64", "annual_sessions": 252},
        "input_sha256": hashes,
        "source_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources},
        "output_sha256": {p.name: sha(p.read_bytes()) for p in sorted(output.iterdir())},
    }
    (output / "evidence_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(dates)} sessions, {fills} fills, {len(cases)} diagnostic cases. Mean screen: {positive_mean_status(bounds)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/phase4-review")
    run(parser.parse_args().output)
