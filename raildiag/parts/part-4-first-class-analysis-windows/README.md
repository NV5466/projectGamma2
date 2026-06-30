# Part 4 - First-Class Analysis Windows

Commit: `f11048b Add first-class analysis windows`

Tag: `part-4`

Purpose: make event windows durable report objects instead of prose-only references.

Included work:

- Added schema `electrostat.report.v2`
- Added `windows` section to JSON reports
- Added baseline, command-active, source, reference, victim chatter, victim dropout, and post-event windows
- Added baseline-vs-event PSD summaries
- Added spectral window-bank checks
- Improved digital-like rail/state warnings
- Corrected dropout-to-fault timing language
- Added conservative cross-channel relationship statements

Current verification output:

```text
C:\Users\dmaca\Documents\JTAStuff\projectGamma\FakeScopeData\raildiag_reports\rail_event_windows_verify
```

Local artifacts:

```text
artifacts/report.txt
artifacts/report.estat.json
artifacts/report.md
artifacts/display_render.txt
artifacts/plots/
```
