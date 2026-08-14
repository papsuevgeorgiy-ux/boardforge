"""Заготовка: ячейки узора и деталь, из которой собирается доска."""

import math
from dataclasses import dataclass, field

from shapely.geometry import Polygon

from .units import EPS

_SNAP_MM = 1e-6
"""Сетка округления контура детали: нанометр. На порядки мельче любого
столярного допуска и на порядки крупнее ошибки округления в пересечениях."""


def _min_rect_side(geometry: object) -> float:
    """Короткая сторона минимального повёрнутого прямоугольника.

    Габаритная рамка для этого не годится: у клина под 45° она большая,
    а сам клин тонкий. Проверка безопасности, построенная на рамке, пропустит
    ровно те детали, ради которых заведена.
    """
    rectangle = geometry.minimum_rotated_rectangle  # type: ignore[attr-defined]
    boundary = getattr(rectangle, "exterior", None)
    if boundary is None:
        return 0.0
    points = list(boundary.coords)[:-1]
    if len(points) < 4:
        return 0.0
    return min(
        math.dist(points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )


def _min_corner_angle(geometry: object) -> float:
    """Самый острый угол контура. Для набора фигур — самый острый по всем."""
    shapes = list(getattr(geometry, "geoms", [geometry]))
    smallest = 180.0
    for shape in shapes:
        boundary = getattr(shape, "exterior", None)
        if boundary is None:
            continue
        points = list(boundary.coords)[:-1]
        count = len(points)
        for index in range(count):
            here = points[index]
            first = (points[index - 1][0] - here[0], points[index - 1][1] - here[1])
            following = points[(index + 1) % count]
            second = (following[0] - here[0], following[1] - here[1])
            length = math.hypot(*first) * math.hypot(*second)
            if length < EPS:
                continue
            cosine = (first[0] * second[0] + first[1] * second[1]) / length
            smallest = min(smallest, math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    return smallest


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

    @property
    def min_width_mm(self) -> float:
        """Настоящая ширина ячейки — короткая сторона минимального прямоугольника.

        Габаритная рамка здесь не годится: у клина под 45° она большая, а сам
        клин тонкий. Меряем по повёрнутому прямоугольнику, иначе проверка
        безопасности пропустит ровно те детали, ради которых заведена.
        """
        return _min_rect_side(self.polygon)

    @property
    def min_angle_deg(self) -> float:
        """Самый острый угол ячейки."""
        return _min_corner_angle(self.polygon)


@dataclass(frozen=True, slots=True)
class Part:
    """Деталь: набор ячеек в собственных координатах плюс третье измерение.

    До `StandOnEnd` плоскость модели — пласть щита, `thickness_mm` — его
    толщина. После — план доски, `thickness_mm` — высота доски.
    """

    pieces: tuple[Piece, ...]
    thickness_mm: float
    _index: object | None = field(default=None, init=False, repr=False, compare=False)
    """Ленивый пространственный индекс для `species_at`. На равенство не влияет."""

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
        """Порода в точке плана. Нужна тестам и подсказкам в UI.

        Через пространственный индекс: у углового узора ячеек сотни, а точку
        спрашивают тысячами, и линейный перебор превращал проверку сходимости
        швов в минуты.
        """
        from shapely import STRtree
        from shapely.geometry import Point

        tree = self._index
        if tree is None:
            tree = STRtree([piece.polygon for piece in self.pieces])
            object.__setattr__(self, "_index", tree)

        point = Point(x, y)
        for index in tree.query(point):
            piece = self.pieces[index]
            if piece.polygon.covers(point):
                return piece.species
        return None

    def has_degenerate(self, min_size_mm: float) -> bool:
        """Есть ли ячейка тоньше порога — слишком тонкие детали опасно пилить."""
        return self.min_width_mm < min_size_mm - EPS

    @property
    def min_width_mm(self) -> float:
        """Ширина самой тонкой ячейки детали."""
        return min(piece.min_width_mm for piece in self.pieces)

    @property
    def min_angle_deg(self) -> float:
        """Самый острый угол среди ячеек детали."""
        return min(piece.min_angle_deg for piece in self.pieces)

    @property
    def outline(self) -> object:
        """Контур детали целиком: ячейки внутри неё уже склеены между собой.

        Разница принципиальная. Ячейка — это область породы в куске дерева,
        а не отдельная деталь: её склеили несколько операций назад, и в руки
        её никто не берёт. По станку едет **деталь**, и опасен её контур.

        Результат объединения округляется до нанометра. Без этого соседние
        ячейки, чьи общие кромки разошлись на 1e-12 мм, оставляют в контуре
        щели нулевой ширины — и `outline_min_angle_deg` честно находит там
        нос в 0°, которого в дереве нет. Ложная ошибка изготовимости хуже
        пропущенной: пользователь перестаёт читать замечания.
        """
        from shapely import set_precision
        from shapely.ops import unary_union

        return set_precision(
            unary_union([piece.polygon for piece in self.pieces]), _SNAP_MM
        )

    @property
    def outline_min_width_mm(self) -> float:
        """Ширина детали целиком — та, при которой полосу затягивает под диск."""
        return _min_rect_side(self.outline)

    @property
    def outline_min_angle_deg(self) -> float:
        """Самый острый угол контура детали: острый нос скалывается на склейке."""
        return _min_corner_angle(self.outline)


type Billet = tuple[Part, ...]
"""Именованная заготовка: щит — кортеж из одной детали, пачка после реза — из n."""
