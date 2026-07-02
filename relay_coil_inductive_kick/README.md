# relay_coil_inductive_kick

Standalone Class A seed for relay coil inductive kickback.

This package intentionally does **not** combine contact bounce, missed short pulse, or noise signatures.
Those remain separate scripts/seeds and are invoked only through the boundary harness.

## Primary model

If CH1 is coil current:

```math
v_{victim}(t) \approx k \frac{di_{coil}}{dt}
```

If CH1 is coil voltage:

```math
v_{victim}(t) \approx k v_{coil}(t)
```

The fitted constant \(k\) absorbs unknown inductance/coupling. We do not need to know \(L\) or \(M\) beforehand.

## Run synthetic positives

```bash
python experiments/validate_seed_boundaries.py --positive-n 250 --out-dir boundary_results
```

## Wire existing negative seeds

Use existing scripts by exporting their generated cases to a simple NPZ:

```text
time:   [n_samples]
source: [n_cases, n_samples]
victim: [n_cases, n_samples]
source_mode: optional scalar string, "current" or "voltage"
```

Then run:

```bash
python experiments/validate_seed_boundaries.py \
  --positive-n 250 \
  --negative-adapter high_speed_input_bounce=/path/to/bounce_cases.npz \
  --negative-adapter missed_short_pulse=/path/to/missed_cases.npz \
  --negative-adapter noise=/path/to/noise_cases.npz
```

You can also pass a Python adapter as `module:function` if it returns dictionaries with:

```python
{
    "time_s": np.ndarray,
    "source": np.ndarray,
    "victim": np.ndarray,
    "source_mode": "current" | "voltage",
    "metadata": {...},  # optional
}
```

## Outputs

- `summary.json`
- `decisions.jsonl`
- `features.csv`

## Class boundary

Ringdown alone does not classify inductive kickback. Ringdown is secondary.
The classifier requires source-locked unknown-gain derivative/voltage coupling.
