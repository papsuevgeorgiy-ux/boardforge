"""Геометрия операций.

Одно соглашение на всю модель: детали укладываются поперёк по X, длина детали
идёт по Y. Рез — пересечение с семейством полос; угол отсчитывается от кромки
(оси Y), поэтому 90° даёт полосы, наложенные вдоль Y.

Отрезанная деталь живёт в собственных координатах: её габарит приводится
к началу отсчёта. Физически это честно — взятая в руки полоса не помнит,
из какого места щита она приехала.
"""

import math

from shapely.affinity import rotate, scale, translate
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import Polygon

from .ops import Strip
from .piece import Part, Piece
from .units import EPS

_BAND_MARGIN_MM = 1.0


def _polygons(geom: BaseGeometry) -> list[Polygon]:
    """Вытащить полигоны из результата пересечения, отбросив мусор."""
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if geom.area > EPS else []
    parts = getattr(geom, "geoms", ())
    result: list[Polygon] = []
    for item in parts:
        result.extend(_polygons(item))
    return result


def normalized(part: Part) -> Part:
    """Привести габарит детали к началу координат."""
    xmin, ymin, _, _ = part.bounds
    if abs(xmin) < EPS and abs(ymin) < EPS:
        return part
    moved = tuple(
        Piece(translate(piece.polygon, -xmin, -ymin), piece.species)
        for piece in part.pieces
    )
    return Part(moved, part.thickness_mm)


def glue(strips: tuple[Strip, ...], length_mm: float, thickness_mm: float) -> Part:
    """Склейка реек кромка-к-кромке: рейки по X, длина по Y."""
    pieces: list[Piece] = []
    cursor = 0.0
    for strip in strips:
        pieces.append(
            Piece(box(cursor, 0.0, cursor + strip.width_mm, length_mm), strip.species)
        )
        cursor += strip.width_mm
    return Part(tuple(pieces), thickness_mm)


def slice_part(part: Part, angle_deg: float, step_mm: float) -> tuple[list[Part], float]:
    """Разрезать деталь на полосы шага `step_mm` под углом `angle_deg` к кромке.

    Возвращает полосы и остаток — кусок короче шага, который уходит в отход.
    Неполная полоса деталью не считается: из неё не выйдет нужного размера.
    """
    turned = [
        Piece(rotate(piece.polygon, -angle_deg, origin=(0, 0)), piece.species)
        for piece in part.pieces
    ]
    boxes = [piece.polygon.bounds for piece in turned]
    xmin = min(b[0] for b in boxes)
    ymin = min(b[1] for b in boxes)
    xmax = max(b[2] for b in boxes)
    ymax = max(b[3] for b in boxes)

    span = xmax - xmin
    count = math.floor((span + EPS) / step_mm)
    if count < 1:
        raise ValueError(
            f"шаг реза {step_mm} мм больше детали ({span:.1f} мм) — резать нечего"
        )

    result: list[Part] = []
    for index in range(count):
        left = xmin + index * step_mm
        band = box(left, ymin - _BAND_MARGIN_MM, left + step_mm, ymax + _BAND_MARGIN_MM)
        pieces: list[Piece] = []
        for piece in turned:
            for polygon in _polygons(piece.polygon.intersection(band)):
                pieces.append(Piece(polygon, piece.species))
        if pieces:
            result.append(normalized(Part(tuple(pieces), part.thickness_mm)))

    return result, span - count * step_mm


def stand_on_end(part: Part, crosscut_step_mm: float) -> Part:
    """Поставить полосу на торец: шаг торцовки уходит в высоту доски.

    Полоса до операции: X — шаг торцовки (по нему идут волокна), Y — ширина
    щита, вне плоскости — толщина щита. Поворот вокруг длинной оси делает
    волокна вертикальными, и в плане на месте шага оказывается толщина.

    Преобразование сводится к масштабу по X только потому, что валидатор
    требует `StandOnEnd` сразу после торцовки: тогда каждая ячейка занимает
    весь шаг по X, и сжатие эквивалентно повороту.
    """
    factor = part.thickness_mm / crosscut_step_mm
    turned = tuple(
        Piece(
            scale(piece.polygon, xfact=factor, yfact=1.0, origin=(0, 0)),
            piece.species,
        )
        for piece in part.pieces
    )
    return normalized(Part(turned, crosscut_step_mm))


def assemble(
    parts: list[Part],
    order: tuple[int, ...],
    reversed_flags: tuple[bool, ...],
    offsets_mm: tuple[float, ...],
) -> Part:
    """Склеить детали в новый щит: порядок по X, разворот, сдвиг по Y."""
    if not order:
        raise ValueError("нечего склеивать")
    for index in order:
        if index >= len(parts):
            raise ValueError(
                f"деталь №{index} не существует: после реза их всего {len(parts)}"
            )

    thickness = parts[order[0]].thickness_mm
    pieces: list[Piece] = []
    cursor = 0.0
    for slot, index in enumerate(order):
        source = normalized(parts[index])
        if abs(source.thickness_mm - thickness) > EPS:
            raise ValueError("нельзя склеить детали разной толщины в один щит")
        if reversed_flags[slot]:
            _, _, xmax, ymax = source.bounds
            source = Part(
                tuple(
                    Piece(
                        rotate(piece.polygon, 180, origin=(xmax / 2, ymax / 2)),
                        piece.species,
                    )
                    for piece in source.pieces
                ),
                source.thickness_mm,
            )
        offset = offsets_mm[slot]
        pieces.extend(
            Piece(translate(piece.polygon, cursor, offset), piece.species)
            for piece in source.pieces
        )
        cursor += source.width_mm

    return normalized(Part(tuple(pieces), thickness))


def crop(part: Part, left: float, right: float, top: float, bottom: float) -> Part:
    """Обрезать щит по периметру, разрезая ячейки где придётся."""
    xmin, ymin, xmax, ymax = part.bounds
    window = box(xmin + left, ymin + bottom, xmax - right, ymax - top)
    if window.is_empty or window.area <= EPS:
        raise ValueError("обрезка не оставляет от щита ничего")

    pieces: list[Piece] = []
    for piece in part.pieces:
        for polygon in _polygons(piece.polygon.intersection(window)):
            pieces.append(Piece(polygon, piece.species))
    if not pieces:
        raise ValueError("обрезка не оставляет от щита ничего")
    return normalized(Part(tuple(pieces), part.thickness_mm))
