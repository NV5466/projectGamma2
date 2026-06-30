import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.ndimage import median_filter
from pathlib import Path
from caas_jupyter_tools import display_dataframe_to_user

# ============================================================
# WAVECOMPARE 2:
# 100 distinct hidden responses
# 100 noisy/shifted/scaled measurements per response
# Build one collective average per response
# Fit piecewise exponentials ONLY to the collective average
# ============================================================

SEED = 230626
FAMILIES = 100
CAPTURES_PER_FAMILY = 100
REGIONS = 6
N = 240
DT = 0.004
T = np.arange(N) * DT

MAX_SHIFT = 9
FILTER_KERNEL = 5
MIN_TRUE_REGION = 25

POLE_GRID = -np.geomspace(0.8, 55.0, 52)
GRID_STEP = 3
MIN_FIT_REGION = 20
MAX_FIT_REGION = 58

rng = np.random.default_rng(SEED)
out = Path("/mnt/data")
out.mkdir(exist_ok=True)

def robust_normalize(y):
    c = np.median(y)
    s = np.percentile(y, 95) - np.percentile(y, 5)
    return (y - c) / max(s, 1e-12)

def random_lengths(total, parts, minimum, rng):
    extra = total - parts * minimum
    weights = rng.dirichlet(np.ones(parts))
    add = np.floor(weights * extra).astype(int)
    delta = extra - int(add.sum())
    if delta > 0:
        add[np.argsort(weights)[-delta:]] += 1
    return minimum + add

def generate_hidden_response(rng):
    lengths = random_lengths(N, REGIONS, MIN_TRUE_REGION, rng)
    boundaries = np.concatenate([[0], np.cumsum(lengths)])

    poles = -np.exp(rng.uniform(np.log(2.0), np.log(34.0), REGIONS))
    y0 = rng.uniform(-0.8, 0.8)

    targets = []
    current_target = y0
    for _ in range(REGIONS):
        jump = rng.uniform(0.55, 2.6) * rng.choice([-1.0, 1.0])
        next_target = np.clip(current_target + jump, -4.0, 4.0)
        if abs(next_target - current_target) < 0.4:
            next_target = np.clip(current_target + 0.75*np.sign(jump), -4.0, 4.0)
        targets.append(next_target)
        current_target = next_target

    y = np.empty(N)
    current = y0
    for r in range(REGIONS):
        i, j = boundaries[r], boundaries[r+1]
        local_t = T[i:j] - T[i]
        C = targets[r]
        A = current - C
        y[i:j] = C + A*np.exp(poles[r]*local_t)
        current = y[j-1]

    return {
        "truth": y,
        "truth_norm": robust_normalize(y),
        "boundaries": boundaries,
        "poles": poles,
        "targets": np.array(targets),
    }

def shift_interp(y, shift_samples):
    shifted_t = T - shift_samples*DT
    return np.interp(shifted_t, T, y, left=y[0], right=y[-1])

def make_capture(truth, rng, force_zero_shift=False):
    shift = 0 if force_zero_shift else int(rng.integers(-MAX_SHIFT, MAX_SHIFT+1))
    scale = rng.uniform(0.65, 1.45)
    offset = rng.uniform(-0.8, 0.8)

    y = offset + scale*shift_interp(truth, shift)

    span = np.percentile(y, 95) - np.percentile(y, 5)
    sigma = rng.uniform(0.035, 0.13) * max(span, 0.5)
    y = y + rng.normal(0.0, sigma, N)

    # Impulsive corruption
    spike_mask = rng.random(N) < rng.uniform(0.006, 0.025)
    if spike_mask.any():
        y[spike_mask] += rng.normal(
            0.0,
            rng.uniform(0.35, 1.0)*max(span, 0.5),
            spike_mask.sum(),
        )

    return {
        "signal": y,
        "shift": shift,
        "scale": scale,
        "offset": offset,
        "sigma": sigma,
    }

def shift_nan(y, lag):
    out = np.full_like(y, np.nan, dtype=float)
    if lag > 0:
        out[:-lag] = y[lag:]
    elif lag < 0:
        q = -lag
        out[q:] = y[:-q]
    else:
        out[:] = y
    return out

def best_lag(template, candidate, max_lag=MAX_SHIFT+3):
    best = None
    for lag in range(-max_lag, max_lag+1):
        shifted = shift_nan(candidate, lag)
        mask = np.isfinite(shifted) & np.isfinite(template)
        if mask.sum() < N - max_lag:
            continue
        a = template[mask]
        b = shifted[mask]
        a = a - a.mean()
        b = b - b.mean()
        denom = np.sqrt(np.dot(a, a)*np.dot(b, b)) + 1e-12
        score = np.dot(a, b)/denom
        if best is None or score > best[0]:
            best = (score, lag)
    return best[1]

def affine_map_to_template(template, candidate):
    mask = np.isfinite(template) & np.isfinite(candidate)
    x = candidate[mask]
    y = template[mask]
    X = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    mapped = beta[0] + beta[1]*candidate
    return mapped

def build_collective_average(captures, iterations=4):
    # Anchor phase to capture 0, which is generated with zero planted shift.
    normalized = np.array([
        robust_normalize(median_filter(c["signal"], size=FILTER_KERNEL))
        for c in captures
    ])

    template = normalized[0].copy()
    last_lags = np.zeros(len(captures), dtype=int)
    aligned_stack = None

    for _ in range(iterations):
        aligned = []
        lags = []
        for y in normalized:
            lag = best_lag(template, y)
            shifted = shift_nan(y, lag)
            mapped = affine_map_to_template(template, shifted)
            aligned.append(mapped)
            lags.append(lag)

        aligned_stack = np.vstack(aligned)

        # Ordinary average, with one guard against isolated impulse contamination:
        # clip each time sample to 4 MAD before averaging.
        center = np.nanmedian(aligned_stack, axis=0)
        mad = np.nanmedian(np.abs(aligned_stack - center), axis=0) + 1e-12
        clipped = np.clip(
            aligned_stack,
            center - 4.0*1.4826*mad,
            center + 4.0*1.4826*mad,
        )
        template = np.nanmean(clipped, axis=0)
        template = robust_normalize(template)
        last_lags = np.array(lags, dtype=int)

    spread = np.nanstd(aligned_stack, axis=0, ddof=1)
    return template, spread, last_lags, aligned_stack

def exp_grid_fit(y, local_t):
    y = np.asarray(y, float)
    Z = np.exp(np.outer(POLE_GRID, local_t))
    n = y.size

    sy = y.sum()
    sy2 = y @ y
    sz = Z.sum(axis=1)
    sz2 = (Z*Z).sum(axis=1)
    szy = Z @ y

    det = n*sz2 - sz*sz
    det = np.where(np.abs(det) < 1e-14, np.nan, det)

    C = (sy*sz2 - sz*szy)/det
    A = (n*szy - sz*sy)/det
    sse = (
        sy2 - 2*C*sy - 2*A*szy
        + n*C*C + 2*C*A*sz + A*A*sz2
    )

    idx = int(np.nanargmin(sse))
    pred = C[idx] + A[idx]*Z[idx]
    return {
        "p": float(POLE_GRID[idx]),
        "C": float(C[idx]),
        "A": float(A[idx]),
        "pred": pred,
        "sse": float(max(sse[idx], 0.0)),
    }

def fit_piecewise_exponential(y):
    y = robust_normalize(median_filter(y, size=3))
    grid = list(range(0, N+1, GRID_STEP))
    if grid[-1] != N:
        grid.append(N)
    G = len(grid)

    cost = np.full((G, G), np.inf)
    for gi, i in enumerate(grid):
        for gj in range(gi+1, G):
            j = grid[gj]
            L = j - i
            if MIN_FIT_REGION <= L <= MAX_FIT_REGION:
                cost[gi, gj] = exp_grid_fit(
                    y[i:j], T[i:j] - T[i]
                )["sse"]

    dp = np.full((REGIONS+1, G), np.inf)
    prev = np.full((REGIONS+1, G), -1, dtype=int)
    dp[0, 0] = 0.0

    for k in range(1, REGIONS+1):
        for gj in range(1, G):
            vals = dp[k-1, :gj] + cost[:gj, gj]
            gi = int(np.argmin(vals))
            if np.isfinite(vals[gi]):
                dp[k, gj] = vals[gi]
                prev[k, gj] = gi

    if not np.isfinite(dp[REGIONS, G-1]):
        raise RuntimeError("Piecewise fit failed")

    idxs = [G-1]
    cur = G-1
    for k in range(REGIONS, 0, -1):
        cur = prev[k, cur]
        idxs.append(cur)
    idxs.reverse()

    boundaries = np.array([grid[q] for q in idxs], dtype=int)
    fit = np.empty(N)
    poles = []
    residues = []
    offsets = []

    for r in range(REGIONS):
        i, j = boundaries[r], boundaries[r+1]
        result = exp_grid_fit(y[i:j], T[i:j] - T[i])
        fit[i:j] = result["pred"]
        poles.append(result["p"])
        residues.append(result["A"])
        offsets.append(result["C"])

    return {
        "normalized_input": y,
        "fit": fit,
        "boundaries": boundaries,
        "poles": np.array(poles),
        "residues": np.array(residues),
        "offsets": np.array(offsets),
    }

# ------------------------------------------------------------
# Generate 100 families x 100 captures = 10,000 measurements.
# ------------------------------------------------------------
hidden_families = [generate_hidden_response(rng) for _ in range(FAMILIES)]
all_captures = []
for f in hidden_families:
    captures = [
        make_capture(f["truth"], rng, force_zero_shift=(i == 0))
        for i in range(CAPTURES_PER_FAMILY)
    ]
    all_captures.append(captures)

# ------------------------------------------------------------
# Build collective averages and fit each average.
# Also fit the first single capture as a baseline.
# ------------------------------------------------------------
rows = []
region_rows = []
example_payloads = {}

for family_idx, (hidden, captures) in enumerate(zip(hidden_families, all_captures)):
    collective, spread, recovered_lags, aligned_stack = build_collective_average(captures)
    collective_fit = fit_piecewise_exponential(collective)

    single = robust_normalize(median_filter(captures[0]["signal"], size=FILTER_KERNEL))
    single_fit = fit_piecewise_exponential(single)

    truth = hidden["truth_norm"]

    # Compare consensus and fitted models directly to the normalized hidden truth.
    consensus_rmse = float(np.sqrt(np.mean((collective - truth)**2)))
    collective_fit_rmse = float(np.sqrt(np.mean((collective_fit["fit"] - truth)**2)))
    single_fit_rmse = float(np.sqrt(np.mean((single_fit["fit"] - truth)**2)))

    boundary_mae_collective = float(np.mean(
        np.abs(collective_fit["boundaries"][1:-1] - hidden["boundaries"][1:-1])
    ))
    boundary_mae_single = float(np.mean(
        np.abs(single_fit["boundaries"][1:-1] - hidden["boundaries"][1:-1])
    ))

    # Region order is fixed, so compare pole magnitudes in log space.
    pole_log_mae_collective = float(np.mean(np.abs(
        np.log(np.abs(collective_fit["poles"]) / np.abs(hidden["poles"]))
    )))
    pole_log_mae_single = float(np.mean(np.abs(
        np.log(np.abs(single_fit["poles"]) / np.abs(hidden["poles"]))
    )))

    planted_lags = np.array([c["shift"] for c in captures])
    lag_mae = float(np.mean(np.abs(recovered_lags - planted_lags)))

    rows.append({
        "Family": family_idx,
        "Consensus RMSE vs truth": consensus_rmse,
        "Collective exp-fit RMSE vs truth": collective_fit_rmse,
        "Single-capture exp-fit RMSE vs truth": single_fit_rmse,
        "Collective boundary MAE (samples)": boundary_mae_collective,
        "Single boundary MAE (samples)": boundary_mae_single,
        "Collective pole log-MAE": pole_log_mae_collective,
        "Single pole log-MAE": pole_log_mae_single,
        "Alignment lag MAE (samples)": lag_mae,
        "Median pointwise spread": float(np.median(spread)),
    })

    for r in range(REGIONS):
        region_rows.append({
            "Family": family_idx,
            "Region": r + 1,
            "True pole": hidden["poles"][r],
            "Collective fitted pole": collective_fit["poles"][r],
            "Single fitted pole": single_fit["poles"][r],
            "True start": hidden["boundaries"][r],
            "Collective fitted start": collective_fit["boundaries"][r],
            "Single fitted start": single_fit["boundaries"][r],
        })

    if family_idx in (0, 1, 2):
        example_payloads[family_idx] = {
            "truth": truth,
            "collective": collective,
            "collective_fit": collective_fit["fit"],
            "single": single,
            "single_fit": single_fit["fit"],
            "spread": spread,
            "true_boundaries": hidden["boundaries"],
            "fit_boundaries": collective_fit["boundaries"],
        }

results = pd.DataFrame(rows)
regions = pd.DataFrame(region_rows)

summary = pd.DataFrame({
    "Metric": [
        "Median consensus RMSE vs hidden truth",
        "Median collective exponential-fit RMSE",
        "Median single-capture exponential-fit RMSE",
        "Median collective boundary MAE (samples)",
        "Median single boundary MAE (samples)",
        "Median collective pole log-MAE",
        "Median single pole log-MAE",
        "Median alignment lag MAE (samples)",
    ],
    "Value": [
        results["Consensus RMSE vs truth"].median(),
        results["Collective exp-fit RMSE vs truth"].median(),
        results["Single-capture exp-fit RMSE vs truth"].median(),
        results["Collective boundary MAE (samples)"].median(),
        results["Single boundary MAE (samples)"].median(),
        results["Collective pole log-MAE"].median(),
        results["Single pole log-MAE"].median(),
        results["Alignment lag MAE (samples)"].median(),
    ],
})

display_dataframe_to_user("WaveCompare 2 summary", summary)
display_dataframe_to_user("WaveCompare 2 per-family results", results)

collective_better_rmse = float(np.mean(
    results["Collective exp-fit RMSE vs truth"]
    < results["Single-capture exp-fit RMSE vs truth"]
))
collective_better_boundary = float(np.mean(
    results["Collective boundary MAE (samples)"]
    < results["Single boundary MAE (samples)"]
))
collective_better_pole = float(np.mean(
    results["Collective pole log-MAE"]
    < results["Single pole log-MAE"]
))

print(f"Distinct hidden responses:                {FAMILIES}")
print(f"Measurements per response:                {CAPTURES_PER_FAMILY}")
print(f"Total noisy measurements:                 {FAMILIES*CAPTURES_PER_FAMILY}")
print(f"Median consensus RMSE:                     {summary.iloc[0,1]:.5f}")
print(f"Median collective exp-fit RMSE:            {summary.iloc[1,1]:.5f}")
print(f"Median single-capture exp-fit RMSE:        {summary.iloc[2,1]:.5f}")
print(f"Collective fit beats single fit (RMSE):    {100*collective_better_rmse:.1f}%")
print(f"Collective beats single (boundaries):      {100*collective_better_boundary:.1f}%")
print(f"Collective beats single (poles):           {100*collective_better_pole:.1f}%")

# ------------------------------------------------------------
# Plots
# ------------------------------------------------------------
plt.figure(figsize=(10, 5.5))
plt.hist(
    results["Single-capture exp-fit RMSE vs truth"],
    bins=24,
    alpha=0.65,
    label="Fit from one noisy capture",
)
plt.hist(
    results["Collective exp-fit RMSE vs truth"],
    bins=24,
    alpha=0.65,
    label="Fit from average of 100 captures",
)
plt.xlabel("Exponential-fit RMSE against hidden truth")
plt.ylabel("Waveform-family count")
plt.title("Collective average versus single noisy measurement")
plt.legend()
plt.tight_layout()
rmse_plot = out / "wavecompare2_collective_vs_single_rmse.png"
plt.savefig(rmse_plot, dpi=180)
plt.show()

ex = example_payloads[0]
plt.figure(figsize=(11, 6))
plt.plot(T, ex["truth"], label="Hidden truth", linewidth=2.2)
plt.plot(T, ex["single"], alpha=0.45, label="One noisy measurement")
plt.plot(T, ex["collective"], label="Average of 100 aligned measurements", linewidth=1.8)
plt.plot(T, ex["collective_fit"], linestyle="--", label="Piecewise exponential fit")
for b in ex["fit_boundaries"][1:-1]:
    plt.axvline(T[b], alpha=0.25)
plt.xlabel("Time (s)")
plt.ylabel("Normalized response")
plt.title("WaveCompare 2 — family 0")
plt.legend()
plt.tight_layout()
example_plot = out / "wavecompare2_collective_example.png"
plt.savefig(example_plot, dpi=180)
plt.show()

plt.figure(figsize=(10, 5.5))
plt.scatter(
    results["Single-capture exp-fit RMSE vs truth"],
    results["Collective exp-fit RMSE vs truth"],
    s=28,
)
limit = max(
    results["Single-capture exp-fit RMSE vs truth"].max(),
    results["Collective exp-fit RMSE vs truth"].max(),
)
plt.plot([0, limit], [0, limit], linestyle="--")
plt.xlabel("Single-capture fit RMSE")
plt.ylabel("Collective-average fit RMSE")
plt.title("Points below the line improved after averaging 100 measurements")
plt.tight_layout()
scatter_plot = out / "wavecompare2_rmse_scatter.png"
plt.savefig(scatter_plot, dpi=180)
plt.show()

summary_csv = out / "wavecompare2_summary.csv"
results_csv = out / "wavecompare2_family_results.csv"
regions_csv = out / "wavecompare2_region_results.csv"
summary.to_csv(summary_csv, index=False)
results.to_csv(results_csv, index=False)
regions.to_csv(regions_csv, index=False)

# Save exact executed source.
ip = get_ipython()
source = None
for _, _, src in reversed(list(ip.history_manager.get_range(output=False, raw=True))):
    if "WAVECOMPARE 2:" in src and "build_collective_average" in src:
        source = src
        break
script_path = out / "wavecompare2_collective_average_test.py"
if source:
    script_path.write_text(source, encoding="utf-8")

print("\nSaved:")
for p in [
    rmse_plot, example_plot, scatter_plot,
    summary_csv, results_csv, regions_csv, script_path
]:
    print(p)