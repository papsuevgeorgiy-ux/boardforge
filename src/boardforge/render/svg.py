"""Рендер доски в SVG. Вход — деталь из `run()`, выход — строка.

Рендер детерминирован: ячейки обходятся в устойчивом порядке, координаты
форматируются с фиксированной точностью, текстура берёт сид из происхождения
ячейки. Один и тот же проект даёт побайтово одинаковый файл.
"""

import math
from dataclasses import dataclass

from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..core.piece import Part, Piece
from ..core.species import Palette, Species
from . import texture
from .canvas import Frame, document, element, num, wrap
from .style import RenderOptions, RenderStyle, Stroke

MIN_RING_STROKE_PX = 0.4
MIN_RAY_STROKE_PX = 0.25

REFERENCE_LATEWOOD_FRACTION = 0.30
NARROW_LATEWOOD_GAIN = 0.6
"""Насколько узкая поздняя зона выигрывает в темноте.

Одного контраста мало: у венге тёмная прослойка втрое уже, чем у дуба, и при
равной непрозрачности она просто теряется. Физически так и есть — чем тоньше
зона, тем плотнее в ней древесина и тем темнее она читается, — поэтому узкая
зона получает надбавку к непрозрачности, а широкая скидку.
"""


def _latewood_opacity(palette: Palette) -> float:
    """Непрозрачность штриха поздней зоны с поправкой на её ширину."""
    gain = (REFERENCE_LATEWOOD_FRACTION / palette.latewood_fraction) ** (
        NARROW_LATEWOOD_GAIN
    )
    return min(1.0, palette.ring_contrast * gain)


class RenderError(ValueError):
    """Доску нельзя нарисовать."""


@dataclass(frozen=True, slots=True)
class Cell:
    """Ячейка, подготовленная к рисованию: полигон, палитра и её круг.

    `radius_mm` — радиус круга, накрывающего ячейку. По нему обрезаются кольца:
    рисовать окружность целиком, когда от неё видно дугу в палец, незачем.
    """

    piece: Piece
    palette: Palette
    center_x: float
    center_y: float
    radius_mm: float
    size_mm: float
    corners: tuple[tuple[float, float], ...]
    """Вершины контура. Достаются из `shapely` один раз на ячейку: заливка, шов
    и обрезка текстуры рисуют один и тот же контур, а обход координат
    геометрии — самая дорогая часть быстрого слоя."""


def prepare_cell(piece: Piece, palette: Palette) -> Cell:
    """Подготовить ячейку к рисованию."""
    xmin, ymin, xmax, ymax = piece.polygon.bounds
    width, height = xmax - xmin, ymax - ymin
    return Cell(
        piece=piece,
        palette=palette,
        center_x=(xmin + xmax) / 2.0,
        center_y=(ymin + ymax) / 2.0,
        radius_mm=math.hypot(width, height) / 2.0,
        size_mm=min(width, height),
        corners=_corners(piece.polygon.exterior),
    )


def _corners(ring) -> tuple[tuple[float, float], ...]:
    """Вершины контура без повторной замыкающей точки."""
    coords = list(ring.coords)
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return tuple(coords)


def _points(corners: tuple[tuple[float, float], ...], frame: Frame) -> str:
    return " ".join(frame.point(x, y) for x, y in corners)


def _ring_path(corners: tuple[tuple[float, float], ...], frame: Frame) -> str:
    if not corners:
        return ""
    head = frame.moveto(*corners[0])
    tail = "".join(frame.lineto(x, y) for x, y in corners[1:])
    return f"{head}{tail}Z"


def _outline_path(polygon: Polygon, frame: Frame) -> str:
    """Контур произвольного полигона, включая дырки. Нужен только кромке доски."""
    return "".join(
        _ring_path(_corners(ring), frame)
        for ring in (polygon.exterior, *polygon.interiors)
    )


def _stroke_attrs(stroke: Stroke, frame: Frame, digits: int) -> dict[str, object]:
    return {
        "fill": "none",
        "stroke": stroke.color,
        "stroke_width": num(frame.px(stroke.width_mm), digits),
        "stroke_opacity": None if stroke.opacity >= 1.0 else num(stroke.opacity, 3),
    }


def _arc_to(
    frame: Frame, point: tuple[float, float], radius_px: str, large: int, digits: int
) -> str:
    """Команда `A`. Обход против часовой в модели — по часовой в документе,
    потому что кадр переворачивает Y; отсюда постоянный флаг направления 0."""
    x = num(frame.x(point[0]), digits)
    y = num(frame.y(point[1]), digits)
    return f"A{radius_px} {radius_px} 0 {large} 0 {x} {y}"


def _rings(cell: Cell, field: texture.RingField, frame: Frame, digits: int) -> str:
    """Дуги колец одним путём: общие атрибуты пишутся один раз на ячейку."""
    arcs = texture.ring_arcs(field, cell.radius_mm)
    if not arcs or cell.palette.ring_contrast <= 0.0:
        return ""

    pith_x = cell.center_x + field.pith_x
    pith_y = cell.center_y + field.pith_y

    def at(radius: float, angle_deg: float) -> tuple[float, float]:
        radians = math.radians(angle_deg)
        return (pith_x + radius * math.cos(radians), pith_y + radius * math.sin(radians))

    commands = []
    for arc in arcs:
        radius_px = num(frame.px(arc.radius_mm), digits)
        start = at(arc.radius_mm, arc.start_deg)
        head = frame.moveto(*start)
        if arc.full:
            opposite = at(arc.radius_mm, arc.start_deg + 180.0)
            commands.append(
                head
                + _arc_to(frame, opposite, radius_px, 1, digits)
                + _arc_to(frame, start, radius_px, 1, digits)
            )
            continue
        end = at(arc.radius_mm, arc.start_deg + arc.span_deg)
        large = 1 if arc.span_deg > 180.0 else 0
        commands.append(head + _arc_to(frame, end, radius_px, large, digits))

    width_px = frame.px(cell.palette.latewood_width_mm)
    return element(
        "path",
        d="".join(commands),
        fill="none",
        stroke=cell.palette.latewood,
        stroke_width=num(max(width_px, MIN_RING_STROKE_PX), digits),
        stroke_opacity=num(_latewood_opacity(cell.palette), 3),
        stroke_linecap="round",
    )


def _rays(cell: Cell, field: texture.RingField, frame: Frame, digits: int) -> str:
    """Сердцевинные лучи — поперёк колец, по параметрам породы.

    Толщина у лучей разная, а `stroke-width` — атрибут всего пути, поэтому лучи
    собираются в пути по толщинам: их три, а не по одному на луч.
    """
    if cell.palette.ray_contrast <= 0.0:
        return ""
    lines = texture.ray_lines(field, cell.radius_mm, cell.palette.ray_width_mm)
    if not lines:
        return ""

    groups: dict[str, list[str]] = {}
    for line in lines:
        width = num(max(frame.px(line.width_mm), MIN_RAY_STROKE_PX), digits)
        commands = groups.setdefault(width, [])
        commands.append(frame.moveto(cell.center_x + line.x1, cell.center_y + line.y1))
        commands.append(frame.lineto(cell.center_x + line.x2, cell.center_y + line.y2))

    return "".join(
        element(
            "path",
            d="".join(commands),
            fill="none",
            stroke=cell.palette.ray,
            stroke_width=width,
            stroke_opacity=num(cell.palette.ray_contrast, 3),
        )
        for width, commands in sorted(groups.items())
    )


def is_textured(cell: Cell, frame: Frame, options: RenderOptions) -> bool:
    """Рисуется ли у этой ячейки текстура.

    Текстура появляется, только если стиль её разрешает и ячейка достаточно
    крупная на экране. Иначе остаётся заливка основным тоном: узор читается,
    а файл не пухнет от колец, которых всё равно не видно.
    """
    return options.style.texture and frame.px(cell.size_mm) >= options.min_texture_px


def cell_elements(
    key: str, cell: Cell, frame: Frame, options: RenderOptions
) -> tuple[list[str], list[str]]:
    """Ячейка целиком: заливка и текстура. Для листа образцов и одиночных вставок."""
    return [], [cell_fill(cell, frame, options) + cell_texture(key, cell, frame, options)]


def cell_fill(cell: Cell, frame: Frame, options: RenderOptions) -> str:
    """Заливка ячейки — быстрый слой.

    Ячейка, которой достанется текстура, заливается сразу ранней древесиной:
    кольца потом лягут поверх, и заливку не придётся класть второй раз. Иначе
    в документе оказалось бы по два полигона на ячейку — лишний вес и потерянный
    инвариант «полигонов столько же, сколько деталей».
    """
    tone = (
        cell.palette.earlywood if is_textured(cell, frame, options) else cell.palette.base
    )
    return element("polygon", points=_points(cell.corners, frame), fill=tone)


def cell_texture(key: str, cell: Cell, frame: Frame, options: RenderOptions) -> str:
    """Текстура ячейки вместе со своей обрезкой — самодостаточный кусок разметки.

    Только кольца и лучи: заливка уже нарисована быстрым слоем. `clipPath`
    кладётся рядом с группой, а не в `<defs>`, чтобы слой вставлялся в готовый
    документ одним фрагментом, не трогая его заголовок. Спецификация это
    разрешает — `clipPath` сам по себе не рисуется.
    """
    field = texture.ring_field(
        cell.piece.origin,
        cell.palette.ring_width_mm,
        cell.size_mm,
        cell.piece.orientation,
    )
    drawn = _rings(cell, field, frame, options.digits) + _rays(
        cell, field, frame, options.digits
    )
    if not drawn:
        return ""

    points = _points(cell.corners, frame)
    clip = wrap("clipPath", element("polygon", points=points), id=key)
    return clip + wrap("g", drawn, clip_path=f"url(#{key})")


def board_cells(
    board: Part, catalogue: dict[str, Species], style: RenderStyle
) -> list[Cell]:
    """Ячейки доски в устойчивом порядке: слева направо, снизу вверх.

    Порядок фиксируется здесь, а не берётся из `Part`: снапшот рендера не
    должен зависеть от того, в каком порядке склейка сложила детали.
    """
    ordered = sorted(
        board.pieces,
        key=lambda piece: (
            round(piece.polygon.bounds[0], 6),
            round(piece.polygon.bounds[1], 6),
            piece.origin.strip,
            round(piece.origin.offset_mm, 6),
        ),
    )
    cells = []
    for piece in ordered:
        species = catalogue.get(piece.species)
        if species is None:
            raise RenderError(f"породы {piece.species} нет в справочнике")
        cells.append(prepare_cell(piece, style.palette(species.palette)))
    return cells


TEXTURE_GROUP_ID = "texture"
"""Имя группы, в которую вставляется слой текстуры."""


@dataclass(frozen=True, slots=True)
class Canvas:
    """Кадр документа: где доска и какого размера лист."""

    frame: Frame
    width_px: float
    height_px: float


def board_canvas(board: Part, options: RenderOptions) -> Canvas:
    """Кадр под габарит доски с полем вокруг."""
    xmin, ymin, xmax, ymax = board.bounds
    return Canvas(
        frame=Frame(xmin, ymax, options.margin_mm, options.scale, options.digits),
        width_px=(xmax - xmin + 2 * options.margin_mm) * options.scale,
        height_px=(ymax - ymin + 2 * options.margin_mm) * options.scale,
    )


def _structure_body(
    cells: list[Cell], canvas: Canvas, options: RenderOptions, texture_layer: str
) -> list[str]:
    """Тело документа: заливки, слой текстуры, швы, кромка — в этом порядке.

    Текстура идёт под швами: шов клеевой, он поверх дерева, а не под ним.
    """
    style = options.style
    frame = canvas.frame
    body: list[str] = []
    if style.background is not None:
        body.append(
            element(
                "rect",
                x="0",
                y="0",
                width=num(canvas.width_px, options.digits),
                height=num(canvas.height_px, options.digits),
                fill=style.background,
            )
        )

    body.extend(cell_fill(cell, frame, options) for cell in cells)
    body.append(wrap("g", texture_layer, id=TEXTURE_GROUP_ID))
    body.append(
        element(
            "path",
            d="".join(_ring_path(cell.corners, frame) for cell in cells),
            stroke_linejoin="round",
            **_stroke_attrs(style.seam, frame, options.digits),
        )
    )

    edge = unary_union([cell.piece.polygon for cell in cells])
    body.append(
        element(
            "path",
            d="".join(
                _outline_path(shape, frame) for shape in getattr(edge, "geoms", (edge,))
            ),
            stroke_linejoin="round",
            **_stroke_attrs(style.edge, frame, options.digits),
        )
    )
    return body


def render_structure(
    board: Part,
    catalogue: dict[str, Species],
    options: RenderOptions | None = None,
) -> str:
    """Быстрый слой: заливка по породе, клеевые швы, кромка. Без текстуры.

    Этим слоем отвечает живое редактирование: узор, размеры и раскладка видны
    сразу, а кольца догоняют отдельным запросом. Внутри документа остаётся
    пустая группа `texture` — место, куда текстура встанет позже.

    Швы обязательны и здесь: без них доска выглядит нарисованной, а не
    склеенной из кусков дерева.
    """
    options = options or RenderOptions()
    canvas = board_canvas(board, options)
    cells = board_cells(board, catalogue, options.style)
    body = _structure_body(cells, canvas, options, "")
    return document(canvas.width_px, canvas.height_px, body, (), options.digits)


def render_texture(
    board: Part,
    catalogue: dict[str, Species],
    options: RenderOptions | None = None,
) -> str:
    """Дорогой слой: содержимое группы `texture` и ничего кроме.

    Возвращается кусок разметки, а не документ: он вставляется внутрь уже
    показанной структуры.
    """
    options = options or RenderOptions()
    canvas = board_canvas(board, options)
    cells = board_cells(board, catalogue, options.style)
    return "".join(
        cell_texture(f"cell{index}", cell, canvas.frame, options)
        for index, cell in enumerate(cells)
        if is_textured(cell, canvas.frame, options)
    )


def render_board(
    board: Part,
    catalogue: dict[str, Species],
    options: RenderOptions | None = None,
) -> str:
    """Полный документ: структура с уже вложенной текстурой.

    Ровно то же, что структура плюс текстура, но одним проходом по ячейкам —
    для файлов, PDF и печати, где ждать нечего и делить нечего.
    """
    options = options or RenderOptions()
    canvas = board_canvas(board, options)
    cells = board_cells(board, catalogue, options.style)
    layer = "".join(
        cell_texture(f"cell{index}", cell, canvas.frame, options)
        for index, cell in enumerate(cells)
        if is_textured(cell, canvas.frame, options)
    )
    body = _structure_body(cells, canvas, options, layer)
    return document(canvas.width_px, canvas.height_px, body, (), options.digits)


__all__ = [
    "TEXTURE_GROUP_ID",
    "Canvas",
    "Cell",
    "RenderError",
    "RenderOptions",
    "board_canvas",
    "board_cells",
    "render_board",
    "render_structure",
    "render_texture",
]
