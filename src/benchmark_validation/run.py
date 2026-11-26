"""Execute one prespecified holdout evaluation after a development-only preflight."""
import argparse
import csv
import hashlib
import io
import json
import platform
import sys
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal as D
from importlib.metadata import version
from pathlib import Path

import exchange_calendars

from src.independent_validation.reproduction import read_session

from .accounting import PORTFOLIOS, WEIGHT, cash_intervals, parse_rates, simulate
from .metrics import descriptive_windows, measures, paired, primary_judgment
from .reconcile import reconcile, require

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "reports/evaluation-protocol.md"
RAW_CASH = "data/cash/fred-dtb3-20261126T195302Z/dtb3.csv"
CASH_META = str(Path(RAW_CASH).with_name("provenance.json"))
PINS = {
    PROTOCOL: "4a71e5097c4ff5c71fc0984725146169faf3b9c828284cf2fba25865d8a4a077",
    RAW_CASH: "221b43d18886931d8d5207ef94c88ea0de19ab0f59b9327f84aa1d818f34b362",
    CASH_META: "19c44b1104148f6a495fdf4d13417d7166dfca2f4af16c51974dac97c971fca4",
}
PHASE4 = "evidence/phase4-review/evidence_manifest.json"
PHASE3 = "evidence/phase3-review/reviewer_daily_equity.csv"
FROZEN = "data/analysis/20261126T193506990307Z/spy.csv"
GATE = ROOT / "evidence/phase5-holdout-claim.json"
DEV = ("2011-01-03", "2018-12-31")
HOLD = ("2019-01-01", "2022-12-31")


def sha(content):
    return hashlib.sha256(content).hexdigest()


def rows(content):
    return csv.DictReader(io.StringIO(content.decode("utf8")))


def verify():
    manifest_data = (ROOT / PHASE4).read_bytes()
    manifest = json.loads(manifest_data)
    expected = {PHASE4: sha(manifest_data), **PINS}
    for namespace in ("input_sha256", "source_sha256", "output_sha256"):
        for name, checksum in manifest[namespace].items():
            relative = str(Path(PHASE4).parent / name) if namespace == "output_sha256" else name
            expected[relative] = checksum
    contents = {name: (ROOT / name).read_bytes() for name in expected}
    for name, checksum in expected.items():
        require(sha(contents[name]) == checksum, f"Unexpected SHA-256 for {name}")
    weight = next(rows(contents["evidence/phase4-review/ledger_statistics.csv"]))
    require(D(weight["mean_close_invested_weight"]) == WEIGHT, "Frozen weight changed")
    require(json.loads(contents[CASH_META])["sha256"] == PINS[RAW_CASH], "Cash snapshot metadata mismatch")
    return expected, contents


def market_partition(source, start, end):
    """Convert fields only for the requested window, using prior closes separately."""
    for row in source:
        stamp = row["trading_date"]
        if stamp > end:
            break
        if stamp >= start:
            yield read_session(row)


def evaluate(bars, dates, rates, warmup=()):
    require([bar.date for bar in bars] == dates, "Missing or unmatched XNYS sessions")
    intervals = list(cash_intervals(dates, rates))
    ledgers = {book: simulate(book, bars, intervals, warmup if book == "sma" else ())
               for book in PORTFOLIOS}
    checks = [reconcile(book, ledger, bars, intervals, warmup if book == "sma" else ())
              for book, ledger in ledgers.items()]
    return ledgers, checks


def verify_development(ledger, old):
    names = {"cash": "cash", "shares": "shares", "equity": "equity", "cost": "trade_cost",
             "dividend_cash": "dividend_cash", "capital_gain_cash": "capital_gain_cash"}
    maximum = D(0)
    for fresh, frozen in zip(ledger, old, strict=True):
        require(fresh["date"] == frozen["trading_date"], "Development date mismatch")
        maximum = max(maximum, *(abs(fresh[k] - D(frozen[v])) for k, v in names.items()))
    require(maximum <= D("1e-8"), "Development SMA reference path differs")
    return maximum


def claim(output):
    with GATE.open("x") as file:
        json.dump({"protocol_sha256": PINS[PROTOCOL], "output_directory": str(output.resolve()),
                   "claimed_utc": datetime.now(timezone.utc).isoformat(),
                   "command": [sys.executable, *sys.orig_argv[1:]]}, file, indent=2)
        file.write("\n")


def write_csv(path, data):
    with path.open("x", newline="", encoding="utf8") as stream:
        writer = csv.DictWriter(stream, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)


def run(output, preflight_only):
    input_hashes, content = verify()
    market = content[FROZEN]
    calendar = exchange_calendars.get_calendar("XNYS", start="2011-01-01", end=HOLD[1])
    dates = calendar.sessions.strftime("%Y-%m-%d").tolist()
    development_dates = [d for d in dates if DEV[0] <= d <= DEV[1]]
    holdout_dates = [d for d in dates if HOLD[0] <= d <= HOLD[1]]
    rates = parse_rates(rows(content[RAW_CASH]))
    # Check cash calendar coverage before the one-shot gate. No holdout equity is evaluated here.
    list(cash_intervals(holdout_dates, rates))
    development = list(market_partition(rows(market), *DEV))
    dev_books, dev_checks = evaluate(development, development_dates, rates)
    same = verify_development(dev_books["sma"], rows(content[PHASE3]))
    print(f"Development preflight: {len(development_dates)} sessions. Maximum frozen SMA path difference {same:.3E}.",
          flush=True)
    if preflight_only:
        return
    require(not output.exists(), "Output directory already exists")
    claim(output)
    warmup = deque(((bar.date, bar.closing) for bar in development), maxlen=50)
    holdout = list(market_partition(rows(market), *HOLD))
    hold_books, hold_checks = evaluate(holdout, holdout_dates, rates, list(warmup))
    books = {"development": dev_books, "holdout": hold_books}

    comparison, uncertainty, checks = [], [], []
    for period, items in books.items():
        comparison.extend({"window": period, **measures(book, ledger)} for book, ledger in items.items())
        uncertainty.extend({"window": period, **paired(book, items["sma"], items[book])}
                           for book in ("fixed_mix", "buy_hold", "cash"))
        checks.extend({"window": period, **row}
                      for row in (dev_checks if period == "development" else hold_checks))
    primary = next(row for row in uncertainty if row["window"] == "holdout" and row["benchmark"] == "fixed_mix")
    findings = [
        {"id": "P501", "status": "PASS", "criterion": "Frozen input and protocol integrity",
         "evidence": "Verified all carried-forward hashes and the independent DTB3 snapshot."},
        {"id": "P502", "status": "PASS", "criterion": "Matched sessions and one-shot boundary",
         "evidence": f"Claimed holdout once. All books match the {len(holdout_dates)} holdout calendar sessions."},
        {"id": "P503", "status": "PASS", "criterion": "Independent timing and accounting reconciliation",
         "evidence": f"All portfolio ledgers reconciled. Development SMA reference maximum difference {same:.3E}."},
        {"id": "P504", "status": primary_judgment(primary), "criterion": "Primary out-of-sample incremental performance",
         "evidence": "Both compounded return gap and the paired mean-difference interval must support the same direction."},
        {"id": "P505", "status": "INCONCLUSIVE", "criterion": "Realistic cash implementation",
         "evidence": "Verified historical rates support a synthetic proxy. Executable bill total returns and broker yields are unavailable."},
        {"id": "P506", "status": "INCONCLUSIVE", "criterion": "Causal attribution and generalization",
         "evidence": "One asset and one holdout. Exposure, timing, costs and idle cash economics differ."},
    ]
    output.mkdir(parents=True, exist_ok=False)
    for period, items in books.items():
        for book, ledger in items.items():
            write_csv(output / f"{period}_{book}.csv", ledger)
    windows = descriptive_windows(hold_books)
    for name, table in (("comparison", comparison), ("paired_uncertainty", uncertainty),
                        ("context_windows", windows), ("reviewer_reconciliation", checks), ("findings", findings)):
        write_csv(output / f"{name}.csv", table)

    from .report import render
    render(output, books, comparison, uncertainty, checks, findings, windows, same)
    source = [*sorted(Path(__file__).parent.glob("*.py")), ROOT / "tests/test_benchmark_validation.py"]
    manifest = {
        "command": [sys.executable, *sys.orig_argv[1:]], "test_command": [".venv/bin/python", "-m", "pytest", "-q", "-rs"],
        "preflight_command": [".venv/bin/python", "-m", "src.benchmark_validation.run", "--preflight-only"],
        "execution_log": "evidence/phase5-run.txt", "python": platform.python_version(),
        "packages": {name: version(name) for name in ("numpy", "pandas", "matplotlib", "exchange-calendars", "pytest")},
        "parameters": {"development": DEV, "holdout": HOLD, "sma": [21, 50], "fee_bps": 5, "cash_series": "DTB3",
                       "fixed_weight": str(WEIGHT), "blocks": 20, "replications": 20_000,
                       "seed": 20261127, "annual_sessions": 252},
        "holdout_claim_sha256": sha(GATE.read_bytes()), "input_sha256": input_hashes,
        "source_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in source},
        "output_sha256": {p.name: sha(p.read_bytes()) for p in sorted(output.iterdir())},
    }
    (output / "evidence_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Holdout evaluated once: {len(holdout_dates)} sessions. Primary judgment: {primary_judgment(primary)}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/phase5-review")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    run(args.output, args.preflight_only)
