import math
import pytest

from calc.errors import DomainEmpty
from calc.lexer import Lexer
from calc.parser import Parser
from calc.plotter import build_scene


def parse_expr(src: str):
    prog = Parser(Lexer(src)).parse_program()
    return prog.body[0]


# --- Scene IR invariants ---

def test_linear_scene_bounds():
    ast = parse_expr("x")
    scene = build_scene(ast, -10.0, 10.0, 800, 600)
    assert scene.x_min == -10.0
    assert scene.x_max == 10.0
    assert scene.width == 800
    assert scene.height == 600


def test_linear_has_one_segment():
    ast = parse_expr("x")
    scene = build_scene(ast, -10.0, 10.0, 800, 600)
    assert len(scene.segments) == 1
    assert len(scene.segments[0]) == 800  # ≥1 sample per pixel


def test_y_range_padded():
    # y = x over [-1, 1]: y_min_data=-1, y_max_data=1, span=2, padding=0.2
    ast = parse_expr("x")
    scene = build_scene(ast, -1.0, 1.0, 100, 100)
    assert scene.y_min < -1.0
    assert scene.y_max > 1.0


def test_constant_function_padded():
    # y = 3 (constant); y_min_data == y_max_data → pad by 0.5
    ast = parse_expr("3")
    scene = build_scene(ast, -5.0, 5.0, 100, 100)
    assert scene.y_min == pytest.approx(2.5)
    assert scene.y_max == pytest.approx(3.5)


def test_x_ticks_within_domain():
    ast = parse_expr("x")
    scene = build_scene(ast, -10.0, 10.0, 800, 600)
    for tick_x, _ in scene.x_ticks:
        assert scene.x_min <= tick_x <= scene.x_max


def test_y_ticks_within_range():
    ast = parse_expr("x")
    scene = build_scene(ast, -10.0, 10.0, 800, 600)
    for tick_y, _ in scene.y_ticks:
        assert scene.y_min <= tick_y <= scene.y_max


def test_tick_labels_are_strings():
    ast = parse_expr("x")
    scene = build_scene(ast, -10.0, 10.0, 800, 600)
    for _, label in scene.x_ticks:
        assert isinstance(label, str)


# --- Discontinuity detection ---

def test_tan_has_multiple_segments():
    # tan(x) has discontinuities near ±π/2 in [-π, π]
    ast = parse_expr("sin(x) / cos(x)")
    scene = build_scene(ast, -math.pi, math.pi, 800, 600)
    assert len(scene.segments) >= 2


def test_reciprocal_has_gap_at_zero():
    # 1/x has a discontinuity at x=0
    ast = parse_expr("1 / x")
    scene = build_scene(ast, -5.0, 5.0, 800, 600)
    assert len(scene.segments) >= 2


def test_sqrt_negative_domain_raises():
    # sqrt(x) over all-negative domain → DomainEmpty
    ast = parse_expr("sqrt(x)")
    with pytest.raises(DomainEmpty):
        build_scene(ast, -10.0, -1.0, 100, 100)


def test_all_undefined_raises():
    # 1/0 (constant, always undefined) → DomainEmpty
    ast = parse_expr("1 / 0")
    with pytest.raises(DomainEmpty):
        build_scene(ast, -5.0, 5.0, 100, 100)


# --- Scene is frozen ---

def test_scene_is_frozen():
    ast = parse_expr("x")
    scene = build_scene(ast, -1.0, 1.0, 10, 10)
    with pytest.raises(Exception):  # FrozenInstanceError
        scene.width = 999  # type: ignore


# --- Segment tuple structure ---

def test_segments_are_tuples():
    ast = parse_expr("x")
    scene = build_scene(ast, -1.0, 1.0, 10, 10)
    assert isinstance(scene.segments, tuple)
    for seg in scene.segments:
        assert isinstance(seg, tuple)
        for pt in seg:
            assert isinstance(pt, tuple)
            assert len(pt) == 2
