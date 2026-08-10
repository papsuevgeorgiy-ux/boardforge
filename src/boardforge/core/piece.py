"""Заготовка: ячейки узора и деталь, из которой собирается доска."""

from dataclasses import dataclass

from shapely.geometry import Polygon

from .units import EPS


@dataclass(frozen=True, slots=True)
class Piece:
    """Ячейка узора: полигон в плоскости модели и порода."""

    polygon: Polygon
    species: str

    @property
    def area_mm2(self) -> float:
        """Площадь ячейки в плоскости модели."""
        return self.polygon.area


@dataclass(frozen=True, slots=True)
class Part:
    """Деталь: набор ячеек в собственных координатах плюс третье измерение.

    До `StandOnEnd` плоскость модели — пласть щита, `thickness_mm` — его
    толщина. После — план доски, `thickness_mm` — высота доски.
    """

    pieces: tuple[Piece, ...]
    thickness_mm: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "pieces", tuple(self.pieces))
        if not self.pieces:
            raise ValueError("деталь без единой ячейки")
        if self.thickness_mm <= 0:
            raise ValueError("третье измерение детали должно быть положительным")

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Габарит детали в плоскости модели: (xmin, ymin, xmax, ymax)."""
        boxes = [piece.polygon.bounds for piece in self.pieces]
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )

    @property
    def width_mm(self) -> float:
        """Размер поперёк, по X."""
        xmin, _, xmax, _ = self.bounds
        return xmax - xmin

    @property
    def length_mm(self) -> float:
        """Размер вдоль, по Y."""
        _, ymin, _, ymax = self.bounds
        return ymax - ymin

    @property
    def area_mm2(self) -> float:
        """Суммарная площадь ячеек."""
        return sum(piece.area_mm2 for piece in self.pieces)

    def species_at(self, x: float, y: float) -> str | None:
        """Порода в точке плана. Нужна тестам и подсказкам в UI."""
        from shapely.geometry import Point

        point = Point(x, y)
        for piece in self.pieces:
            if piece.polygon.covers(point):
                return piece.species
        return None

    def has_degenerate(self, min_size_mm: float) -> bool:
        """Есть ли ячейка тоньше порога — слишком тонкие детали опасно пилить."""
        for piece in self.pieces:
            xmin, ymin, xmax, ymax = piece.polygon.bounds
            if min(xmax - xmin, ymax - ymin) < min_size_mm - EPS:
                return True
        return False


type Billet = tuple[Part, ...]
"""Именованная заготовка: щит — кортеж из одной детали, пачка после реза — из n."""
