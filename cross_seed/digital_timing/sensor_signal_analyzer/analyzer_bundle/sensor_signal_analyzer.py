
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

EPS = 1e-12


@dataclass
class SensorCapture:
    t: np.ndarray
    sensor_output_v: np.ndarray
    command_v: Optional[np.ndarray] = None
    actuator_current_a: Optional[np.ndarray] = None
    position: Optional[np.ndarray] = None
    analog_sensor_v: Optional[np.ndarray] = None
    label: str = ""


def moving_average(x: np.ndarray, samples: int) -> np.ndarray:
    samples = max(1, int(samples))
    if samples == 1:
        return np.asarray(x, dtype=float)
    kernel = np.ones(samples, dtype=float) / samples
    return np.convolve(np.asarray(x, dtype=float), kernel, mode="same")


def robust_center_scale(values) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)
    center = float(np.median(x))
    mad = float(np.median(np.abs(x - center)))
    return center, max(1.4826 * mad, EPS)


def robust_z(value: float, baseline_values) -> float:
    center, scale = robust_center_scale(baseline_values)
    return float((value - center) / scale)


def estimate_rails(x: np.ndarray) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    return float(np.quantile(x, 0.05)), float(np.quantile(x, 0.95))


def crossing_times(t, x, level, direction):
    x = np.asarray(x, dtype=float)
    if direction == "rising":
        idx = np.flatnonzero((x[:-1] < level) & (x[1:] >= level))
    elif direction == "falling":
        idx = np.flatnonzero((x[:-1] > level) & (x[1:] <= level))
    else:
        raise ValueError("direction must be rising or falling")

    times = []
    for i in idx:
        x0, x1 = x[i], x[i + 1]
        if abs(x1 - x0) < EPS:
            times.append(float(t[i]))
        else:
            a = (level - x0) / (x1 - x0)
            times.append(float(t[i] + a * (t[i + 1] - t[i])))
    return np.asarray(times, dtype=float)


def first_crossing(t, x, level, direction, after_s=None):
    times = crossing_times(t, x, level, direction)
    if after_s is not None:
        times = times[times >= after_s]
    if len(times) == 0:
        raise ValueError(f"No {direction} crossing found")
    return float(times[0])


def schmitt_state(x, low_threshold, high_threshold):
    x = np.asarray(x, dtype=float)
    state = np.zeros(len(x), dtype=np.int8)
    state[0] = int(x[0] >= (low_threshold + high_threshold) / 2)
    for i in range(1, len(x)):
        if x[i] >= high_threshold:
            state[i] = 1
        elif x[i] <= low_threshold:
            state[i] = 0
        else:
            state[i] = state[i - 1]
    return state


def sustained_true_time(t, mask, dwell_s):
    dt = float(np.median(np.diff(t)))
    run = max(1, int(round(dwell_s / dt)))
    conv = np.convolve(mask.astype(int), np.ones(run, dtype=int), mode="valid")
    hits = np.flatnonzero(conv >= run)
    if len(hits) == 0:
        raise ValueError("No sustained event found")
    return float(t[int(hits[0])])


def settling_time(t, x, start_s, target, tolerance, dwell_s=0.001):
    start_i = int(np.searchsorted(t, start_s))
    mask = np.abs(x - target) <= tolerance
    dt = float(np.median(np.diff(t)))
    run = max(1, int(round(dwell_s / dt)))
    for i in range(start_i, len(x) - run):
        if np.all(mask[i:i + run]):
            return float(t[i] - start_s)
    return float(t[-1] - start_s)


def analyze_edge(t, output_v, direction="rising", nominal_low_v=0.0, nominal_high_v=24.0):
    dt = float(np.median(np.diff(t)))
    xs = moving_average(output_v, max(1, round(0.00008 / dt)))
    low, high = estimate_rails(xs)
    span = max(high - low, EPS)

    if direction == "rising":
        l10, l50, l90 = low + 0.1*span, low + 0.5*span, low + 0.9*span
    else:
        l10, l50, l90 = high - 0.1*span, high - 0.5*span, high - 0.9*span

    t10 = first_crossing(t, xs, l10, direction)
    t50 = first_crossing(t, xs, l50, direction, after_s=t10)
    t90 = first_crossing(t, xs, l90, direction, after_s=t50)

    edge_time = abs(t90 - t10)
    dvdt = np.gradient(xs, t)
    window = (t >= min(t10, t90)-0.0005) & (t <= max(t10, t90)+0.0005)
    max_slew = float(np.max(np.abs(dvdt[window])))

    after = xs[t >= t90]
    if direction == "rising":
        overshoot = max(0.0, float(np.max(after) - high)) / span
        target = high
    else:
        overshoot = max(0.0, float(low - np.min(after))) / span
        target = low

    settle = settling_time(t, xs, t90, target, 0.05*span, dwell_s=0.001)

    state = schmitt_state(xs, low + 0.4*span, low + 0.6*span)
    local = (t >= t10 - 0.001) & (t <= t90 + 0.015)
    idx = np.flatnonzero(local)
    chatter = 0
    if len(idx) > 2:
        transitions = int(np.sum(np.diff(state[idx[0]:idx[-1]+1]) != 0))
        chatter = max(0, transitions - 1)

    return {
        "direction": direction,
        "t10_s": t10,
        "t50_s": t50,
        "t90_s": t90,
        "transition_time_s": edge_time,
        "max_slew_v_per_s": max_slew,
        "overshoot_fraction": overshoot,
        "settling_time_s": settle,
        "chatter_reversals": chatter,
        "low_rail_v": low,
        "high_rail_v": high,
        "low_rail_error_v": low - nominal_low_v,
        "high_rail_error_v": high - nominal_high_v,
    }


def detect_step_time(t, x, direction="rising"):
    dt = float(np.median(np.diff(t)))
    xs = moving_average(x, max(1, round(0.00008 / dt)))
    low, high = estimate_rails(xs)
    return first_crossing(t, xs, low + 0.5*(high-low), direction)


def detect_current_onset(t, current):
    dt = float(np.median(np.diff(t)))
    xs = moving_average(current, max(1, round(0.00030 / dt)))
    n0 = max(20, int(0.12*len(xs)))
    baseline = float(np.median(xs[:n0]))
    high = float(np.quantile(xs, 0.95))
    threshold = baseline + 0.12*(high-baseline)
    mask = xs >= threshold
    return sustained_true_time(t, mask, dwell_s=0.0004)


def detect_motion_onset(t, position):
    """
    Sustained departure from the pre-motion baseline.
    More robust than differentiating a noisy position channel.
    """
    dt = float(np.median(np.diff(t)))
    xs = moving_average(position, max(1, round(0.00060 / dt)))
    n0 = max(20, int(0.12*len(xs)))
    baseline = float(np.median(xs[:n0]))
    low, high = estimate_rails(xs)
    span = max(high-low, EPS)
    mask = np.abs(xs - baseline) >= 0.012*span
    return sustained_true_time(t, mask, dwell_s=0.0007)


def detect_analog_threshold(t, analog_sensor_v, threshold_v, direction="rising"):
    dt = float(np.median(np.diff(t)))
    xs = moving_average(analog_sensor_v, max(1, round(0.00015 / dt)))
    return first_crossing(t, xs, threshold_v, direction)


def analyze_mode1(capture: SensorCapture, direction="rising"):
    return {
        "label": capture.label,
        **analyze_edge(capture.t, capture.sensor_output_v, direction),
    }


def analyze_mode2(capture: SensorCapture, direction="rising"):
    if capture.command_v is None:
        raise ValueError("Mode 2 requires command_v")
    edge = analyze_edge(capture.t, capture.sensor_output_v, direction)
    command_time = detect_step_time(capture.t, capture.command_v, "rising")
    return {
        "label": capture.label,
        **edge,
        "command_time_s": command_time,
        "command_to_sensor_latency_s": edge["t50_s"] - command_time,
    }


def analyze_mode3(capture: SensorCapture):
    if capture.position is None:
        raise ValueError("Mode 3 requires position")
    dt = float(np.median(np.diff(capture.t)))
    xs = moving_average(capture.sensor_output_v, max(1, round(0.00010 / dt)))
    low, high = estimate_rails(xs)
    midpoint = low + 0.5*(high-low)
    rises = crossing_times(capture.t, xs, midpoint, "rising")
    falls = crossing_times(capture.t, xs, midpoint, "falling")
    if len(rises) == 0:
        raise ValueError("No ON transition found")
    rise = float(rises[0])
    valid_falls = falls[falls > rise]
    if len(valid_falls) == 0:
        raise ValueError("No OFF transition found after ON transition")
    fall = float(valid_falls[0])
    on_position = float(np.interp(rise, capture.t, capture.position))
    off_position = float(np.interp(fall, capture.t, capture.position))
    return {
        "label": capture.label,
        "on_position": on_position,
        "off_position": off_position,
        "hysteresis_position": abs(off_position-on_position),
        "rising_edge_time_s": rise,
        "falling_edge_time_s": fall,
    }


def analyze_mode4(capture: SensorCapture, analog_threshold_v=0.60):
    if any(v is None for v in [
        capture.command_v,
        capture.actuator_current_a,
        capture.position,
        capture.analog_sensor_v,
    ]):
        raise ValueError("Mode 4 requires command, actuator current, position, analog sensor, and output")

    command_time = detect_step_time(capture.t, capture.command_v, "rising")
    current_time = detect_current_onset(capture.t, capture.actuator_current_a)
    motion_time = detect_motion_onset(capture.t, capture.position)
    threshold_time = detect_analog_threshold(capture.t, capture.analog_sensor_v, analog_threshold_v, "rising")
    output = analyze_edge(capture.t, capture.sensor_output_v, "rising")

    return {
        "label": capture.label,
        "command_time_s": command_time,
        "current_onset_s": current_time,
        "motion_onset_s": motion_time,
        "analog_threshold_time_s": threshold_time,
        "digital_output_time_s": output["t50_s"],
        "command_to_current_s": current_time-command_time,
        "current_to_motion_s": motion_time-current_time,
        "actuation_delay_s": motion_time-command_time,
        "actuator_response_time_s": threshold_time-motion_time,
        "sensor_decision_delay_s": output["t50_s"]-threshold_time,
        "total_chain_latency_s": output["t50_s"]-command_time,
    }
