# Part 3 - Structured Display Reports

Commit: `349a7d2 Add structured text report display`

Tag: `part-3`

Purpose: make report display cleaner and easier to feed into other tools.

Included work:

- Added `report.txt` fixed-width report
- Added `report.estat.json` structured report export
- Kept `report.md` as legacy output
- Added `python -m raildiag.display` for rendering structured reports
- Reduced fragile Markdown table formatting

Primary outputs:

```text
report.txt
report.estat.json
report.md
plots/
```

Local artifacts:

```text
artifacts/report.txt
artifacts/report.estat.json
artifacts/report.md
artifacts/plots/
```
