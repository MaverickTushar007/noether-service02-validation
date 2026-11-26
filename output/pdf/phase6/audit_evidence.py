"""Read-only check of frozen evidence and numbers cited in the Phase 6 report."""
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
entries = {}
references = 0


def verify(path, expected):
    global references
    path = str(path)
    actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Digest mismatch: {path}")
    entries[path] = actual
    references += 1


def read_json(path):
    return json.loads((root / path).read_text())


def csvrows(path):
    with (root / path).open(newline="") as stream:
        return list(csv.DictReader(stream))


for name, sections in {
    "evidence/20261126T193436807402Z/manifest.json": ("files",),
    "evidence/20261126T193506990307Z/manifest.json": ("files",),
    "evidence/phase2-development/run.json": ("frozen_input", "source_sha256", "output_sha256"),
    "evidence/phase3-review/evidence_manifest.json": ("input_sha256", "reviewer_source_sha256", "output_sha256"),
    "evidence/phase4-review/evidence_manifest.json": ("input_sha256", "source_sha256", "output_sha256"),
    "evidence/phase5-review/evidence_manifest.json": ("input_sha256", "source_sha256", "output_sha256"),
}.items():
    manifest = read_json(name)
    for key in sections:
        for path, digest in manifest[key].items():
            verify(Path(name).parent / path if key == "output_sha256" else path, digest)
    if "holdout_claim_sha256" in manifest:
        verify("evidence/phase5-holdout-claim.json", manifest["holdout_claim_sha256"])
    entries[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()

for number in range(1, 6):
    name = f"evidence/phase{number}-run.txt"
    entries[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()

market = read_json("evidence/20261126T193506990307Z/audit.json")
assert (market["first_date"], market["last_date"], market["observation_count"]) == ("2011-01-03", "2022-12-30", 3020)
assert (len(market["dividend_events"]), len(market["large_close_returns"]), len(market["split_events"])) == (48, 4, 0)
for check in ("missing_expected_sessions", "unexpected_sessions", "duplicate_dates", "ohlc_inconsistency_dates"):
    assert not market[check]
p3 = "evidence/phase3-review/"
checks = csvrows(p3 + "comparison.csv")
assert len(checks) == 57 and all(row["status"] == "PASS" for row in checks)
equity_check = next(r for r in checks if r["section"] == "daily" and r["field"] == "equity")
assert f"{float(equity_check['max_abs_difference']):.2e}" == "2.90e-10"

p4 = "evidence/phase4-review/"
bootstrap = csvrows(p4 + "bootstrap.csv")
assert [(row["block_sessions"], f"{float(row['annualized_lower']):.2%}", f"{float(row['annualized_upper']):.2%}")
        for row in bootstrap] == [("20", "-0.82%", "11.88%"), ("10", "-0.99%", "12.23%"), ("40", "-0.93%", "12.07%")]
assert all(row["zero_excluded"] == "False" for row in bootstrap)
assert [f"{float(row['cagr']):.2%}" for row in csvrows(p4 + "parameter_sensitivity.csv")] == ["4.98%", "5.34%", "4.24%"]
assert [f"{float(row['cagr']):.2%}" for row in csvrows(p4 + "cost_sensitivity.csv")] == ["5.34%", "5.05%", "4.47%"]

p5 = "evidence/phase5-review/"
comparison = csvrows(p5 + "comparison.csv")
same_dates = {}
for row in comparison:
    window, book = row["window"], row["portfolio"]
    ledger = csvrows(f"{p5}{window}_{book}.csv")
    dates = [r["date"] for r in ledger]
    assert dates == same_dates.setdefault(window, dates)
    assert (len(dates), dates[0], dates[-1]) == (int(row["sessions"]), row["start"], row["end"])
    first, last = ledger[0], ledger[-1]
    assert float(first["prior_cash"]) == 100_000 and float(first["prior_shares"]) == 0
    assert math.isclose(float(last["equity"]), float(row["ending_equity"]), abs_tol=1e-8)
    for source, total in [("cost", "modeled_cost_usd"), ("interest", "cash_interest_usd"),
                          ("dividend_cash", "dividends_usd")]:
        assert math.isclose(sum(float(r[source]) for r in ledger), float(row[total]), abs_tol=1e-8)
    if book == "sma":
        assert all(float(r["interest"]) == 0 for r in ledger)
    print(window, book, *(f"{float(row[k]):.2%}" for k in ("cumulative_return", "cagr", "annualized_volatility", "maximum_drawdown")))
assert len(same_dates["development"]) + len(same_dates["holdout"]) == 3020
sma_start = csvrows(p5 + "holdout_sma.csv")[0]
assert (sma_start["signal_date"], sma_start["open_target_long"], sma_start["trade_reason"]) == ("2018-12-31", "False", "")
spreads = csvrows(p5 + "paired_uncertainty.csv")
primary = next(r for r in spreads if r["window"] == "holdout" and r["benchmark"] == "fixed_mix")
assert [f"{float(primary[k])*100:.2f}" for k in ("compounded_total_return_gap", "annualized_arithmetic_gap",
       "annualized_ci_lower", "annualized_ci_upper")] == ["-21.92", "-4.25", "-13.31", "7.01"]
for phase in (3, 4, 5):
    path = f"evidence/phase{phase}-review/findings.csv"
    print(f"Historical Phase {phase} classifications", dict(Counter(row["status"] for row in csvrows(path))))
print(f"Verified {references} reference hashes. Inventoried {len(entries)} distinct paths including manifests and run logs.")
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps({"verified_hash_references": references, "input_sha256": entries}, indent=2) + "\n")
