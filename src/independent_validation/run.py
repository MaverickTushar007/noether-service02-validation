"""Run Phase 3 against the frozen development submission."""
import argparse
import csv
import hashlib
import io
import json
import math
import platform
import sys
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from statistics import mean, stdev

import exchange_calendars
import yaml

from .comparison import CASH, METRIC, PRICE, SHARES, compare
from .reproduction import FEE, STARTING_CASH, SESSIONS_PER_YEAR, metrics, read_session, reproduce

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = "20261126T193506990307Z"
PHASE1 = f"evidence/{SNAPSHOT}/manifest.json"
CLIENT = "evidence/phase2-development"
START, END = "2011-01-01", "2018-12-31"


def sha(content):
    return hashlib.sha256(content).hexdigest()


def csv_rows(content):
    return csv.DictReader(io.StringIO(content.decode("utf-8")))


def verify_inputs():
    first = json.loads((ROOT / PHASE1).read_bytes())
    client = json.loads((ROOT / CLIENT / "run.json").read_bytes())
    if (first["snapshot"], first["status"], first["symbol"], first["price_currency"]) != (
        SNAPSHOT, "complete", "SPY", "USD"
    ) or first["request"]["auto_adjust"] is not False:
        raise ValueError("Unexpected Phase 1 snapshot or price basis")
    market_paths = [f"data/{basis}/{SNAPSHOT}/spy.csv" for basis in ("raw", "analysis")]
    expected = dict(client["source_sha256"])
    for path in market_paths:
        if first["files"][path] != client["frozen_input"][path]:
            raise ValueError(f"Phase 1 and Phase 2 hashes disagree: {path}")
        expected[path] = first["files"][path]
    for name in ("signals.csv", "trades.csv", "daily_equity.csv"):
        expected[f"{CLIENT}/{name}"] = client["output_sha256"][name]
    blobs = {path: (ROOT / path).read_bytes() for path in expected}
    for path, value in expected.items():
        if sha(blobs[path]) != value:
            raise ValueError(f"Unexpected frozen SHA-256: {path}")
    expected[f"{CLIENT}/run.json"] = sha((ROOT / CLIENT / "run.json").read_bytes())
    return expected, blobs, market_paths[1], client


def client_derived_metrics(rows):
    """Second formula implementation on saved client equity, with binary floats."""
    values = [float(STARTING_CASH), *(float(row["equity"]) for row in rows)]
    returns = [right / left - 1 for left, right in zip(values, values[1:])]
    growth = values[-1] / values[0]
    risk = stdev(returns)
    peak = values[0]
    drawdowns = []
    for value in values[1:]:
        peak = max(peak, value)
        drawdowns.append((peak - value) / peak)
    return {
        "total_return": growth - 1,
        "annualized_return": math.expm1(math.log(growth) * SESSIONS_PER_YEAR / len(returns)),
        "annualized_volatility": risk * math.sqrt(SESSIONS_PER_YEAR),
        "annualized_sharpe": mean(returns) / risk * math.sqrt(SESSIONS_PER_YEAR) if risk else None,
        "max_drawdown": max(drawdowns),
    }


def save_csv(path, rows):
    with path.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output):
    input_hashes, blobs, analysis_path, submitted = verify_inputs()
    research = yaml.safe_load(blobs["config/research_spec.yaml"])
    if research["asset"] != "SPY" or research["development"] != {"start": START, "end": END}:
        raise ValueError("Unexpected research scope")
    if research["sma"] != {"fast": 21, "slow": 50}:
        raise ValueError("Unexpected SMA parameter")
    parameters = {"symbol": "SPY", "development_start": START, "development_end": END,
                  "sma": research["sma"], "starting_cash": int(STARTING_CASH), "currency": "USD",
                  "cost_rate": float(FEE), "idle_cash_interest_rate": 0}
    parameter_match = submitted["parameters"] == parameters

    bars = []
    for row in csv_rows(blobs[analysis_path]):
        if row["trading_date"] > END:
            break
        if row["trading_date"] >= START:
            bars.append(read_session(row))
    calendar = exchange_calendars.get_calendar("XNYS", start=START, end=END)
    dates = calendar.sessions.strftime("%Y-%m-%d").tolist()
    signals, trades, ledger = reproduce(bars, dates, **research["sma"])
    reference_signals = list(csv_rows(blobs[f"{CLIENT}/signals.csv"]))
    reference_trades = list(csv_rows(blobs[f"{CLIENT}/trades.csv"]))
    reference_ledger = list(csv_rows(blobs[f"{CLIENT}/daily_equity.csv"]))

    # Derive client crossover labels only from the saved client target column.
    prior = "False"
    for row in reference_signals:
        target = row["target_long"]
        row["crossover"] = ("ENTER" if target == "True" else "EXIT") if target != prior else ""
        prior = target

    reviewer_metrics = metrics([row["equity"] for row in ledger])
    reference_metrics = client_derived_metrics(reference_ledger)
    comparisons = (
        compare("signals", reference_signals, signals,
                dict(trading_date=None, close=PRICE, sma_fast=PRICE, sma_slow=PRICE,
                     ready=None, target_long=None, crossover=None), "trading_date")
        + compare("fills", reference_trades, trades,
                  dict(signal_date=None, trade_date=None, side=None, price=PRICE, shares_delta=SHARES,
                       notional=CASH, cost=CASH, cash_before_fill=CASH, net_trade_cash=CASH,
                       cash_after_fill=CASH), "trade_date")
        + compare("daily", reference_ledger, ledger,
                  dict(trading_date=None, open=PRICE, close=PRICE, prior_cash=CASH,
                       prior_shares=SHARES, dividend_cash=CASH, capital_gain_cash=CASH,
                       net_trade_cash=CASH, trade_cost=CASH, shares_delta=SHARES, cash=CASH,
                       shares=SHARES, position_value=CASH, equity=CASH, overnight_pnl=CASH,
                       intraday_pnl=CASH, cash_residual=CASH, equity_bridge_residual=CASH),
                  "trading_date")
        + compare("derived_metrics", [reference_metrics], [reviewer_metrics],
                  dict.fromkeys(reviewer_metrics, METRIC), "metric")
    )

    final = ledger[-1]
    accounting = {
        "sessions": len(ledger), "first_session": dates[0], "last_session": dates[-1],
        "first_ready_signal": next(row["trading_date"] for row in signals if row["ready"]),
        "fills": len(trades), "ending_cash": final["cash"], "ending_shares": final["shares"],
        "ending_position_value": final["position_value"], "ending_equity": final["equity"],
        "unfilled_final_target_change": signals[-1]["target_long"] != bool(final["shares"]),
        "dividend_cash": sum(row["dividend_cash"] for row in ledger),
        "capital_gain_cash": sum(row["capital_gain_cash"] for row in ledger),
        "development_capital_gain_events": sum(bool(bar.capital_gain) for bar in bars),
        "net_trade_cash": sum(row["net_trade_cash"] for row in ledger),
        "trading_cost": sum(row["trade_cost"] for row in ledger),
        "max_abs_cash_residual": max(abs(row["cash_residual"]) for row in ledger),
        "max_abs_equity_bridge_residual": max(abs(row["equity_bridge_residual"]) for row in ledger),
    }
    counts = {"sessions", "fills", "development_capital_gain_events"}
    comparisons += compare(
        "submitted_accounting", [submitted["accounting"]], [accounting],
        {key: None if key in counts or not isinstance(value, Decimal) else
         SHARES if key == "ending_shares" else CASH for key, value in accounting.items()}, "aggregate",
    )
    max_shares_residual = max(abs(row["shares_residual"]) for row in ledger)
    balances_ok = all(row["cash"] >= 0 and row["shares"] >= 0 for row in ledger)
    reconciled = (balances_ok and accounting["max_abs_cash_residual"] <= CASH
                  and accounting["max_abs_equity_bridge_residual"] <= CASH
                  and max_shares_residual <= SHARES)

    def status(condition):
        return "PASS" if condition else "FAIL"

    findings = [
        ("F01", "PASS", "Frozen inputs and client output/source integrity", "SHA-256 matches the recorded references."),
        ("F02", status(parameter_match), "Client settings versus written scope", "Compared Phase 2 parameters with the reviewer transcription."),
        ("F03", "PASS", "Development session coverage", f"All {len(dates)} expected XNYS sessions matched."),
    ]
    for identifier, section, subject in [
        ("F04", "signals", "SMA, warmup, targets and crossover dates"),
        ("F05", "fills", "Signal-to-fill dates, opening executions and fees"),
        ("F06", "daily", "Daily shares, cash, distributions and equity"),
        ("F07", "submitted_accounting", "Submitted accounting totals"),
        ("F08", "derived_metrics", "Metrics recalculated from client equity"),
    ]:
        failed = [row["field"] for row in comparisons if row["section"] == section and row["status"] == "FAIL"]
        findings.append((identifier, status(not failed), subject,
                         f"Out-of-tolerance fields {', '.join(failed)}." if failed else "All fields matched within tolerance."))
    findings.extend([
        ("F09", "INCONCLUSIVE", "Client-submitted performance metric values", "Phase 2 submitted equity but no performance metrics. F08 compares recalculations."),
        ("F10", "INCONCLUSIVE", "Impact of ex-date cash availability", "Payment dates and settlement cash were not modeled or tested."),
        ("F11", status(reconciled), "Reviewer cash, shares and equity reconciliation", "Checked ending-of-session balances and daily accounting identities."),
    ])

    output.mkdir(parents=True, exist_ok=False)
    for name, rows in [
        ("reviewer_signals.csv", signals), ("reviewer_trades.csv", trades),
        ("reviewer_daily_equity.csv", ledger), ("comparison.csv", comparisons),
        ("metrics.csv", [{"metric": key, "reviewer": value, "derived_from_client_equity": reference_metrics[key]}
                         for key, value in reviewer_metrics.items()]),
        ("findings.csv", [dict(zip(("id", "status", "subject", "evidence"), item, strict=True)) for item in findings]),
    ]:
        save_csv(output / name, rows)

    entitled = sum(bool(row["dividend_cash"] or row["capital_gain_cash"]) for row in ledger)
    exit_entitled = sum(row["shares_delta"] < 0 and bool(row["dividend_cash"] or row["capital_gain_cash"])
                        for row in ledger)
    write_report(output, findings, comparisons, accounting, reviewer_metrics, reference_metrics,
                 entitled, exit_entitled, max_shares_residual)
    source_paths = [*sorted(Path(__file__).parent.glob("*.py")),
                    ROOT / "tests/test_independent_validation.py"]
    record = {
        "command": [sys.executable, *sys.orig_argv[1:]],
        "verification_command": [".venv/bin/python", "-m", "pytest", "-q", "-rs"],
        "verification_log": "evidence/phase3-run.txt",
        "python": platform.python_version(),
        "package_versions": {name: version(name) for name in ("exchange-calendars", "PyYAML", "pytest")},
        "parameters": {**parameters, "annual_sessions": SESSIONS_PER_YEAR, "risk_free_rate": 0},
        "input_sha256": input_hashes,
        "reviewer_source_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in source_paths},
        "output_sha256": {p.name: sha(p.read_bytes()) for p in sorted(output.iterdir())},
    }
    (output / "evidence_manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    failures = sum(item[1] == "FAIL" for item in findings)
    print(f"{len(ledger)} sessions, {len(trades)} fills, {len(comparisons)} field checks, {failures} failed findings. {output}")
    return 1 if failures else 0


def write_report(output, findings, comparisons, accounting, reviewer, client, entitled, exit_entitled, share_residual):
    lines = [
        "# Phase 3 mathematical reconciliation", "",
        "SPY development sessions only, 2011–2018. The reviewer parsed the frozen analysis CSV and independently "
        "summed complete 21- and 50-close windows using 40-digit decimal arithmetic. The sign of the SMA difference "
        "uses cross-multiplied window sums. The portfolio uses the prior session's target at each open. On buys, "
        "gross notional equals available cash divided by 1.0005. On sales, gross proceeds less 5 bp and any "
        "already available cash determine the new balance. A close mark equals cash plus shares times Close.", "",
        f"Reproduced {accounting['sessions']} sessions and {accounting['fills']} fills. Ending equity was "
        f"${accounting['ending_equity']:,.2f}. Maximum reviewer cash, share, and equity-bridge residuals "
        f"were {accounting['max_abs_cash_residual']:.3E}, {share_residual:.3E}, and "
        f"{accounting['max_abs_equity_bridge_residual']:.3E}, respectively.", "",
        "## Metric conventions", "",
        "Daily simple returns use closing equity over the preceding close, with $100,000 as the starting "
        "observation before the first session. Total return is final equity divided by $100,000 minus one. "
        "Geometric annualized return raises that same equity ratio to 252 divided by the number of daily "
        "returns, then subtracts one. Volatility is sample daily standard deviation (ddof=1) times the square "
        "root of 252. Sharpe uses the arithmetic mean of daily returns over sample daily standard deviation, "
        "times the square root of 252, with a zero risk-free rate. Idle cash earns zero interest. "
        "Drawdown is the largest positive decline from the running equity peak, including starting capital, "
        "divided by that peak. For example, equity of 100, 120, 90, 110 has a 25% maximum drawdown.", "",
        "Phase 2 submitted no performance metrics. The client column below was calculated from its saved equity "
        "using separate floating-point formulas and the same conventions.", "",
        "| Metric | Reviewer | Derived from client equity |", "| --- | ---: | ---: |",
    ]
    for key, value in reviewer.items():
        fmt = ".8f" if key == "annualized_sharpe" else ".8%"
        lines.append(f"| {key.replace('_', ' ')} | {value:{fmt}} | {client[key]:{fmt}} |")
    lines.extend([
        "", "## Comparison and findings", "",
        "Dates, labels, warmup blanks, and row order were compared exactly. Numerical comparisons used "
        "absolute tolerance plus 1e-12 times the absolute client value. Absolute tolerances were 1e-10 USD "
        "for market prices and SMA, 1e-9 shares for quantities, 1e-8 USD for cash and accounting, and "
        "1e-12 for decimal metrics. Relative error is absolute error divided by absolute client value. "
        "Zero client values are included in absolute error only. Near-zero client residuals can give large "
        "relative errors even when absolute differences are at roundoff scale.", "",
        "The [comparison CSV](comparison.csv) records maximum absolute and relative differences, counts, and "
        "the first mismatching key per field. The [findings register](findings.csv) covers actual submission "
        "results. Intentionally altered scenarios are exercised separately by the reviewer tests.", "",
        "| ID | Status | Finding |", "| --- | --- | --- |",
    ])
    lines.extend(f"| {identifier} | {status} | {subject}. {evidence} |"
                 for identifier, status, subject, evidence in findings)
    lines.extend([
        "", "| Field | Maximum absolute difference | Maximum relative difference |",
        "| --- | ---: | ---: |",
    ])
    highlighted = {("signals", "sma_fast"), ("signals", "sma_slow"), ("fills", "shares_delta"),
                   ("fills", "cost"), ("daily", "cash"), ("daily", "dividend_cash"),
                   ("daily", "equity")}
    for row in comparisons:
        if (row["section"], row["field"]) in highlighted:
            lines.append(
                f"| {row['section']} {row['field']} | {row['max_abs_difference']:.3E} | "
                f"{row['max_rel_difference']:.3E} |"
            )
    lines.extend([
        "", "## Distributions and settlement", "",
        f"The reviewer reproduced cash credits on {entitled} entitled sessions, including {exit_entitled} "
        "sessions with an opening sale. Prior-close holdings receive the distribution. Opening buyers receive "
        "none for that date. Credits use the provider event date as an ex-date proxy. Economic entitlement can "
        "arise at the ex date while spendable cash depends on the payment date and the broker's availability "
        "rules. The model makes these credits spendable immediately, potentially earlier than real cash "
        "availability if a later entry falls before payment. The model carries cash during a long holding "
        "period and sizes a subsequent entry with available cash. Payment-date data and a counterfactual "
        "ledger were outside this reconciliation, so no performance effect was established.",
    ])
    (output / "reconciliation.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/phase3-review")
    raise SystemExit(run(parser.parse_args().output))
