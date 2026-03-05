from __future__ import annotations

from pathlib import Path
from typing import Protocol

from calc.plotter import Scene


class Renderer(Protocol):
    def render(self, scene: Scene, output: Path) -> None:
        """Write the rendered image to output. Raises OSError on write failure."""
        ...


def get_renderer(output: Path) -> Renderer:
    """Return the appropriate renderer based on the output file suffix.

    Raises:
        ImportError: never (both renderers are stdlib-only).
        KeyError: never (caller validates suffix before calling this).
    """
    from calc.renderer.png import PngRenderer
    from calc.renderer.svg import SvgRenderer

    dispatch = {
        ".png": PngRenderer,
        ".svg": SvgRenderer,
    }
    return dispatch[output.suffix]()
