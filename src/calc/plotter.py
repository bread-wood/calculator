from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from calc.evaluator import evaluate, _CONSTANTS_VALUES
from calc.errors import CalcError


class DomainEmpty(CalcError):
    def description(self) -> str:
        return "expression undefined over entire domain"


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    x_ticks: tuple[tuple[float, str], ...]
    y_ticks: tuple[tuple[float, str], ...]
    segments: tuple[tuple[tuple[float, float], ...], ...]


def _linspace(x_min: float, x_max: float, n: int) -> list[float]:
    if n == 1:
        return [x_min]
    return [x_min + i * (x_max - x_min) / (n - 1) for i in range(n)]


def _sample_expression(ast, x_values: list[float]) -> list[tuple[float, float | None]]:
    raw: list[tuple[float, float | None]] = []
    for x in x_values:
        env = dict(_CONSTANTS_VALUES)
        env["x"] = x
        try:
            y = evaluate(ast, env)
            if not math.isfinite(y):
                raw.append((x, None))
            else:
                raw.append((x, y))
        except CalcError:
            raw.append((x, None))
    return raw


def _build_segments(raw: list[tuple[float, float | None]]) -> list[list[tuple[float, float]]]:
    # Apply slope-jump heuristic to detect discontinuities
    valid_pairs = [
        (i, raw[i][1], raw[i + 1][1])
        for i in range(len(raw) - 1)
        if raw[i][1] is not None and raw[i + 1][1] is not None
    ]
    if valid_pairs:
        diffs = [abs(y1 - y0) for _, y0, y1 in valid_pairs]
        med = statistics.median(diffs)
        threshold = max(10 * med, 1e-12)
    else:
        threshold = 1e-12

    # Mark discontinuities: if slope jump too large, set left point to None
    marked = list(raw)
    for i, y0, y1 in valid_pairs:
        if abs(y1 - y0) > threshold:
            marked[i] = (marked[i][0], None)

    # Build segments from non-None runs
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for x, y in marked:
        if y is None:
            if len(current) >= 2:
                segments.append(current)
            current = []
        else:
            current.append((x, y))
    if len(current) >= 2:
        segments.append(current)
    return segments


def _calc_ticks(data_min: float, data_max: float, target_n: int = 6) -> list[tuple[float, str]]:
    """Heckbert nice-numbers tick algorithm (1990)."""
    if data_min >= data_max:
        return [(data_min, f"{data_min:.3g}")]

    data_range = data_max - data_min
    rough_step = data_range / target_n
    mag = math.floor(math.log10(rough_step))
    mag_pow = 10 ** mag
    normalized = rough_step / mag_pow

    if normalized <= 1.0:
        nice = 1.0
    elif normalized <= 2.0:
        nice = 2.0
    elif normalized <= 5.0:
        nice = 5.0
    else:
        nice = 10.0

    step = nice * mag_pow
    tick_min = math.ceil(data_min / step) * step
    tick_max = math.floor(data_max / step) * step

    ticks = []
    t = tick_min
    while t <= tick_max + step * 1e-9:
        if data_min - step * 0.1 <= t <= data_max + step * 0.1:
            label = f"{t:.3g}"
            ticks.append((t, label))
        t += step
        # Guard against float accumulation drift
        if len(ticks) > target_n * 3:
            break

    return ticks


def build_scene(
    ast,
    x_min: float,
    x_max: float,
    width: int,
    height: int,
) -> Scene:
    x_values = _linspace(x_min, x_max, width)
    raw = _sample_expression(ast, x_values)
    segments = _build_segments(raw)

    all_points = [pt for seg in segments for pt in seg]
    if not all_points:
        raise DomainEmpty()

    y_values = [pt[1] for pt in all_points]
    y_data_min = min(y_values)
    y_data_max = max(y_values)

    # 10% padding on y range
    y_span = y_data_max - y_data_min
    if y_span == 0:
        y_span = abs(y_data_min) if y_data_min != 0 else 1.0
    y_min = y_data_min - 0.1 * y_span
    y_max = y_data_max + 0.1 * y_span

    x_ticks = _calc_ticks(x_min, x_max)
    y_ticks = _calc_ticks(y_min, y_max)

    return Scene(
        width=width,
        height=height,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        x_ticks=tuple((wx, label) for wx, label in x_ticks),
        y_ticks=tuple((wy, label) for wy, label in y_ticks),
        segments=tuple(
            tuple((x, y) for x, y in seg)
            for seg in segments
        ),
    )
