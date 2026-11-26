# Noether Meridian Service 02 Unit 1

Internal simulation for Roosevelt PETNGA. Approval is PENDING. Start with final-report.pdf and executive-summary.pdf. The Word files are editable. The validation matrix connects report claims to their sources and methods. The findings register has matching CSV and XLSX versions.

## Verify without evaluating the holdout again

Run from the repository root:

```sh
.venv/bin/python -B output/pdf/phase6/audit_evidence.py
.venv/bin/python -B final_deliverables/independent_audit.py "$PWD"
.venv/bin/python -B -m pytest -q -rs -p no:cacheprovider
```

The second command reads only frozen bars and existing portfolio rows. It recalculates recorded statistics and reconciliation identities. No acquisition or portfolio engine is invoked. The eight ledgers and recorded holdout claim remain in their original locations. Earlier manifest digests and final outputs are in evidence-manifest.json. The manifest does not hash itself.

## Rebuild the document exports

Use the included source Markdown and builders. Install ReportLab 5.1.2 in a separate virtual environment. The PDFs use Arial and Georgia from the macOS Supplemental font directory. For Word use the Codex runtime Python with python-docx 1.2.0. For spreadsheets and slides use the Codex runtime Node and @oai/artifact-tool 2.8.167, or the version recorded in the manifest. Copy the builders and inputs to a separate staging directory if rebuilding all outputs. Make its node_modules resolve to the runtime packages. Example commands from the repository root:

```sh
python final_deliverables/render_report.py "$PWD" final_deliverables/report.md /tmp/noether-validation.pdf
python final_deliverables/render_report.py "$PWD" final_deliverables/executive-summary.md /tmp/noether-summary.pdf
python final_deliverables/render_report.py "$PWD" final_deliverables/technical-appendix.md /tmp/noether-appendix.pdf
python final_deliverables/build_docx.py "$PWD" /path/to/staged/inputs-and-outputs
node final_deliverables/build_office.mjs "$PWD" /path/to/staged/inputs-and-outputs
```

The builder uses the verified figures under evidence/ and the staged Markdown and workbook-input.json. For office QA use LibreOffice or a compatible viewer, and check the matrix's three COUNTIF formulas against the classified register. Hashes authenticate current artifact bytes. They are not signed proof of external custody or review.
