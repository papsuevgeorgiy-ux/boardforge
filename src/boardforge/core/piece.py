"""Заготовка: ячейки узора и деталь, из которой собирается доска."""

import math
from dataclasses import dataclass, field

from shapely.geometry import Polygon

from .units import EPS


@dataclass(frozen=True, slots=True)
class Origin:
    """Откуда приехал кусок дерева: щит, рейка в нём и место по длине рейки.

    Переживает все операции: рез только уточняет смещение, а постановка на
    торец, склейка со сдвигами и отражениями и обрезка происхождение не меняют.
    Это единственный способ узнать, что две ячейки — последовательные срезы
    одной и той же рейки, а не просто одного цвета.
    """

    billet: str
    strip: int
    offset_mm: float
    """Расстояние от начала рейки до начала ячейки вдоль исходной длины щита."""
    species: str

    def __post_init__(self) -> None:
        if self.strip < 0:
            raise ValueError("номер рейки не может быть отрицательным")
        if not self.species:
            raise ValueError("у ячейки не указана порода")

    @property
    def strip_key(self) -> tuple[str, int]:
        """Рейка целиком — сид текстуры берётся из неё, а не из ячейки."""
        return (self.billet, self.strip)

    def shifted(self, delta_mm: float) -> "Origin":
        """То же происхождение, но глубже по длине рейки на `delta_mm`."""
        if delta_mm == 0.0:
            return self
        return Origin(self.billet, self.strip, self.offset_mm + delta_mm, self.species)


@dataclass(frozen=True, slots=True)
class Orientation:
    """Каким боком деталь положили в план относительно того, как её отпилили.

    Полигон помнит, где деталь лежит, но не помнит, как её повернули: квадрат,
    развёрнутый на 180°, — тот же самый квадрат. А рисунок волокон в нём
    развёрнут, потому что физически перевернулся вместе с деревом. Без этого
    поля `reversed` и `flipped` не видно в превью, и половина узоров Дня 4
    перестаёт отличаться от узоров без разворотов.

    Преобразование читается справа налево: сначала отражение поперёк продольной
    оси, затем поворот в плане.
    """

    turn_deg: float = 0.0
    mirrored: bool = False

    def turned(self, degrees: float) -> "Orientation":
        """Ещё один поворот детали в плане."""
        return Orientation((self.turn_deg + degrees) % 360.0, self.mirrored)

    def flipped(self) -> "Orientation":
        """Переворот на другую сторону, вокруг продольной оси.

        Отражение слева от уже накопленного поворота эквивалентно отражению
        справа с обратным поворотом — отсюда смена знака.
        """
        return Orientation((-self.turn_deg) % 360.0, not self.mirrored)

    def apply(self, x: float, y: float) -> tuple[float, float]:
        """Точка из системы координат куска дерева — в систему координат плана."""
        if self.mirrored:
            x = -x
        radians = math.radians(self.turn_deg)
        cosine, sine = math.cos(radians), math.sin(radians)
        return (x * cosine - y * sine, x * sine + y * cosine)


@dataclass(frozen=True, slots=True)
class Piece:
    """Ячейка узора: полигон в плоскости модели, происхождение и разворот."""

    polygon: Polygon
    origin: Origin
    orientation: Orientation = field(default_factory=Orientation)

    @property
    def species(self) -> str:
        """Порода ячейки. Хранится в происхождении: источник истины один."""
        return self.origin.species

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
