"""Свой SVG-writer: числа, кадр, элементы, документ. Без сторонних библиотек.

Один и тот же вектор идёт на экран, в PDF и на печать 1:1, поэтому здесь нет
ничего растрового и ничего недетерминированного: координаты форматируются
с фиксированной точностью, порядок элементов задаёт вызывающий, словари
атрибутов обходятся в порядке вставки.
"""

from collections.abc import Iterable
from dataclasses import dataclass

XMLNS = "http://www.w3.org/2000/svg"

DIGITS = 2
"""Знаков после запятой в координатах. При 2 знаках пиксель делится на сотые —
заведомо мельче, чем видит глаз и печатает лазерник."""


def num(value: float, digits: int = DIGITS) -> str:
    """Число для SVG: без хвостовых нулей и без минус-нуля."""
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-", "-0") else text


def escape(text: str) -> str:
    """Текст внутри разметки: экранируется только то, что её ломает."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _attributes(attrs: dict[str, object]) -> str:
    parts = []
    for key, value in attrs.items():
        if value is None:
            continue
        name = key.rstrip("_").replace("_", "-")
        parts.append(f' {name}="{value}"')
    return "".join(parts)


def element(tag: str, /, **attrs: object) -> str:
    """Самозакрывающийся элемент. `None` в атрибуте означает «не писать»."""
    return f"<{tag}{_attributes(attrs)}/>"


def wrap(tag: str, content: str, /, **attrs: object) -> str:
    """Элемент с содержимым."""
    return f"<{tag}{_attributes(attrs)}>{content}</{tag}>"


@dataclass(frozen=True, slots=True)
class Frame:
    """Перевод миллиметров модели в пиксели документа.

    Y модели растёт вверх, Y документа — вниз, поэтому кадр переворачивает ось
    здесь, а не преобразованием в SVG: иначе подписи на чертеже пришлось бы
    переворачивать обратно каждую по отдельности.
    """

    xmin_mm: float
    ymax_mm: float
    margin_mm: float
    scale: float
    digits: int = DIGITS

    def x(self, mm: float) -> float:
        """Координата X документа в пикселях."""
        return (mm - self.xmin_mm + self.margin_mm) * self.scale

    def y(self, mm: float) -> float:
        """Координата Y документа в пикселях."""
        return (self.ymax_mm - mm + self.margin_mm) * self.scale

    def px(self, mm: float) -> float:
        """Длина в пикселях."""
        return mm * self.scale

    def point(self, x_mm: float, y_mm: float) -> str:
        """Точка для атрибута `points`."""
        return f"{num(self.x(x_mm), self.digits)},{num(self.y(y_mm), self.digits)}"

    def moveto(self, x_mm: float, y_mm: float) -> str:
        """Команда `M` пути."""
        return f"M{num(self.x(x_mm), self.digits)} {num(self.y(y_mm), self.digits)}"

    def lineto(self, x_mm: float, y_mm: float) -> str:
        """Команда `L` пути."""
        return f"L{num(self.x(x_mm), self.digits)} {num(self.y(y_mm), self.digits)}"


def document(
    width_px: float,
    height_px: float,
    body: Iterable[str],
    defs: Iterable[str] = (),
    digits: int = DIGITS,
) -> str:
    """Собрать документ. Каждый элемент верхнего уровня — своя строка."""
    width = num(width_px, digits)
    height = num(height_px, digits)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="{XMLNS}" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
    ]
    definitions = list(defs)
    if definitions:
        lines.append(wrap("defs", "".join(definitions)))
    lines.extend(body)
    lines.append("</svg>")
    return "\n".join(lines) + "\n"
