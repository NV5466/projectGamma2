"""Gamma / ElectroStat Harmonic Distortion Seed v0.1.0.

Primary evidence is the normalized harmonic magnitude vector h, not THD.
WaveCompare 2 supplies the singular expected waveform. This seed analyzes:

    expected waveform -> h_expected
    measured waveform -> h_measured
    delta_h = h_measured - h_expected

Optional historical captures are also analyzed and stored, but they do not
participate in the v0.1.0 fault score. That later normal-variation logic belongs
to a future Gamma layer.

Method:
1. Remove DC and linear trend.
2. Estimate f0 by harmonic-summed, zero-padded spectral search.
3. Refine f0 by minimizing a low-order harmonic least-squares residual.
4. Fit sine/cosine coefficients exactly at n*f0 using linear least squares.
5. Normalize harmonic amplitudes to the fundamental.
6. Compare the full harmonic vector; compute THD only as a summary.

Synthetic research prototype only. Not field calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable
import math
import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize_scalar

Array = NDArray[np.float64]
ComplexArray = NDArray[np.complex128]


@dataclass(frozen=True)
class HarmonicConfig:
    minimum_frequency_hz: float = 40.0
    maximum_frequency_hz: float = 70.0
    maximum_harmonic_order: int = 20
    fundamental_refine_harmonics: int = 6
    zero_padding_factor: int = 8
    measured_frequency_search_fraction: float = 0.05
    minimum_absolute_harmonic_change: float = 0.0075
    harmonic_change_sigma: float = 4.0
    total_fingerprint_distance_threshold: float = 0.012
    minimum_fundamental_snr: float = 12.0
    minimum_harmonic_fit_fraction: float = 0.20
    maximum_reported_changes: int = 8
    epsilon: float = 1e-12

    def __post_init__(self) -> None:
        if self.minimum_frequency_hz <= 0:
            raise ValueError("minimum_frequency_hz must be positive")
        if self.maximum_frequency_hz <= self.minimum_frequency_hz:
            raise ValueError("maximum_frequency_hz must exceed minimum")
        if self.maximum_harmonic_order < 2:
            raise ValueError("maximum_harmonic_order must be >= 2")
        if self.fundamental_refine_harmonics < 1:
            raise ValueError("fundamental_refine_harmonics must be >= 1")
        if self.zero_padding_factor < 2:
            raise ValueError("zero_padding_factor must be >= 2")
        if not 0 < self.measured_frequency_search_fraction < 0.5:
            raise ValueError("measured_frequency_search_fraction is invalid")
        if min(
            self.minimum_absolute_harmonic_change,
            self.harmonic_change_sigma,
            self.total_fingerprint_distance_threshold,
            self.minimum_fundamental_snr,
        ) <= 0:
            raise ValueError("thresholds must be positive")
        if not 0 <= self.minimum_harmonic_fit_fraction <= 1:
            raise ValueError("minimum_harmonic_fit_fraction must be in [0, 1]")


@dataclass(frozen=True)
class HarmonicFingerprint:
    fundamental_hz: float
    harmonic_orders: Array
    peak_amplitudes: Array
    amplitude_standard_errors: Array
    normalized_magnitudes: Array
    normalized_magnitude_standard_errors: Array
    relative_phases_deg: Array
    shift_invariant_complex: ComplexArray
    thd: float
    odd_harmonic_rss: float
    even_harmonic_rss: float
    harmonic_fit_fraction: float
    residual_rms: float
    fundamental_snr: float
    reconstructed_waveform: Array
    residual_waveform: Array

    def table(self) -> list[dict[str, float]]:
        return [
            {
                "order": int(order),
                "frequency_hz": float(order * self.fundamental_hz),
                "normalized_magnitude": float(magnitude),
                "normalized_magnitude_se": float(se),
                "relative_phase_deg": float(phase),
            }
            for order, magnitude, se, phase in zip(
                self.harmonic_orders,
                self.normalized_magnitudes,
                self.normalized_magnitude_standard_errors,
                self.relative_phases_deg,
            )
        ]


@dataclass(frozen=True)
class HistoricalHarmonicContext:
    capture_count: int
    harmonic_orders: Array
    capture_magnitude_matrix: Array
    mean_magnitudes: Array
    standard_deviation_magnitudes: Array
    phase_consistency: Array
    used_in_fault_score: bool = False


@dataclass(frozen=True)
class HarmonicChange:
    order: int
    frequency_hz: float
    expected_magnitude: float
    measured_magnitude: float
    delta_magnitude: float
    significance_sigma: float
    expected_relative_phase_deg: float
    measured_relative_phase_deg: float
    relative_phase_change_deg: float


@dataclass(frozen=True)
class HarmonicEvidence:
    status: str
    expected: HarmonicFingerprint
    measured: HarmonicFingerprint
    delta_h: Array
    delta_h_sigma: Array
    complex_fingerprint_delta: ComplexArray
    magnitude_fingerprint_distance: float
    complex_fingerprint_distance: float
    expected_thd: float
    measured_thd: float
    delta_thd: float
    frequency_shift_hz: float
    active_changed_orders: tuple[int, ...]
    dominant_changes: tuple[HarmonicChange, ...]
    historical_context: HistoricalHarmonicContext | None
    historical_context_used_in_fault_score: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "expected_f0_hz": self.expected.fundamental_hz,
            "measured_f0_hz": self.measured.fundamental_hz,
            "frequency_shift_hz": self.frequency_shift_hz,
            "expected_thd": self.expected_thd,
            "measured_thd": self.measured_thd,
            "delta_thd": self.delta_thd,
            "magnitude_fingerprint_distance": self.magnitude_fingerprint_distance,
            "complex_fingerprint_distance": self.complex_fingerprint_distance,
            "active_changed_orders": list(self.active_changed_orders),
            "dominant_changes": [asdict(change) for change in self.dominant_changes],
            "historical_context_present": self.historical_context is not None,
            "historical_context_used_in_fault_score": self.historical_context_used_in_fault_score,
            "notes": list(self.notes),
        }


def _validate_waveform(waveform: Array, name: str = "waveform") -> Array:
    waveform = np.asarray(waveform, dtype=float)
    if waveform.ndim != 1 or waveform.size < 32:
        raise ValueError(f"{name} must be a one-dimensional waveform with >= 32 samples")
    if not np.isfinite(waveform).all():
        raise ValueError(f"{name} must contain only finite values")
    return waveform


def _remove_linear_trend(waveform: Array) -> Array:
    n = waveform.size
    x = np.linspace(-1.0, 1.0, n)
    X = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(X, waveform, rcond=None)
    return waveform - X @ beta


def _next_power_of_two(value: int) -> int:
    return 1 << max(1, int(value - 1).bit_length())


def _harmonic_least_squares(
    waveform: Array,
    sample_rate_hz: float,
    fundamental_hz: float,
    maximum_harmonic_order: int,
    epsilon: float,
) -> dict[str, Any]:
    waveform = _validate_waveform(waveform)
    n = waveform.size
    t = np.arange(n, dtype=float) / sample_rate_hz
    centered_t = t - np.mean(t)

    nyquist_guard = 0.98 * sample_rate_hz / 2.0
    maximum_order = min(
        maximum_harmonic_order,
        int(math.floor(nyquist_guard / fundamental_hz)),
    )
    if maximum_order < 1:
        raise ValueError("fundamental is too close to Nyquist")

    columns: list[Array] = [np.ones(n), centered_t]
    for order in range(1, maximum_order + 1):
        angle = 2.0 * np.pi * order * fundamental_hz * t
        columns.extend([np.cos(angle), np.sin(angle)])
    design = np.column_stack(columns)

    coefficients, *_ = np.linalg.lstsq(design, waveform, rcond=None)
    reconstructed = design @ coefficients
    residual = waveform - reconstructed

    degrees_of_freedom = max(n - design.shape[1], 1)
    residual_variance = float(np.dot(residual, residual) / degrees_of_freedom)
    covariance = residual_variance * np.linalg.pinv(design.T @ design)

    amplitudes = np.empty(maximum_order, dtype=float)
    phases = np.empty(maximum_order, dtype=float)
    complex_coefficients = np.empty(maximum_order, dtype=complex)
    amplitude_standard_errors = np.empty(maximum_order, dtype=float)

    for order in range(1, maximum_order + 1):
        index = 2 + 2 * (order - 1)
        cosine_coefficient = float(coefficients[index])
        sine_coefficient = float(coefficients[index + 1])
        amplitude = math.hypot(cosine_coefficient, sine_coefficient)
        phase = math.atan2(-sine_coefficient, cosine_coefficient)

        amplitudes[order - 1] = amplitude
        phases[order - 1] = phase
        complex_coefficients[order - 1] = (
            cosine_coefficient - 1j * sine_coefficient
        )

        coefficient_covariance = covariance[index:index + 2, index:index + 2]
        if amplitude > epsilon:
            gradient = np.array(
                [cosine_coefficient / amplitude, sine_coefficient / amplitude]
            )
            amplitude_variance = max(
                float(gradient @ coefficient_covariance @ gradient),
                0.0,
            )
        else:
            amplitude_variance = max(
                float(np.trace(coefficient_covariance)),
                0.0,
            )
        amplitude_standard_errors[order - 1] = math.sqrt(amplitude_variance)

    centered_energy = float(np.dot(waveform - np.mean(waveform), waveform - np.mean(waveform)))
    residual_energy = float(np.dot(residual, residual))
    harmonic_fit_fraction = float(
        np.clip(1.0 - residual_energy / max(centered_energy, epsilon), 0.0, 1.0)
    )

    return {
        "maximum_order": maximum_order,
        "amplitudes": amplitudes,
        "phases": phases,
        "complex_coefficients": complex_coefficients,
        "amplitude_standard_errors": amplitude_standard_errors,
        "reconstructed": reconstructed,
        "residual": residual,
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
        "harmonic_fit_fraction": harmonic_fit_fraction,
    }


def estimate_fundamental(
    waveform: Array,
    sample_rate_hz: float,
    config: HarmonicConfig = HarmonicConfig(),
    hint_hz: float | None = None,
) -> float:
    waveform = _validate_waveform(waveform)
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")

    detrended = _remove_linear_trend(waveform)
    n = detrended.size
    nfft = _next_power_of_two(config.zero_padding_factor * n)
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(detrended * window, n=nfft))
    frequencies = np.fft.rfftfreq(nfft, d=1.0 / sample_rate_hz)

    if hint_hz is None:
        lower = config.minimum_frequency_hz
        upper = config.maximum_frequency_hz
    else:
        lower = max(
            config.minimum_frequency_hz,
            hint_hz * (1.0 - config.measured_frequency_search_fraction),
        )
        upper = min(
            config.maximum_frequency_hz,
            hint_hz * (1.0 + config.measured_frequency_search_fraction),
        )

    candidate_mask = (frequencies >= lower) & (frequencies <= upper)
    candidates = frequencies[candidate_mask]
    if candidates.size < 3:
        raise ValueError("frequency search interval is too narrow")

    scores = np.zeros_like(candidates)
    nyquist = sample_rate_hz / 2.0
    score_harmonics = min(
        config.maximum_harmonic_order,
        config.fundamental_refine_harmonics,
    )
    for order in range(1, score_harmonics + 1):
        valid = order * candidates < 0.98 * nyquist
        values = np.interp(
            order * candidates[valid],
            frequencies,
            spectrum,
        )
        scores[valid] += values**2 / (order**1.2)

    # Requiring the first harmonic to carry weight suppresses subharmonic guesses.
    scores += 2.0 * np.interp(candidates, frequencies, spectrum) ** 2
    coarse_fundamental = float(candidates[int(np.argmax(scores))])

    fft_spacing = sample_rate_hz / nfft
    refine_lower = max(lower, coarse_fundamental - 2.5 * fft_spacing)
    refine_upper = min(upper, coarse_fundamental + 2.5 * fft_spacing)

    def objective(candidate_hz: float) -> float:
        fit = _harmonic_least_squares(
            detrended,
            sample_rate_hz,
            candidate_hz,
            min(
                config.fundamental_refine_harmonics,
                config.maximum_harmonic_order,
            ),
            config.epsilon,
        )
        return float(np.dot(fit["residual"], fit["residual"]))

    refined = minimize_scalar(
        objective,
        bounds=(refine_lower, refine_upper),
        method="bounded",
        options={"xatol": 1e-7, "maxiter": 40},
    )
    return float(refined.x)


def extract_harmonic_fingerprint(
    waveform: Array,
    sample_interval_s: float,
    config: HarmonicConfig = HarmonicConfig(),
    fundamental_hint_hz: float | None = None,
) -> HarmonicFingerprint:
    waveform = _validate_waveform(waveform)
    if sample_interval_s <= 0:
        raise ValueError("sample_interval_s must be positive")
    sample_rate_hz = 1.0 / sample_interval_s

    fundamental_hz = estimate_fundamental(
        waveform,
        sample_rate_hz,
        config,
        hint_hz=fundamental_hint_hz,
    )
    fit = _harmonic_least_squares(
        waveform,
        sample_rate_hz,
        fundamental_hz,
        config.maximum_harmonic_order,
        config.epsilon,
    )

    amplitudes = fit["amplitudes"]
    amplitude_standard_errors = fit["amplitude_standard_errors"]
    phases = fit["phases"]
    if amplitudes.size < 2:
        raise ValueError("not enough resolvable harmonic orders")

    fundamental_amplitude = max(float(amplitudes[0]), config.epsilon)
    fundamental_standard_error = float(amplitude_standard_errors[0])
    harmonic_orders = np.arange(2, amplitudes.size + 1, dtype=float)
    normalized_magnitudes = amplitudes[1:] / fundamental_amplitude
    normalized_standard_errors = np.sqrt(
        (amplitude_standard_errors[1:] / fundamental_amplitude) ** 2
        + (
            amplitudes[1:]
            * fundamental_standard_error
            / fundamental_amplitude**2
        ) ** 2
    )

    relative_phases = phases[1:] - harmonic_orders * phases[0]
    relative_phases = np.angle(np.exp(1j * relative_phases))
    shift_invariant_complex = normalized_magnitudes * np.exp(1j * relative_phases)

    odd_mask = (harmonic_orders.astype(int) % 2) == 1
    even_mask = ~odd_mask
    odd_harmonic_rss = float(np.linalg.norm(normalized_magnitudes[odd_mask]))
    even_harmonic_rss = float(np.linalg.norm(normalized_magnitudes[even_mask]))
    thd = float(np.linalg.norm(normalized_magnitudes))
    fundamental_snr = float(
        fundamental_amplitude / max(fundamental_standard_error, config.epsilon)
    )

    return HarmonicFingerprint(
        fundamental_hz=fundamental_hz,
        harmonic_orders=harmonic_orders,
        peak_amplitudes=amplitudes,
        amplitude_standard_errors=amplitude_standard_errors,
        normalized_magnitudes=normalized_magnitudes,
        normalized_magnitude_standard_errors=normalized_standard_errors,
        relative_phases_deg=np.degrees(relative_phases),
        shift_invariant_complex=shift_invariant_complex,
        thd=thd,
        odd_harmonic_rss=odd_harmonic_rss,
        even_harmonic_rss=even_harmonic_rss,
        harmonic_fit_fraction=float(fit["harmonic_fit_fraction"]),
        residual_rms=float(fit["residual_rms"]),
        fundamental_snr=fundamental_snr,
        reconstructed_waveform=np.asarray(fit["reconstructed"], dtype=float),
        residual_waveform=np.asarray(fit["residual"], dtype=float),
    )


def analyze_historical_captures(
    captures: Array,
    sample_interval_s: float,
    expected_fundamental_hz: float,
    config: HarmonicConfig = HarmonicConfig(),
) -> HistoricalHarmonicContext:
    captures = np.asarray(captures, dtype=float)
    if captures.ndim != 2 or captures.shape[0] < 1:
        raise ValueError("captures must have shape (capture_count, sample_count)")

    fingerprints = [
        extract_harmonic_fingerprint(
            capture,
            sample_interval_s,
            config,
            fundamental_hint_hz=expected_fundamental_hz,
        )
        for capture in captures
    ]
    minimum_orders = min(fp.normalized_magnitudes.size for fp in fingerprints)
    magnitude_matrix = np.vstack(
        [fp.normalized_magnitudes[:minimum_orders] for fp in fingerprints]
    )
    complex_matrix = np.vstack(
        [fp.shift_invariant_complex[:minimum_orders] for fp in fingerprints]
    )

    mean_complex = np.mean(complex_matrix, axis=0)
    mean_magnitude = np.mean(np.abs(complex_matrix), axis=0)
    phase_consistency = np.abs(mean_complex) / np.maximum(
        mean_magnitude,
        config.epsilon,
    )

    return HistoricalHarmonicContext(
        capture_count=int(captures.shape[0]),
        harmonic_orders=np.arange(2, minimum_orders + 2, dtype=float),
        capture_magnitude_matrix=magnitude_matrix,
        mean_magnitudes=np.mean(magnitude_matrix, axis=0),
        standard_deviation_magnitudes=np.std(magnitude_matrix, axis=0, ddof=1)
        if captures.shape[0] > 1
        else np.zeros(minimum_orders),
        phase_consistency=phase_consistency,
        used_in_fault_score=False,
    )


def _wrapped_phase_difference_deg(measured: Array, expected: Array) -> Array:
    return np.degrees(np.angle(np.exp(1j * np.radians(measured - expected))))


def run_harmonic_distortion_seed(
    expected_waveform: Array,
    measured_waveform: Array,
    sample_interval_s: float,
    historical_captures: Array | None = None,
    config: HarmonicConfig = HarmonicConfig(),
) -> HarmonicEvidence:
    expected_waveform = _validate_waveform(expected_waveform, "expected_waveform")
    measured_waveform = _validate_waveform(measured_waveform, "measured_waveform")
    if expected_waveform.shape != measured_waveform.shape:
        raise ValueError("expected and measured waveforms must have the same shape")

    expected = extract_harmonic_fingerprint(
        expected_waveform,
        sample_interval_s,
        config,
    )
    measured = extract_harmonic_fingerprint(
        measured_waveform,
        sample_interval_s,
        config,
        fundamental_hint_hz=expected.fundamental_hz,
    )

    common_orders = min(
        expected.normalized_magnitudes.size,
        measured.normalized_magnitudes.size,
    )
    if common_orders < 1:
        raise ValueError("expected and measured fingerprints do not overlap")

    expected_h = expected.normalized_magnitudes[:common_orders]
    measured_h = measured.normalized_magnitudes[:common_orders]
    delta_h = measured_h - expected_h
    combined_standard_error = np.sqrt(
        expected.normalized_magnitude_standard_errors[:common_orders] ** 2
        + measured.normalized_magnitude_standard_errors[:common_orders] ** 2
    )
    delta_h_sigma = np.abs(delta_h) / np.maximum(
        combined_standard_error,
        config.epsilon,
    )

    expected_complex = expected.shift_invariant_complex[:common_orders]
    measured_complex = measured.shift_invariant_complex[:common_orders]
    complex_delta = measured_complex - expected_complex

    active_mask = (
        (np.abs(delta_h) >= config.minimum_absolute_harmonic_change)
        & (delta_h_sigma >= config.harmonic_change_sigma)
    )
    orders = expected.harmonic_orders[:common_orders].astype(int)
    active_orders = tuple(int(order) for order in orders[active_mask])

    magnitude_distance = float(np.linalg.norm(delta_h))
    complex_distance = float(np.linalg.norm(complex_delta))

    expected_periodic = (
        expected.fundamental_snr >= config.minimum_fundamental_snr
        and expected.harmonic_fit_fraction >= config.minimum_harmonic_fit_fraction
    )
    measured_periodic = (
        measured.fundamental_snr >= config.minimum_fundamental_snr
        and measured.harmonic_fit_fraction >= config.minimum_harmonic_fit_fraction
    )

    if not expected_periodic:
        status = "insufficient_expected_periodicity"
    elif not measured_periodic:
        status = "insufficient_measured_periodicity"
    elif active_orders or magnitude_distance >= config.total_fingerprint_distance_threshold:
        status = "harmonic_deviation_supported"
    else:
        status = "no_harmonic_deviation_supported"

    phase_changes = _wrapped_phase_difference_deg(
        measured.relative_phases_deg[:common_orders],
        expected.relative_phases_deg[:common_orders],
    )
    change_indices = np.argsort(np.abs(delta_h))[::-1][
        : config.maximum_reported_changes
    ]
    dominant_changes = tuple(
        HarmonicChange(
            order=int(orders[index]),
            frequency_hz=float(orders[index] * measured.fundamental_hz),
            expected_magnitude=float(expected_h[index]),
            measured_magnitude=float(measured_h[index]),
            delta_magnitude=float(delta_h[index]),
            significance_sigma=float(delta_h_sigma[index]),
            expected_relative_phase_deg=float(expected.relative_phases_deg[index]),
            measured_relative_phase_deg=float(measured.relative_phases_deg[index]),
            relative_phase_change_deg=float(phase_changes[index]),
        )
        for index in change_indices
    )

    historical_context = None
    if historical_captures is not None:
        historical_context = analyze_historical_captures(
            historical_captures,
            sample_interval_s,
            expected.fundamental_hz,
            config,
        )

    return HarmonicEvidence(
        status=status,
        expected=expected,
        measured=measured,
        delta_h=delta_h,
        delta_h_sigma=delta_h_sigma,
        complex_fingerprint_delta=complex_delta,
        magnitude_fingerprint_distance=magnitude_distance,
        complex_fingerprint_distance=complex_distance,
        expected_thd=expected.thd,
        measured_thd=measured.thd,
        delta_thd=float(measured.thd - expected.thd),
        frequency_shift_hz=float(measured.fundamental_hz - expected.fundamental_hz),
        active_changed_orders=active_orders,
        dominant_changes=dominant_changes,
        historical_context=historical_context,
        historical_context_used_in_fault_score=False,
        notes=(
            "The normalized harmonic magnitude vector h is the primary evidence.",
            "THD is derived from h and is not used as the sole diagnostic measurement.",
            "Relative harmonic phase is preserved as supporting evidence but does not drive the v0.1.0 status.",
            "Historical capture fingerprints are stored but do not participate in the current fault score.",
            "Frequency shift and non-harmonic residual energy are reported separately from harmonic distortion.",
            "Synthetic research prototype only; no field-calibration claim.",
        ),
    )


# Clear adapter name for Gamma / WaveCompare 2 integration.
def analyze_wavecompare2_harmonics(
    expected_waveform: Array,
    new_capture: Array,
    sample_interval_s: float,
    old_captures: Array | None = None,
    config: HarmonicConfig = HarmonicConfig(),
) -> HarmonicEvidence:
    return run_harmonic_distortion_seed(
        expected_waveform=expected_waveform,
        measured_waveform=new_capture,
        sample_interval_s=sample_interval_s,
        historical_captures=old_captures,
        config=config,
    )
