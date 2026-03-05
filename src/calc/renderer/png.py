from __future__ import annotations

from pathlib import Path

from calc.plotter import Scene
from calc.png import encode_png


class PngRenderer:
    """Render a Scene to an 8-bit RGB PNG file using the hand-rolled encoder."""

    # Colour palette (R, G, B)
    BG_COLOR = (255, 255, 255)      # white background
    AXIS_COLOR = (180, 180, 180)    # light grey axes
    TICK_COLOR = (180, 180, 180)    # same as axes
    CURVE_COLOR = (31, 119, 180)    # blue curve

    def render(self, scene: Scene, output: Path) -> None:
        pixels = [self.BG_COLOR] * (scene.width * scene.height)

        def world_to_pixel(wx: float, wy: float) -> tuple[int, int]:
            px = int((wx - scene.x_min) / (scene.x_max - scene.x_min) * scene.width)
            py = int((scene.y_max - wy) / (scene.y_max - scene.y_min) * scene.height)
            return px, py

        def set_pixel(px: int, py: int, color: tuple[int, int, int]) -> None:
            if 0 <= px < scene.width and 0 <= py < scene.height:
                pixels[py * scene.width + px] = color

        def draw_vline(px: int, color: tuple[int, int, int]) -> None:
            for py in range(scene.height):
                set_pixel(px, py, color)

        def draw_hline(py: int, color: tuple[int, int, int]) -> None:
            for px in range(scene.width):
                set_pixel(px, py, color)

        # Draw x-axis (y=0) if within y range
        if scene.y_min <= 0 <= scene.y_max:
            _, py0 = world_to_pixel(0.0, 0.0)
            draw_hline(py0, self.AXIS_COLOR)

        # Draw y-axis (x=0) if within x range
        if scene.x_min <= 0 <= scene.x_max:
            px0, _ = world_to_pixel(0.0, 0.0)
            draw_vline(px0, self.AXIS_COLOR)

        # Draw x tick marks (short vertical lines)
        tick_len = max(4, scene.height // 60)
        for wx, _ in scene.x_ticks:
            px, py_center = world_to_pixel(wx, 0.0)
            # Draw tick straddling the x-axis (or top of image if axis not visible)
            if scene.y_min <= 0 <= scene.y_max:
                for dy in range(-tick_len // 2, tick_len // 2 + 1):
                    set_pixel(px, py_center + dy, self.TICK_COLOR)
            else:
                py_top = scene.height - 1
                for dy in range(tick_len):
                    set_pixel(px, py_top - dy, self.TICK_COLOR)

        # Draw y tick marks (short horizontal lines)
        for wy, _ in scene.y_ticks:
            py, px_center = world_to_pixel(0.0, wy)[1], world_to_pixel(0.0, wy)[0]
            if scene.x_min <= 0 <= scene.x_max:
                for dx in range(-tick_len // 2, tick_len // 2 + 1):
                    set_pixel(px_center + dx, py, self.TICK_COLOR)
            else:
                px_left = 0
                for dx in range(tick_len):
                    set_pixel(px_left + dx, py, self.TICK_COLOR)

        # Draw curve segments as polylines (1px thick, no anti-aliasing)
        for segment in scene.segments:
            for i in range(len(segment) - 1):
                x0, y0 = segment[i]
                x1, y1 = segment[i + 1]
                px0, py0 = world_to_pixel(x0, y0)
                px1, py1 = world_to_pixel(x1, y1)
                self._draw_line(pixels, scene.width, scene.height,
                                px0, py0, px1, py1, self.CURVE_COLOR)

        output.write_bytes(encode_png(scene.width, scene.height, pixels))

    @staticmethod
    def _draw_line(
        pixels: list[tuple[int, int, int]],
        width: int, height: int,
        x0: int, y0: int, x1: int, y1: int,
        color: tuple[int, int, int],
    ) -> None:
        """Bresenham's line algorithm."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            if 0 <= x0 < width and 0 <= y0 < height:
                pixels[y0 * width + x0] = color
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
