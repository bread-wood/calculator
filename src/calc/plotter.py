from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from calc.errors import CalcError, DomainEmpty
from calc.evaluator import _CONSTANTS_VALUES, evaluate
from calc.parser import ASTNode


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    x_ticks: tuple[tuple[float, str], ...]   # ((world_x, label), ...)
    y_ticks: tuple[tuple[float, str], ...]   # ((world_y, label), ...)
    segments: tuple[tuple[tuple[float, float], ...], ...]
    # segments: outer=list of curves, inner=list of (x,y) points per curve


def build_scene(
    ast: ASTNode,
    x_min: float,
    x_max: float,
    width: int,
    height: int,
) -> Scene:
    # 1. Sample x values
    n = width
    if n == 1:
        x_values = [x_min]
    else:
        x_values = [x_min + i * (x_max - x_min) / (n - 1) for i in range(n)]

    # 2. Sample expression
    raw = sample_expression(ast, x_values)

    # 3. Slope-jump heuristic
    valid_pairs = [
        (raw[i][1], raw[i + 1][1])
        for i in range(len(raw) - 1)
        if raw[i][1] is not None and raw[i + 1][1] is not None
    ]
    if valid_pairs:
        diffs = [abs(b - a) for a, b in valid_pairs]
        threshold = max(10 * statistics.median(diffs), 1e-12)
        raw_list = list(raw)
        for i in range(len(raw_list) - 1):
            xi, yi = raw_list[i]
            xn, yn = raw_list[i + 1]
            if yi is not None and yn is not None:
                if abs(yn - yi) > threshold:
                    raw_list[i] = (xi, None)
        raw = raw_list

    # 4. Build segments
    segments = build_segments(raw)

    # 5. Check for empty domain
    if sum(len(s) for s in segments) == 0:
        raise DomainEmpty()

    # 6. Compute y range
    y_valid = [y for seg in segments for (_, y) in seg]
    y_min_data, y_max_data = min(y_valid), max(y_valid)
    if y_min_data == y_max_data:
        y_min = y_min_data - 0.5
        y_max = y_max_data + 0.5
    else:
        span = y_max_data - y_min_data
        y_min = y_min_data - 0.1 * span
        y_max = y_max_data + 0.1 * span

    # 7. Compute ticks
    x_ticks = calc_ticks(x_min, x_max)
    y_ticks = calc_ticks(y_min, y_max)

    # 8. Return Scene
    return Scene(
        width=width, height=height,
        x_min=x_min, x_max=x_max,
        y_min=y_min, y_max=y_max,
        x_ticks=tuple(x_ticks),
        y_ticks=tuple(y_ticks),
        segments=tuple(tuple(seg) for seg in segments),
    )


def sample_expression(
    ast: ASTNode,
    x_values: list[float],
) -> list[tuple[float, float | None]]:
    result = []
    for xi in x_values:
        env = {"x": xi, **_CONSTANTS_VALUES}
        try:
            y = evaluate(ast, env, None)
            result.append((xi, y))
        except CalcError:
            result.append((xi, None))
    return result


def build_segments(
    raw: list[tuple[float, float | None]],
) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for x, y in raw:
        if y is None:
            if current:
                segments.append(current)
                current = []
        else:
            current.append((x, y))
    if current:
        segments.append(current)
    return segments


def nice_num(x: float, round_: bool) -> float:
    exp = math.floor(math.log10(x))
    f = x / 10**exp  # fractional part: 1 <= f < 10
    if round_:
        if f < 1.5:
            nf = 1
        elif f < 3:
            nf = 2
        elif f < 7:
            nf = 5
        else:
            nf = 10
    else:
        if f <= 1:
            nf = 1
        elif f <= 2:
            nf = 2
        elif f <= 5:
            nf = 5
        else:
            nf = 10
    return nf * 10**exp


def calc_ticks(
    data_min: float,
    data_max: float,
    target_n: int = 6,
) -> list[tuple[float, str]]:
    span = data_max - data_min
    if span <= 0:
        return [(data_min, f"{data_min:.3g}"), (data_max, f"{data_max:.3g}")]

    range_ = nice_num(span, False)
    d = nice_num(range_ / (target_n - 1), True)
    graph_min = math.floor(data_min / d) * d
    graph_max = math.ceil(data_max / d) * d
    n_steps = round((graph_max - graph_min) / d)
    ticks_raw = [graph_min + i * d for i in range(n_steps + 1)]
    tol = d * 1e-10
    ticks = [t for t in ticks_raw if data_min - tol <= t <= data_max + tol]
    labels = [f"{t:.3g}" for t in ticks]
    result = list(zip(ticks, labels))
    if len(result) < 2:
        return [(data_min, f"{data_min:.3g}"), (data_max, f"{data_max:.3g}")]
    return result
