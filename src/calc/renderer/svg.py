from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from calc.plotter import Scene


class SvgRenderer:
    """Render a Scene to an SVG file using xml.etree.ElementTree."""

    BG_COLOR = "white"
    AXIS_COLOR = "#b4b4b4"
    CURVE_COLOR = "#1f77b4"
    TICK_LEN = 6  # pixels

    def render(self, scene: Scene, output: Path) -> None:
        svg = ET.Element("svg", {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(scene.width),
            "height": str(scene.height),
            "viewBox": f"0 0 {scene.width} {scene.height}",
        })

        # Background rectangle
        ET.SubElement(svg, "rect", {
            "width": str(scene.width),
            "height": str(scene.height),
            "fill": self.BG_COLOR,
        })

        def wx_to_px(wx: float) -> float:
            return (wx - scene.x_min) / (scene.x_max - scene.x_min) * scene.width

        def wy_to_py(wy: float) -> float:
            return (scene.y_max - wy) / (scene.y_max - scene.y_min) * scene.height

        # x-axis
        if scene.y_min <= 0 <= scene.y_max:
            py0 = wy_to_py(0.0)
            ET.SubElement(svg, "line", {
                "x1": "0", "y1": f"{py0:.2f}",
                "x2": str(scene.width), "y2": f"{py0:.2f}",
                "stroke": self.AXIS_COLOR, "stroke-width": "1",
            })

        # y-axis
        if scene.x_min <= 0 <= scene.x_max:
            px0 = wx_to_px(0.0)
            ET.SubElement(svg, "line", {
                "x1": f"{px0:.2f}", "y1": "0",
                "x2": f"{px0:.2f}", "y2": str(scene.height),
                "stroke": self.AXIS_COLOR, "stroke-width": "1",
            })

        # x-tick marks
        py_axis = wy_to_py(0.0) if scene.y_min <= 0 <= scene.y_max else scene.height
        for wx, label in scene.x_ticks:
            px = wx_to_px(wx)
            ET.SubElement(svg, "line", {
                "x1": f"{px:.2f}", "y1": f"{py_axis - self.TICK_LEN / 2:.2f}",
                "x2": f"{px:.2f}", "y2": f"{py_axis + self.TICK_LEN / 2:.2f}",
                "stroke": self.AXIS_COLOR, "stroke-width": "1",
            })
            ET.SubElement(svg, "text", {
                "x": f"{px:.2f}", "y": f"{py_axis + self.TICK_LEN + 12:.2f}",
                "text-anchor": "middle", "font-size": "10",
                "fill": "#555",
            }).text = label

        # y-tick marks
        px_axis = wx_to_px(0.0) if scene.x_min <= 0 <= scene.x_max else 0.0
        for wy, label in scene.y_ticks:
            py = wy_to_py(wy)
            ET.SubElement(svg, "line", {
                "x1": f"{px_axis - self.TICK_LEN / 2:.2f}", "y1": f"{py:.2f}",
                "x2": f"{px_axis + self.TICK_LEN / 2:.2f}", "y2": f"{py:.2f}",
                "stroke": self.AXIS_COLOR, "stroke-width": "1",
            })
            ET.SubElement(svg, "text", {
                "x": f"{px_axis - self.TICK_LEN - 4:.2f}", "y": f"{py + 4:.2f}",
                "text-anchor": "end", "font-size": "10",
                "fill": "#555",
            }).text = label

        # Curve segments as <polyline> elements
        for segment in scene.segments:
            if len(segment) < 2:
                continue
            points = " ".join(
                f"{wx_to_px(wx):.2f},{wy_to_py(wy):.2f}"
                for wx, wy in segment
            )
            ET.SubElement(svg, "polyline", {
                "points": points,
                "fill": "none",
                "stroke": self.CURVE_COLOR,
                "stroke-width": "1.5",
            })

        output.write_text(
            ET.tostring(svg, encoding="unicode", xml_declaration=False),
            encoding="utf-8",
        )
