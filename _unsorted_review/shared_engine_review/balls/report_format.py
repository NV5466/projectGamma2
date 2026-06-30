from __future__ import annotations

import textwrap


def title(lines: list[str], text: str, width: int) -> None:
    lines.append(text)
    lines.append("=" * min(width, max(20, len(text))))
    lines.append("")


def section(lines: list[str], text: str, width: int) -> None:
    lines.append("")
    lines.append(text)
    lines.append("-" * min(width, max(12, len(text))))


def kv_block(lines: list[str], rows: list[tuple[str, object]], width: int, indent: int = 0) -> None:
    label_width = min(24, max((len(label) for label, _ in rows), default=0))
    pad = " " * indent
    for label, value in rows:
        if value in (None, ""):
            continue
        prefix = f"{pad}{label:<{label_width}} : "
        wrapped_line(lines, str(value), width, prefix=prefix, continuation_indent=len(prefix))
    if rows:
        lines.append("")


def bullets(lines: list[str], values: list[str], width: int, indent: int = 0) -> None:
    pad = " " * indent
    for value in values:
        wrapped_line(lines, str(value), width, prefix=f"{pad}- ", continuation_indent=indent + 2)


def wrapped_line(
    lines: list[str],
    text: str,
    width: int,
    prefix: str = "",
    continuation_indent: int | None = None,
) -> None:
    continuation = " " * (continuation_indent if continuation_indent is not None else len(prefix))
    wrapped = textwrap.wrap(
        text,
        width=max(40, width),
        initial_indent=prefix,
        subsequent_indent=continuation,
        break_long_words=False,
        break_on_hyphens=False,
    )
    lines.extend(wrapped or [prefix.rstrip()])


def fmt_optional(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "not available"
    return f"{value:.6g}{suffix}"


def fmt_percent(value: float | None) -> str:
    if value is None:
        return "not available"
    return f"{value:.3%}"


def fmt_number(value: float) -> str:
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return f"{value:.0f}"
        return f"{value:.6g}"
    return str(value)


def fmt_window(value: list[float] | None) -> str:
    if not value:
        return "not applied"
    return f"{value[0]:.6g} s to {value[1]:.6g} s"


def fmt_peak_list(values: list[float]) -> str:
    if not values:
        return "none"
    return ", ".join(f"{value:.6g} Hz" for value in values)


def fmt_event_linked(values: list[dict[str, float]]) -> str:
    if not values:
        return "none"
    return ", ".join(f"{item['frequency_hz']:.6g} Hz (+{item['growth_db']:.3g} dB)" for item in values)
