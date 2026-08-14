"""Цеховой чертёж: то, что кладут на верстак рядом с пилой.

Отличается от превью не «стилем», а назначением. Превью показывает, какой
доска будет; чертёж отвечает на другие вопросы: где какая порода, какого доска
размера и на каком шаге всё это происходит. Поэтому здесь есть размерные линии,
условные обозначения и штамп, и нет ни одного цветного пикселя.

Печать — офисный лазерник. Отсюда белая заливка и чёрные линии: серые заливки
на нём растрируются в точки, точки съедают буквы поверх них, а породы всё равно
не различаются. Породу называет **буква**, и это единственное, что её называет.

Сам рисунок доски берётся у обычного рисовальщика с записью `BLUEPRINT`
из `STYLES` — новых веток в `svg.py` из-за чертежа не появилось, там только
поле `label`, устроенное как давно существующее `background`. Всё, что вокруг
рисунка, живёт здесь.
"""

from dataclasses import dataclass, replace

from ..core.piece import Part
from ..core.species import Species
from ..core.units import MILLIMETRES, Units
from .canvas import document, element, escape, num, wrap
from .style import BLUEPRINT, RenderOptions
from .svg import FONT, board_body, board_canvas, board_cells, species_letters

MARGIN_MM = 26.0
"""Поле вокруг доски: в нём живут размерные линии. Меньше — цифры лезут на кромку."""

TICK_MM = 3.0
OFFSET_MM = 11.0
"""На сколько размерная линия отступает от кромки доски."""

FOOTER_PX = 78.0
"""Высота штампа под рисунком, в пикселях документа. В пикселях, а не в
миллиметрах доски: штамп — часть листа, а не часть доски, и от масштаба
рисунка его высота зависеть не должна."""

INK = "#000000"
HAIRLINE_MM = 0.25


@dataclass(frozen=True, slots=True)
class Sheet:
    """Что написать в штампе чертежа."""

    title: str = "Торцевая разделочная доска"
    step: int | None = None
    """Номер шага в инструкции. `None` — чертёж не про шаг, а про доску целиком."""
    note: str = ""

    @property
    def heading(self) -> str:
        """Заголовок штампа: шаг и его название одной строкой."""
        return f"Шаг {self.step}. {self.title}" if self.step is not None else self.title


def _text(
    body: str, x: float, y: float, size: float, anchor: str = "start", weight: str = ""
) -> str:
    return wrap(
        "text",
        escape(body),
        x=num(x),
        y=num(y),
        font_size=num(size),
        text_anchor=anchor,
        font_weight=weight or None,
    )


def _dimension(
    frame: object,
    start: tuple[float, float],
    end: tuple[float, float],
    caption: str,
    horizontal: bool,
) -> str:
    """Размерная линия с засечками и подписью посередине."""
    x1, y1 = frame.x(start[0]), frame.y(start[1])  # type: ignore[attr-defined]
    x2, y2 = frame.x(end[0]), frame.y(end[1])  # type: ignore[attr-defined]
    tick = frame.px(TICK_MM)  # type: ignore[attr-defined]

    if horizontal:
        ticks = (
            f"M{num(x1)} {num(y1 - tick)}V{num(y1 + tick)}"
            f"M{num(x2)} {num(y2 - tick)}V{num(y2 + tick)}"
        )
        label = _text(caption, (x1 + x2) / 2, y1 - tick - 4.0, 11.0, "middle")
    else:
        ticks = (
            f"M{num(x1 - tick)} {num(y1)}H{num(x1 + tick)}"
            f"M{num(x2 - tick)} {num(y2)}H{num(x2 + tick)}"
        )
        label = wrap(
            "g",
            _text(caption, 0.0, 0.0, 11.0, "middle"),
            transform=(
                f"translate({num(x1 - tick - 5.0)} {num((y1 + y2) / 2)}) rotate(-90)"
            ),
        )

    line = element(
        "path",
        d=f"M{num(x1)} {num(y1)}L{num(x2)} {num(y2)}{ticks}",
        fill="none",
        stroke=INK,
        stroke_width=num(frame.px(HAIRLINE_MM)),  # type: ignore[attr-defined]
    )
    return line + label


def _legend(
    letters: dict[str, str],
    catalogue: dict[str, Species],
    x: float,
    y: float,
) -> str:
    """Условные обозначения: буква — порода. Без них чертёж нечитаем."""
    parts = []
    for key, letter in sorted(letters.items(), key=lambda item: item[1]):
        name = catalogue[key].name if key in catalogue else key
        parts.append(f"{letter} — {name}")
    return _text("   ".join(parts), x, y, 11.0)


def render_blueprint(
    board: Part,
    catalogue: dict[str, Species],
    options: RenderOptions | None = None,
    sheet: Sheet | None = None,
    units: Units = MILLIMETRES,
) -> str:
    """Чертёж доски: рисунок, размеры, обозначения пород и штамп."""
    sheet = sheet or Sheet()
    options = replace(options or RenderOptions(), style=BLUEPRINT, margin_mm=MARGIN_MM)

    canvas = board_canvas(board, options)
    cells = board_cells(board, catalogue, options.style)
    body = board_body(cells, canvas, options, "")

    xmin, ymin, xmax, ymax = board.bounds
    frame = canvas.frame
    body.append(
        wrap(
            "g",
            _dimension(
                frame,
                (xmin, ymin - OFFSET_MM),
                (xmax, ymin - OFFSET_MM),
                units.format(xmax - xmin),
                horizontal=True,
            )
            + _dimension(
                frame,
                (xmin - OFFSET_MM, ymin),
                (xmin - OFFSET_MM, ymax),
                units.format(ymax - ymin),
                horizontal=False,
            ),
            fill=INK,
            font_family=FONT,
        )
    )

    letters = species_letters(cell.piece.species for cell in cells)
    top = canvas.height_px
    footer = [
        element(
            "path",
            d=f"M0 {num(top)}H{num(canvas.width_px)}",
            stroke=INK,
            stroke_width="1",
            fill="none",
        ),
        _text(sheet.heading, 10.0, top + 22.0, 13.0, weight="bold"),
        _text(
            f"Габарит: {units.format(xmax - xmin)} × {units.format(ymax - ymin)} × "
            f"{units.format(board.thickness_mm)}. Ячеек: {len(board.pieces)}",
            10.0,
            top + 40.0,
            11.0,
        ),
        _legend(letters, catalogue, 10.0, top + 58.0),
    ]
    if sheet.note:
        footer.append(_text(sheet.note, 10.0, top + 74.0, 10.0))

    body.append(wrap("g", "".join(footer), fill=INK, font_family=FONT))
    body.insert(
        0,
        element(
            "rect",
            x="0",
            y=num(top),
            width=num(canvas.width_px),
            height=num(FOOTER_PX),
            fill="#ffffff",
        ),
    )

    return document(
        canvas.width_px, canvas.height_px + FOOTER_PX, body, (), options.digits
    )


__all__ = ["FOOTER_PX", "MARGIN_MM", "Sheet", "render_blueprint"]
