# Phase 6 evidence verification and PDF reproduction

Run from the repository root. The verifier reads frozen manifests, reports and ledgers. It checks SHA-256, displayed values, date alignment and interest totals from saved rows. It creates no market data and calls no strategy or holdout runner.

```sh
.venv/bin/python -B output/pdf/phase6/audit_evidence.py
.venv/bin/python -B -m pytest -q -rs -p no:cacheprovider
```

The recorded verification is in verification.log. The exact suite output is in test-run.txt. The evidence manifest maps every inventoried prior artifact and Phase 6 deliverable to its SHA-256 digest. The manifest excludes its own digest. Phase 5's original execution command is historical evidence. Preserve the holdout claim and ledgers. Do not use the Phase 5 run command to reproduce this package.

To reproduce the PDFs under macOS, use the included renderer with the editable Markdown, original figures and an isolated ReportLab environment. The shipped PDFs use Georgia and Arial from the macOS Supplemental font directory. The locked project environment can remain unchanged.

```sh
python3.13 -m venv /tmp/noether-report-render
/tmp/noether-report-render/bin/python -m pip install reportlab==5.1.2 pillow==13.0.0 charset-normalizer==3.5.3
/tmp/noether-report-render/bin/python output/pdf/phase6/render_report.py "$PWD" output/pdf/phase6/report.md /tmp/noether-report.pdf
/tmp/noether-report-render/bin/python output/pdf/phase6/render_report.py "$PWD" output/pdf/phase6/executive-summary.md /tmp/noether-executive.pdf
pdftoppm -png -r 100 /tmp/noether-report.pdf /tmp/noether-report
pdftoppm -png -r 100 /tmp/noether-executive.pdf /tmp/noether-executive
```
