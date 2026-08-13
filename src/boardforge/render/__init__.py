"""Рендер: SVG (2D) и меш для 3D."""

from .style import FLAT, PREVIEW, STYLES, RenderOptions, RenderStyle, style_by_name
from .svg import RenderError, render_board
from .swatches import render_swatches

__all__ = [
    "FLAT",
    "PREVIEW",
    "STYLES",
    "RenderError",
    "RenderOptions",
    "RenderStyle",
    "render_board",
    "render_swatches",
    "style_by_name",
]
