import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import pytest

from calc.lexer import Lexer
from calc.parser import Parser
from calc.plotter import build_scene
from calc.renderer import get_renderer
from calc.renderer.png import PngRenderer
from calc.renderer.svg import SvgRenderer


def parse_expr(src: str):
    return Parser(Lexer(src)).parse_program().body[0]


def make_scene(expr: str = "x", xmin: float = -5.0, xmax: float = 5.0,
               w: int = 200, h: int = 150):
    ast = parse_expr(expr)
    return build_scene(ast, xmin, xmax, w, h)


def read_png_pixel(path: Path, col: int, row: int) -> tuple[int, int, int]:
    data = path.read_bytes()
    width, _ = struct.unpack(">II", data[16:24])
    pos = 8
    idat_payload = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        if tag == b"IDAT":
            idat_payload.extend(chunk_data)
        elif tag == b"IEND":
            break
        pos += 4 + 4 + length + 4
    raw = zlib.decompress(bytes(idat_payload))
    stride = 1 + width * 3
    offset = row * stride + 1 + col * 3
    return raw[offset], raw[offset + 1], raw[offset + 2]


# --- get_renderer dispatch ---

def test_get_renderer_png(tmp_path):
    r = get_renderer(tmp_path / "out.png")
    assert isinstance(r, PngRenderer)


def test_get_renderer_svg(tmp_path):
    r = get_renderer(tmp_path / "out.svg")
    assert isinstance(r, SvgRenderer)


def test_get_renderer_unknown_suffix(tmp_path):
    with pytest.raises(KeyError):
        get_renderer(tmp_path / "out.bmp")


# --- PngRenderer ---

def test_png_file_created(tmp_path):
    out = tmp_path / "plot.png"
    scene = make_scene()
    PngRenderer().render(scene, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_png_has_correct_dimensions(tmp_path):
    out = tmp_path / "plot.png"
    scene = make_scene(w=200, h=150)
    PngRenderer().render(scene, out)
    data = out.read_bytes()
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (200, 150)


def test_png_starts_with_signature(tmp_path):
    out = tmp_path / "plot.png"
    PngRenderer().render(make_scene(), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_curve_pixel_not_background(tmp_path):
    """At least one pixel should differ from the background (white)."""
    out = tmp_path / "plot.png"
    scene = make_scene("x", -5.0, 5.0, 200, 150)
    PngRenderer().render(scene, out)
    data = out.read_bytes()
    _, _ = struct.unpack(">II", data[16:24])
    raw = zlib.decompress(b"".join(
        data[pos + 8:pos + 8 + struct.unpack(">I", data[pos:pos + 4])[0]]
        for pos in _idat_positions(data)
    ))
    stride = 1 + 200 * 3
    non_white = any(
        raw[row * stride + 1 + col * 3] != 255
        for row in range(150) for col in range(200)
    )
    assert non_white


def _idat_positions(data: bytes) -> list[int]:
    positions = []
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        if tag == b"IDAT":
            positions.append(pos)
        elif tag == b"IEND":
            break
        pos += 4 + 4 + length + 4
    return positions


# --- SvgRenderer ---

def test_svg_file_created(tmp_path):
    out = tmp_path / "plot.svg"
    SvgRenderer().render(make_scene(), out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_svg_has_polyline(tmp_path):
    out = tmp_path / "plot.svg"
    SvgRenderer().render(make_scene("x", -5.0, 5.0, 200, 150), out)
    root = ET.parse(out).getroot()
    polylines = root.findall("polyline") or root.findall("{http://www.w3.org/2000/svg}polyline")
    assert len(polylines) >= 1


def test_svg_polyline_has_enough_points(tmp_path):
    out = tmp_path / "plot.svg"
    scene = make_scene("x", -5.0, 5.0, 200, 150)
    SvgRenderer().render(scene, out)
    root = ET.parse(out).getroot()
    polylines = root.findall("polyline") or root.findall("{http://www.w3.org/2000/svg}polyline")
    total_points = sum(
        len(pl.get("points", "").split())
        for pl in polylines
    )
    assert total_points >= scene.width  # at least 1 point pair per sample


def test_svg_y_range_spans_image(tmp_path):
    """Curve y-pixels should span a meaningful fraction of the image height."""
    out = tmp_path / "plot.svg"
    scene = make_scene("x", -5.0, 5.0, 200, 150)
    SvgRenderer().render(scene, out)
    root = ET.parse(out).getroot()
    polylines = root.findall("polyline") or root.findall("{http://www.w3.org/2000/svg}polyline")
    all_y = []
    for pl in polylines:
        for pt in pl.get("points", "").split():
            _, y = pt.split(",")
            all_y.append(float(y))
    if all_y:
        y_span = max(all_y) - min(all_y)
        assert y_span >= scene.height * 0.5
