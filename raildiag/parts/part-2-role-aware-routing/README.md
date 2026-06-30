# Part 2 - Role-Aware Routing

Commit: `b8c4f40 Add role-aware analysis routing`

Tag: `part-2`

Purpose: stop treating every channel as a generic waveform and route analysis from user-supplied metadata.

Included work:

- Extended channel metadata fields
- Added channel role table
- Added command/source/reference/victim/output routing
- Added edge timing, chatter, dropout, source activity, reference movement, and output assertion detection
- Added role-aware interpretation
- Added event timeline
- Added rail-event metadata example

Primary example:

```text
examples/rail_event_metadata.yaml
```

Local artifacts:

```text
artifacts/report.md
artifacts/plots/
```
