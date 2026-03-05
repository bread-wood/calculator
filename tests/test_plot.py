"""End-to-end integration tests for the plot subcommand."""
from __future__ import annotations

import struct
import subprocess
import sys
import zlib
from pathlib import Path


def run_calc(*args: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "calc", *args],
        capture_output=True, text=True, cwd=cwd,
    )


def read_png_pixel(path: Path, col: int, row: int) -> tuple[int, int, int]:
    """Read a single RGB pixel from a filter-type-0 PNG produced by encode_png."""
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


# --- Success cases ---

def test_plot_creates_png(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "x", "--output", str(out))
    assert result.returncode == 0
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_creates_svg(tmp_path):
    out = tmp_path / "out.svg"
    result = run_calc("plot", "sin(x)", "--output", str(out))
    assert result.returncode == 0
    assert out.exists()
    assert "<polyline" in out.read_text()


def test_plot_no_stdout(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "x", "--output", str(out))
    assert result.stdout == ""


def test_plot_png_correct_dimensions(tmp_path):
    out = tmp_path / "out.png"
    run_calc("plot", "x", "--width", "300", "--height", "200", "--output", str(out))
    data = out.read_bytes()
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (300, 200)


def test_plot_default_domain(tmp_path):
    """Default xmin=-10, xmax=10 — plot should succeed."""
    out = tmp_path / "out.png"
    result = run_calc("plot", "x * x", "--output", str(out))
    assert result.returncode == 0


def test_plot_custom_domain(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "x", "--xmin", "0", "--xmax", "1", "--output", str(out))
    assert result.returncode == 0


# --- PNG pixel sampling: verify curve placement ---

def test_png_curve_pixel_near_origin(tmp_path):
    """For y=x, the pixel at the image centre should be near the curve colour."""
    out = tmp_path / "out.png"
    w, h = 200, 200
    run_calc("plot", "x", "--xmin", "-1", "--xmax", "1",
             "--width", str(w), "--height", str(h), "--output", str(out))
    # For y=x over [-1,1] with 10% padding, the curve passes through (0,0)
    # which maps to approximately the centre of the image.
    # Check a 5-pixel neighbourhood around the centre for a non-white pixel.
    cx, cy = w // 2, h // 2
    found_non_white = False
    for dx in range(-5, 6):
        for dy in range(-5, 6):
            col, row = cx + dx, cy + dy
            if 0 <= col < w and 0 <= row < h:
                r, g, b = read_png_pixel(out, col, row)
                if (r, g, b) != (255, 255, 255):
                    found_non_white = True
    assert found_non_white, "Expected curve pixels near the image centre"


# --- Error cases: exit code 1 + correct stderr ---

def test_invalid_domain_bounds(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "x", "--xmin", "5", "--xmax", "1", "--output", str(out))
    assert result.returncode == 1
    assert "xmin must be less than xmax" in result.stderr


def test_equal_domain_bounds(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "x", "--xmin", "0", "--xmax", "0", "--output", str(out))
    assert result.returncode == 1
    assert "xmin must be less than xmax" in result.stderr


def test_unsupported_format(tmp_path):
    out = tmp_path / "out.bmp"
    result = run_calc("plot", "x", "--output", str(out))
    assert result.returncode == 1
    assert "unsupported format" in result.stderr
    assert ".bmp" in result.stderr
    assert "use .png or .svg" in result.stderr


def test_undefined_function(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "foo(x)", "--output", str(out))
    assert result.returncode == 1
    assert "undefined function: foo" in result.stderr


def test_undefined_variable(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "x + y", "--output", str(out))
    assert result.returncode == 1
    assert "undefined variable: y" in result.stderr


def test_domain_empty(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "sqrt(x)", "--xmin", "-10", "--xmax", "-1",
                      "--output", str(out))
    assert result.returncode == 1
    assert "expression undefined over entire domain" in result.stderr


def test_parse_error(tmp_path):
    out = tmp_path / "out.png"
    result = run_calc("plot", "x +", "--output", str(out))
    assert result.returncode == 1
    assert "error:" in result.stderr


def test_output_not_writable(tmp_path):
    # Use a path inside a non-existent directory
    out = tmp_path / "no_such_dir" / "out.png"
    result = run_calc("plot", "x", "--output", str(out))
    assert result.returncode == 1
    assert "cannot write output" in result.stderr


# --- Legacy path unaffected ---

def test_legacy_path_still_works():
    result = run_calc("2 + 3")
    assert result.returncode == 0
    assert "5" in result.stdout
