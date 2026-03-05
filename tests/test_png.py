import struct
import zlib

import pytest

from calc.png import DEFAULT_HEIGHT, DEFAULT_WIDTH, encode_png


def _decompress_idat(png_bytes: bytes) -> bytes:
    """Extract and decompress all IDAT chunk payloads from a PNG byte string."""
    pos = 8  # skip PNG signature
    idat_payload = bytearray()
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        tag = png_bytes[pos + 4:pos + 8]
        data = png_bytes[pos + 8:pos + 8 + length]
        if tag == b"IDAT":
            idat_payload.extend(data)
        elif tag == b"IEND":
            break
        pos += 4 + 4 + length + 4
    return zlib.decompress(bytes(idat_payload))


def test_returns_bytes():
    result = encode_png(1, 1, [(255, 255, 255)])
    assert isinstance(result, bytes)


def test_png_signature():
    result = encode_png(1, 1, [(255, 255, 255)])
    assert result[:8] == b"\x89PNG\r\n\x1a\n"


def test_ihdr_dimensions_1x1():
    result = encode_png(1, 1, [(255, 255, 255)])
    w, h = struct.unpack(">II", result[16:24])
    assert (w, h) == (1, 1)


def test_ihdr_dimensions_default():
    pixels = [(255, 255, 255)] * (DEFAULT_WIDTH * DEFAULT_HEIGHT)
    result = encode_png(DEFAULT_WIDTH, DEFAULT_HEIGHT, pixels)
    w, h = struct.unpack(">II", result[16:24])
    assert (w, h) == (DEFAULT_WIDTH, DEFAULT_HEIGHT)


def test_ihdr_colour_type_is_rgb():
    result = encode_png(1, 1, [(0, 0, 0)])
    # IHDR data starts at byte 16; colour type is at offset 9 within IHDR data = byte 25
    assert result[25] == 2


def test_iend_present():
    result = encode_png(1, 1, [(0, 0, 0)])
    assert b"IEND" in result[-20:]


def test_pixel_value_roundtrip():
    pixels = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]  # red, green, blue
    result = encode_png(3, 1, pixels)
    raw = _decompress_idat(result)
    # Row 0: filter byte + 9 RGB bytes
    assert raw[0] == 0x00           # filter type None
    assert raw[1:4] == bytes([255, 0, 0])   # red
    assert raw[4:7] == bytes([0, 255, 0])   # green
    assert raw[7:10] == bytes([0, 0, 255])  # blue


def test_all_white_image():
    pixels = [(255, 255, 255)] * (DEFAULT_WIDTH * DEFAULT_HEIGHT)
    result = encode_png(DEFAULT_WIDTH, DEFAULT_HEIGHT, pixels)
    raw = _decompress_idat(result)
    stride = 1 + DEFAULT_WIDTH * 3
    assert raw[0] == 0x00           # first row filter byte
    assert all(b == 255 for b in raw[1:stride])  # all RGB bytes in first row


def test_all_black_image():
    pixels = [(0, 0, 0)] * (DEFAULT_WIDTH * DEFAULT_HEIGHT)
    result = encode_png(DEFAULT_WIDTH, DEFAULT_HEIGHT, pixels)
    raw = _decompress_idat(result)
    stride = 1 + DEFAULT_WIDTH * 3
    # Skip filter bytes; all RGB bytes should be 0
    rgb_bytes = bytearray()
    for row in range(DEFAULT_HEIGHT):
        rgb_bytes.extend(raw[row * stride + 1:(row + 1) * stride])
    assert all(b == 0 for b in rgb_bytes)


def test_assertion_width_zero():
    with pytest.raises(AssertionError):
        encode_png(0, 1, [])


def test_assertion_height_zero():
    with pytest.raises(AssertionError):
        encode_png(1, 0, [])


def test_default_constants():
    assert DEFAULT_WIDTH == 800
    assert DEFAULT_HEIGHT == 600
