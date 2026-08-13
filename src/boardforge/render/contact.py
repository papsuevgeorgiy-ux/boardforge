"""Контактный лист: все демо-доски и лист пород на одной странице.

Нужен, чтобы после правки палитры или текстуры одним взглядом увидеть, что
изменилось везде сразу, а не открывать шесть файлов по очереди. Отсюда и
название: это контрольный отпечаток, а не украшение.

Собирается из уже готовых документов, а не рисуется заново: каждая доска
рендерится своим `render_board`, потом её содержимое вкладывается в общий лист
внутри `<svg>` со своим `viewBox`. Вложенный `svg` сам масштабирует содержимое
под отведённое место, поэтому пересчитывать координаты не приходится.
"""

import re
from dataclasses import dataclass

from ..core.species import Species
from .canvas import Frame, document, element, escape, num, wrap
from .style import RenderOptions
from .swatches import render_swatches

SHEET_WIDTH_MM = 420.0
MARGIN_MM = 12.0
GAP_MM = 10.0
TITLE_MM = 7.0
CAPTION_MM = 5.2

_SHEET_COLOR = "#faf7f1"
_INK = "#241c16"
_INK_SOFT = "#6b5c4d"
_FONT = "'DejaVu Sans', 'Segoe UI', sans-serif"

_SVG_OPEN = re.compile(r"^.*?<svg[^>]*viewBox=\"([^\"]+)\"[^>]*>", re.DOTALL)
_ID = re.compile(r'\bid="([^"]+)"')
_REF = re.compile(r"url\(#([^)]+)\)")


def _namespaced(body: str, prefix: str) -> str:
    """Развести идентификаторы вложенного документа.

    На общем листе документов несколько, а обрезка ячеек в каждом называется
    одинаково — `cell0`, `cell1`. В одном документе такие имена сталкиваются,
    и `clipPath` первой доски начинает обрезать текстуру всех остальных: доски
    выходят наполовину без колец, с торчащими за края штрихами.
    """
    body = _ID.sub(lambda match: f'id="{prefix}{match.group(1)}"', body)
    return _REF.sub(lambda match: f"url(#{prefix}{match.group(1)})", body)


@dataclass(frozen=True, slots=True)
class Sheet:
    """Готовый документ и его место на листе."""

    title: str
    body: str
    view_box: str
    ratio: float
    """Высота к ширине — по ней документу отводится место."""


def _split(svg: str) -> Sheet:
    """Разобрать готовый документ на `viewBox` и содержимое."""
    match = _SVG_OPEN.match(svg)
    if match is None:
        raise ValueError("это не документ SVG: нет viewBox")
    view_box = match.group(1)
    body = svg[match.end() : svg.rindex("</svg>")]
    _, _, width, height = (float(value) for value in view_box.split())
    return Sheet("", body, view_box, height / width if width else 1.0)


def sheet_of(title: str, svg: str, prefix: str = "") -> Sheet:
    """Именованный лист из готового документа с разведёнными идентификаторами."""
    parts = _split(svg)
    body = _namespaced(parts.body, prefix) if prefix else parts.body
    return Sheet(title, body, parts.view_box, parts.ratio)


def _text(content: str, x: float, y: float, size: float, color: str) -> str:
    return wrap(
        "text",
        escape(content),
        x=num(x),
        y=num(y),
        fill=color,
        font_family=_FONT,
        font_size=num(size),
    )


def render_contact_sheet(
    boards: dict[str, str],
    catalogue: dict[str, Species],
    options: RenderOptions | None = None,
) -> str:
    """Одна страница: доски сверху, лист пород снизу.

    `boards` — заголовок и готовый SVG каждой доски.
    """
    options = options or RenderOptions(scale=2.0)
    sources = [*boards.items(), ("Породы", render_swatches(catalogue, columns=6))]
    sheets = [
        sheet_of(title, svg, prefix=f"s{index}-")
        for index, (title, svg) in enumerate(sources)
    ]

    inner = SHEET_WIDTH_MM - 2 * MARGIN_MM
    scale = options.scale
    frame = Frame(0.0, 0.0, 0.0, scale, options.digits)

    body: list[str] = []
    cursor = MARGIN_MM
    for sheet in sheets:
        cursor += TITLE_MM
        body.append(
            _text(sheet.title, frame.px(MARGIN_MM), frame.px(cursor), frame.px(4.6), _INK)
        )
        cursor += CAPTION_MM
        height = inner * sheet.ratio
        body.append(
            wrap(
                "svg",
                sheet.body,
                x=num(frame.px(MARGIN_MM)),
                y=num(frame.px(cursor)),
                width=num(frame.px(inner)),
                height=num(frame.px(height)),
                viewBox=sheet.view_box,
                preserveAspectRatio="xMidYMin meet",
            )
        )
        cursor += height + GAP_MM

    total_height = cursor - GAP_MM + MARGIN_MM
    width_px = frame.px(SHEET_WIDTH_MM)
    height_px = frame.px(total_height)

    head = [
        element(
            "rect",
            x="0",
            y="0",
            width=num(width_px),
            height=num(height_px),
            fill=_SHEET_COLOR,
        ),
        _text(
            "BoardForge — контактный лист",
            frame.px(MARGIN_MM),
            frame.px(MARGIN_MM * 0.55),
            frame.px(5.4),
            _INK,
        ),
        _text(
            "доска — это программа, а не картинка",
            frame.px(MARGIN_MM),
            frame.px(MARGIN_MM * 0.95),
            frame.px(3.6),
            _INK_SOFT,
        ),
    ]
    return document(width_px, height_px, head + body, (), options.digits)
