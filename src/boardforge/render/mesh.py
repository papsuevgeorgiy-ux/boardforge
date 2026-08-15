"""Трёхмерная доска: те же ячейки ядра, поднятые на высоту, и фаска по кромке.

Меш ничего не придумывает. Ячейка плана становится призмой, порода — цветом
вершин, высота доски берётся у `Part.thickness_mm`. Разойдись 3D с плоским
рендером — это была бы уже другая доска, а доска у нас одна и та же программа.

**Фаска** сделана без булевых операций и без второй библиотеки. У каждой
вершины спрашивается расстояние до кромки доски: ближе фаски — вершина
опускается, дальше — стоит на полной высоте. Чтобы скос вышел шириной ровно
в фаску, крайняя ячейка заранее **режется** линией фаски на середину и полосу
вдоль кромки, и каждая часть становится своей призмой. Резать обязательно:
одних лишь вершин на линии фаски мало — триангуляция крышки соединяет вершины
как ей удобно и спокойно кладёт треугольник от кромки до дальнего угла ячейки,
растягивая двухмиллиметровый скос на все сорок. Измерено: без реза объём доски
падал на 20% вместо 0.1%.

**Масло** — преобразование цвета, а не модель финиша: тон темнеет и насыщается,
как темнеет смоченное дерево. Физики отражения здесь нет и не заявляется.

Экспорт — `.glb` в **метрах**: glTF так договорился, а доска в миллиметрах
пришла бы в браузер размером с дом.
"""

from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient

from ..core.piece import Part
from ..core.species import Species

CHAMFER_MM = 2.0
"""Фаска по верхней и нижней кромке. Снимают её всегда: острое ребро торцевой
доски скалывается о раковину в первый же месяц."""

OIL_DARKEN = 0.82
OIL_SATURATE = 1.18
"""Насколько масло темнит и насыщает тон. Подобрано на глаз по смоченному
образцу — измерением это не является и `verified` тут не будет."""

METRES_PER_MM = 0.001

_SNAP = 6
"""До скольких знаков округляются координаты при сопоставлении вершин.

Триангуляция возвращает те же точки, что были на входе, но пришедшие через
GEOS обратно; сравнивать их на точное равенство нельзя, а миллионная доля
миллиметра меньше любого столярного смысла.
"""


@dataclass(frozen=True, slots=True)
class MeshOptions:
    """Как строить меш."""

    chamfer_mm: float = CHAMFER_MM
    oiled: bool = True

    def __post_init__(self) -> None:
        if self.chamfer_mm < 0:
            raise ValueError("фаска не может быть отрицательной")


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    raw = value.lstrip("#")
    return tuple(int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def oiled_colour(value: str) -> tuple[int, int, int]:
    """Цвет породы под маслом: темнее и насыщеннее, как смоченное дерево."""
    red, green, blue = _hex_to_rgb(value)
    grey = (red + green + blue) / 3.0
    channels = [
        min(1.0, max(0.0, (grey + (channel - grey) * OIL_SATURATE) * OIL_DARKEN))
        for channel in (red, green, blue)
    ]
    return tuple(round(channel * 255) for channel in channels)  # type: ignore[return-value]


def _slabs(polygon: Polygon, inset: Polygon | None) -> list[Polygon]:
    """Ячейка, разрезанная линией фаски: середина и полоса вдоль кромки.

    Каждая часть дальше живёт своей призмой. Внутри середины все вершины стоят
    на полной высоте, внутри полосы — либо на кромке, либо на линии фаски,
    и скос получается ровно той ширины, какой заказан.
    """
    if inset is None:
        return [polygon]
    parts = []
    for piece in (polygon.intersection(inset), polygon.difference(inset)):
        if piece.is_empty:
            continue
        for geom in getattr(piece, "geoms", (piece,)):
            if geom.geom_type == "Polygon" and geom.area > 0:
                parts.append(geom)
    return parts or [polygon]


def _counterclockwise(polygon: Polygon) -> Polygon:
    """Контур против часовой стрелки — иначе призма выйдет вывернутой наизнанку.

    Ячейки ядра приходят согласованными, а `difference` по линии фаски отдаёт
    кольцо в любом порядке, какой ему удобнее. Замкнутость меша от этого не
    страдает, и на глаз тоже ничего не видно — а объём считается по нормалям,
    и вывернутый кусок вычитается вместо того, чтобы прибавиться: у шахматки
    доска "похудела" на 20% при фаске в два миллиметра.
    """
    return orient(polygon, sign=1.0)


def _heights(
    coords: list[tuple[float, float]],
    boundary: object,
    thickness: float,
    chamfer: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Верх и низ каждой вершины: у кромки доски они сходятся на величину фаски."""
    top = np.full(len(coords), thickness)
    bottom = np.zeros(len(coords))
    if chamfer <= 0:
        return top, bottom
    for index, (x, y) in enumerate(coords):
        distance = boundary.distance(Point(x, y))  # type: ignore[attr-defined]
        if distance < chamfer:
            cut = chamfer - distance
            top[index] -= cut
            bottom[index] += cut
    return top, bottom


def _fan(
    polygon: Polygon, order: dict[tuple[float, float], int]
) -> list[tuple[int, int, int]]:
    """Треугольники крышки против часовой стрелки, номерами вершин контура.

    Триангуляция берётся у GEOS: ячейка после обрезки бывает невыпуклой, и
    веер из первой вершины на ней разваливается. Новых точек GEOS не заводит,
    поэтому каждый угол треугольника обязан найтись в контуре — если не нашёлся,
    строить меш по этой ячейке нельзя, и молчать об этом нельзя тоже.

    Направление обхода GEOS не обещает, поэтому оно приводится здесь по знаку
    площади: от него зависит, куда смотрят нормали, а от нормалей — объём.
    """
    triangles = []
    for triangle in shapely.constrained_delaunay_triangles(polygon).geoms:
        corners = list(triangle.exterior.coords)[:3]
        found = [order.get((round(x, _SNAP), round(y, _SNAP))) for x, y in corners]
        if any(index is None for index in found):
            raise ValueError("триангуляция ячейки завела точку вне её контура")
        (ax, ay), (bx, by), (cx, cy) = corners
        if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0:
            found.reverse()
        triangles.append(tuple(found))  # type: ignore[arg-type]
    return triangles


def _prism(
    ring: Polygon, boundary: object, thickness: float, chamfer: float
) -> tuple[np.ndarray, np.ndarray]:
    """Вершины и треугольники одного куска — замкнутая призма со скосами.

    Повторяющиеся вершины отбрасываются, и триангулируется уже очищенный
    контур, а не исходный. Это не перестраховка: у кубов из 420 ячеек 209
    приходят с точкой, повторённой дважды — на кубах вообще много вырожденных
    мест, — и если крышку резать по исходному контуру, а бока строить по
    очищенному, треугольник крышки получает два одинаковых номера вершины.
    Грань схлопывается в отрезок, и меш перестаёт быть замкнутым.
    """
    coords: list[tuple[float, float]] = []
    order: dict[tuple[float, float], int] = {}
    for x, y in list(ring.exterior.coords)[:-1]:
        key = (round(x, _SNAP), round(y, _SNAP))
        if key in order:
            continue
        order[key] = len(coords)
        coords.append((x, y))
    count = len(coords)
    if count < 3:
        raise ValueError("в контуре куска меньше трёх различных вершин")

    top_z, bottom_z = _heights(coords, boundary, thickness, chamfer)
    vertices = np.array(
        [(x, y, top_z[i]) for i, (x, y) in enumerate(coords)]
        + [(x, y, bottom_z[i]) for i, (x, y) in enumerate(coords)],
        dtype=np.float64,
    )

    # Верх — как пришло от `_fan` (против часовой, нормаль вверх), низ — тем же
    # обходом наоборот. Бок для ребра i→j контура, идущего против часовой,
    # смотрит наружу именно в таком порядке вершин.
    cap = _fan(Polygon(coords), order)
    faces = list(cap)
    faces += [(c + count, b + count, a + count) for a, b, c in cap]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, i + count, j + count))
        faces.append((i, j + count, j))
    return vertices, np.array(faces, dtype=np.int64)


def board_mesh(
    board: Part, catalogue: dict[str, Species], options: MeshOptions | None = None
):
    """Меш доски: призма на ячейку, цвет вершин по породе, фаска по кромке."""
    import trimesh

    options = options or MeshOptions()
    outline = board.outline
    chamfer = options.chamfer_mm
    inset = None
    if chamfer > 0:
        shrunk = outline.buffer(-chamfer, join_style=2)
        if not shrunk.is_empty and shrunk.geom_type == "Polygon":
            inset = shrunk
    boundary = outline.boundary

    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    colours: list[np.ndarray] = []
    offset = 0
    for piece in board.pieces:
        species = catalogue.get(piece.species)
        base = species.palette.base if species else "#b0a08a"
        colour = oiled_colour(base) if options.oiled else _byte(base)
        for slab in _slabs(piece.polygon, inset):
            slab = _counterclockwise(slab)
            slab_vertices, slab_faces = _prism(
                slab, boundary, board.thickness_mm, chamfer
            )
            vertices.append(slab_vertices)
            faces.append(slab_faces + offset)
            offset += len(slab_vertices)
            colours.append(np.tile([*colour, 255], (len(slab_vertices), 1)))

    mesh = trimesh.Trimesh(
        vertices=np.vstack(vertices) * METRES_PER_MM,
        faces=np.vstack(faces),
        vertex_colors=np.vstack(colours).astype(np.uint8),
        process=False,
    )
    return mesh


def _byte(value: str) -> tuple[int, int, int]:
    red, green, blue = _hex_to_rgb(value)
    return (round(red * 255), round(green * 255), round(blue * 255))


def export_glb(
    board: Part, catalogue: dict[str, Species], options: MeshOptions | None = None
) -> bytes:
    """Доска в `.glb` — то, что показывает `<model-viewer>`.

    Здесь же меняются оси. У нас вверх смотрит Z: план доски лежит в XY, как
    во всём остальном проекте, и менять это ради экспорта нельзя. У glTF вверх
    смотрит Y, и никакого поворота при записи `trimesh` не делает — доска
    приезжает в браузер стоящей на ребре. Поворот на четверть оборота вокруг X
    ставит её на стол.
    """
    import trimesh

    mesh = board_mesh(board, catalogue, options).copy()
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(-np.pi / 2, (1.0, 0.0, 0.0))
    )
    return mesh.export(file_type="glb")


__all__ = [
    "CHAMFER_MM",
    "METRES_PER_MM",
    "MeshOptions",
    "board_mesh",
    "export_glb",
    "oiled_colour",
]
