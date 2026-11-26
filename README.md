# Noether Meridian Service 02 · Unit 1

Internal Noether Meridian Service 02, Unit 1 methodology demonstration. The hypothetical SPY strategy uses daily SMA 21/50 with next-open fills and historical data spanning 2011–2022. There was no real client engagement, live model or certification. Human approval remains pending.

**Mathematical reproduction passed. Predictive reliability and incremental economic value were inconclusive.** Development SMA CAGR was 5.34%. In holdout, the SMA earned 23.14% cumulatively versus 45.06% for the fixed mix. The paired annualized arithmetic gap had a 95% interval spanning zero. The frozen model earns zero on idle cash while benchmark cash earns a synthetic Treasury accrual. Ex-date cash availability and modeled fills also limit interpretation.

| Stage | Evidence |
| --- | --- |
| 1 · Acquisition and data audit | [Snapshot and quality audit](reports/20261126T193506990307Z.md) |
| 2 · Hypothetical submission | [Frozen strategy rules](reports/strategy-spec.md) |
| 3 · Independent calculation | [Reconciliation](evidence/phase3-review/reconciliation.md) |
| 4 · Statistical and bias review | [Protocol](reports/statistical-protocol.md) and [results](evidence/phase4-review/statistical-review.md) |
| 5 · One-shot benchmark holdout | [Protocol](reports/evaluation-protocol.md) and [results](evidence/phase5-review/evaluation.md) |
| 6 · Consolidated internal review | [Final report](final_deliverables/final-report.pdf) and [traceability](final_deliverables/claim-traceability.csv) |

## Setup and commands

Use CPython 3.13.3 on macOS arm64 for the pinned environment. From the project root:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip check
.venv/bin/python -B -m pytest -q -rs -p no:cacheprovider -k 'not test_manifest_checksums and not test_saved_dataset'
```

The filter is for a private GitHub checkout without the local snapshots. For the complete test and hash audit, restore the original authorized local evidence at the paths recorded in the manifest and remove the filter. See [reproducibility instructions](final_deliverables/README.md). The historical one-shot holdout command is part of the local audit record. Do not use it to reconstruct the publication checkout.

## Private publication and data rights

The [publication inventory](PUBLICATION_FILES.txt) lists this release. Summary findings, protocols, reports and research source are included. Raw vendor data, row-level market and portfolio files, draft packages, local environment files, verbose local logs and machine-specific run manifests are preserved in the local archive. Some included evidence documents refer to those locally held files by design. Private repository visibility does not confer data redistribution rights or authorization to share internal materials.

When permitted by your provider terms, run `.venv/bin/python src/acquire.py` to request a new independently dated SPY snapshot. Do not substitute it for the historical frozen bytes. Yahoo may revise values, and a fresh retrieval will have separate provenance. Use the [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) and [yfinance documentation](https://github.com/ranaroussi/yfinance) to review permitted use.

The separate Treasury source is Board of Governors H.15 DTB3 via FRED, Federal Reserve Bank of St. Louis. The [local provenance record](data/cash/fred-dtb3-20261126T195302Z/provenance.json) gives the dated CSV query, checksum and transformation reference. Fetch that query independently if permitted. A current response may differ from the frozen vintage. See the [FRED DTB3 series](https://fred.stlouisfed.org/series/DTB3) and [FRED terms](https://fred.stlouisfed.org/legal/terms/).

## Project layout

| Path | Purpose |
| --- | --- |
| `src/acquire.py` | Acquisition CLI, date normalization, audit and evidence writer |
| `config/research_spec.yaml` | Future research plan and predeclared date ranges |
| `tests/test_acquire.py` | Synthetic regression fixtures and checks against saved snapshots |
| `requirements-lock.txt` | Pinned environment |
| `data/raw/<snapshot>/spy.csv` | Unedited CSV serialization of the DataFrame returned by yfinance |
| `data/analysis/<snapshot>/spy.csv` | Copy with exchange-local trading date labels |
| `evidence/<snapshot>/manifest.json` | Request, version, UTC retrieval time, currency, status and SHA-256 file hashes |
| `evidence/phase1-run.txt` | Executed commands, output and exit codes |
| `evidence/<snapshot>/audit.json` | Machine-readable quality findings when the response can be audited |
| `reports/<snapshot>.md` | Human-readable data audit or snapshot failure details |
| `.gitignore` | Excludes local environments, caches, data CSVs and common environment files |

## Data policy

The CLI requests SPY from Yahoo Finance through yfinance using daily bars from 2011-01-01 inclusive to 2023-01-01 exclusive. It disables automatic OHLC adjustment and repair, requests corporate actions, and preserves rows exposed by yfinance with `keepna=True`. The raw CSV captures the library-returned table and yfinance may process the upstream response before returning that table. The normalization step first converts timestamps to America/New_York and then takes the local date. For example, 04:00 UTC on a winter morning is 23:00 in New York the previous evening.

The XNYS calendar serves as a US equities session proxy for NYSE Arca-listed SPY. A scheduled session absent from the data is a gap, while a weekend, holiday or scheduled exchange closure requires no bar. Failed or incomplete retrievals exit with a nonzero code and leave evidence without publishing an analysis CSV. Auditing applies no filling, interpolation, row deletion or price repair.

OHLC consistency uses provider Open, High, Low and Close on their common basis. Yahoo's historical OHLC may already reflect split normalization. Adjusted Close is the vendor's additional corporate-action-adjusted series and is unsuitable as an executable transaction price. For example, if the prior Close is $100 and the next session carries a $1 dividend, the adjustment factor Adj Close / Close should increase by roughly 1 / 0.99 across that boundary, absent a split. The check screens for discrepancies and does not recalculate vendor prices. Review the session-calendar proxy, 8% absolute daily move threshold, and 5 basis point adjustment-factor tolerance before later research. A review flag calls for investigation. Confirming a vendor error requires independent evidence.

Yahoo Finance data can change and carry no exchange certification. A checksum fingerprints bytes. A changed digit in a CSV yields a different hash even if the filename stays the same.

References [yfinance history implementation](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py) · [Exchange Calendars](https://github.com/gerrymanoim/exchange_calendars)

## Phase 2 development demonstration

See [the client strategy specification](reports/strategy-spec.md) for signal, execution, and accounting rules. Phase 2 uses the successful local Phase 1 snapshot and verifies both input hashes before parsing development bars. The Phase 1 data audit still covers the entire frozen dataset. The strategy runner ends on 2018-12-31.

```sh
.venv/bin/python -m src.run_development
.venv/bin/python -m pytest -q -rs
```

The first command writes `evidence/phase2-development/`. To repeat the run, use `--output evidence/phase2-development-repeat` with a fresh directory name.

| Path | Purpose |
| --- | --- |
| `src/signals.py` | Completed-close SMA levels and binary targets |
| `src/portfolio.py` | Next-open orders, distributions, cash and share accounting, and closing equity bridge |
| `src/run_development.py` | Verifies frozen data and produces development-only evidence |
| `tests/test_strategy.py` | Hand-calculated strategy and accounting checks plus input-integrity and date-boundary tests |
| `evidence/phase2-development/signals.csv` | Daily close, SMA values, readiness, and closing target |
| `evidence/phase2-development/trades.csv` | Signal date, fill date, signed shares, price, notional, fee, and cash |
| `evidence/phase2-development/daily_equity.csv` | Daily cash, positions, equity, distributions, and reconciliation residuals |
| `evidence/phase2-development/run.json` | Inputs and output hashes, source file hashes, versions, parameters, and accounting summary |
| `evidence/phase2-run.txt` | Executed demonstration and test commands with their outcomes |

## Phase 3 independent mathematical reproduction

Run the reviewer from the project root with the existing frozen artifacts.

```sh
.venv/bin/python -m src.independent_validation.run
.venv/bin/python -m pytest -q -rs
```

The reviewer writes a new `evidence/phase3-review/` directory. Use `--output` with a fresh directory for repeat runs. The independent arithmetic lives in `src/independent_validation/reproduction.py`, and `comparison.py` applies the review tolerances to the saved client submission. `run.py` verifies inputs and writes the reviewer ledgers, comparison, metric table, findings, reconciliation, and evidence manifest. The hand-calculated challenges in `tests/test_independent_validation.py` are separate from the SPY findings.
