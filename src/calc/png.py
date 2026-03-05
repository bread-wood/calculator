import struct
import zlib

DEFAULT_WIDTH: int = 800
DEFAULT_HEIGHT: int = 600


def encode_png(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int]],
) -> bytes:
    """Encode an 8-bit RGB pixel buffer as a PNG file.

    pixels: row-major list of (r, g, b) tuples, each channel 0-255.
    Returns a complete PNG file as bytes.
    """
    assert 1 <= width <= 65535 and 1 <= height <= 65535

    def _chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    raw = bytearray()
    for row_idx in range(height):
        raw += b"\x00"
        base = row_idx * width
        for col_idx in range(width):
            r, g, b = pixels[base + col_idx]
            raw += bytes([r, g, b])

    idat = _chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend
