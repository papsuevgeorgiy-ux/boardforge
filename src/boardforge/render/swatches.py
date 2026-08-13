"""Лист образцов пород: торцевые квадраты с подписями.

Нужен ровно для одного — сверить цвета глазами и поправить `species.yaml`.
Поэтому на листе видно и породу, и её ключ, и характерную ширину кольца,
и пометку «не сверено» у тех, чью палитру ещё никто не проверял.
"""

from dataclasses import replace

from shapely.geometry import box

from ..core.piece import Origin, Piece
from ..core.species import Species
from .canvas import Frame, document, element, escape, num, wrap
from .style import PREVIEW, RenderOptions
from .svg import cell_elements, prepare_cell

SWATCH_MM = 62.0
GAP_MM = 10.0
LABEL_MM = 25.0
LINE_MM = 4.6
COLUMNS = 4

_LABEL_COLOR = "#2a211a"
_WARNING_COLOR = "#a8391a"
_SHEET_COLOR = "#faf7f1"
_FONT = "'DejaVu Sans', 'Segoe UI', sans-serif"


def _swatch_piece(key: str, index: int) -> Piece:
    """Квадрат торца. Номер породы играет роль номера рейки: у каждой свой
    разворот колец, но при том же справочнике — всегда тот же самый."""
    return Piece(box(0.0, 0.0, SWATCH_MM, SWATCH_MM), Origin("swatch", index, 0.0, key))


def render_swatches(
    catalogue: dict[str, Species],
    options: RenderOptions | None = None,
    columns: int = COLUMNS,
) -> str:
    """Нарисовать лист образцов. Порядок пород — как в справочнике."""
    if columns < 1:
        raise ValueError("на листе должен быть хотя бы один столбец")
    options = replace(options or RenderOptions(scale=3.0), style=PREVIEW)

    items = list(catalogue.items())
    rows = -(-len(items) // columns)
    cell_w = SWATCH_MM + GAP_MM
    cell_h = SWATCH_MM + LABEL_MM + GAP_MM
    width_mm = columns * cell_w - GAP_MM
    height_mm = rows * cell_h - GAP_MM

    frame = Frame(0.0, height_mm, options.margin_mm, options.scale, options.digits)
    width_px = (width_mm + 2 * options.margin_mm) * options.scale
    height_px = (height_mm + 2 * options.margin_mm) * options.scale

    defs: list[str] = []
    body: list[str] = [
        element(
            "rect",
            x="0",
            y="0",
            width=num(width_px, options.digits),
            height=num(height_px, options.digits),
            fill=_SHEET_COLOR,
        )
    ]

    for index, (key, species) in enumerate(items):
        column, row = index % columns, index // columns
        left = column * cell_w
        top = height_mm - row * cell_h
        piece = _swatch_piece(key, index)
        placed = Piece(box(left, top - SWATCH_MM, left + SWATCH_MM, top), piece.origin)
        cell = prepare_cell(placed, species.palette)
        cell_defs, cell_body = cell_elements(f"swatch{index}", cell, frame, options)
        defs.extend(cell_defs)
        body.extend(cell_body)
        body.append(
            element(
                "rect",
                x=num(frame.x(left), options.digits),
                y=num(frame.y(top), options.digits),
                width=num(frame.px(SWATCH_MM), options.digits),
                height=num(frame.px(SWATCH_MM), options.digits),
                fill="none",
                stroke=_LABEL_COLOR,
                stroke_width=num(frame.px(0.4), options.digits),
            )
        )
        body.extend(_labels(species, left, top, frame, options))

    return document(width_px, height_px, body, defs, options.digits)


def _text(
    content: str, x_px: float, y_px: float, size_px: float, color: str, digits: int
) -> str:
    return wrap(
        "text",
        escape(content),
        x=num(x_px, digits),
        y=num(y_px, digits),
        fill=color,
        font_family=_FONT,
        font_size=num(size_px, digits),
    )


def _labels(
    species: Species, left: float, top: float, frame: Frame, options: RenderOptions
) -> list[str]:
    """Подпись под образцом: по строке на смысл, чтобы не залезать в соседний."""
    palette = species.palette
    base_x = frame.x(left)
    baseline = frame.y(top - SWATCH_MM) + frame.px(4.6)

    rows = [
        (species.name, 4.2, _LABEL_COLOR),
        (f"{species.key} · {palette.base}", 2.9, _LABEL_COLOR),
        (
            f"кольцо {palette.ring_width_mm:g} мм · поздняя "
            f"{palette.latewood_fraction:g} · контраст {palette.ring_contrast:g}",
            2.8,
            _LABEL_COLOR,
        ),
        (
            f"лучи {palette.ray_width_mm:g} мм · контраст {palette.ray_contrast:g}",
            2.8,
            _LABEL_COLOR,
        ),
    ]
    if not palette.verified:
        rows.append(("палитра не сверена", 2.9, _WARNING_COLOR))

    return [
        _text(
            content,
            base_x,
            baseline + frame.px(LINE_MM) * index,
            frame.px(size),
            color,
            options.digits,
        )
        for index, (content, size, color) in enumerate(rows)
    ]
