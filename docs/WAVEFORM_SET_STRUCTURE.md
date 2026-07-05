# Gamma Waveform Set Structure

Gamma can analyze a single `.npz` capture file or a folder of `.npz` captures directly. For repeatable work inside the app, use a waveform set.

Default local library:

```text
waveform_sets/
  <set_id>/
    manifest.json
    notes.md
    captures/
      <capture_id>.npz
```

`manifest.json` records:

- set id
- source file path for each imported capture
- stored capture path
- capture id
- byte size
- import timestamp
- supported file formats

The app-created `waveform_sets/<set_id>/` folders are ignored by git so local captures do not get committed by accident.

Current supported capture format:

```text
.npz
```

Required `.npz` fields are the existing Gamma Core capture schema:

- `sample_rate_hz`
- `primary`
- at least one reference waveform, either `secondary`, `reference_<label>`, or `references_json` mapping

Optional fields:

- `time_s`
- `capture_id`
- `truth_label`
- `primary_label`
- `metadata_json`

Recommended workflow:

1. Open the GUI with `python -m gamma_app.runner gui`.
2. Use the `Waveform Sets` tab.
3. Name a set, for example `bench_relay_run_001`.
4. Select one or more `.npz` files, or a folder containing `.npz` files.
5. Click `Import Into Set`.
6. Click `Use Set In Analyze Tab`.
7. Run analysis from the `Analyze Capture` tab.

