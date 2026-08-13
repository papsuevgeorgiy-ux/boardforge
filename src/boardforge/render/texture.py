"""Процедурная текстура торца: годичные кольца и сердцевинные лучи.

Кольца — дуги окружностей с центром вне ячейки. Расстояние и направление до
сердцевины разыгрываются **на рейку, а не на ячейку**: соседние ячейки одного
столбца — последовательные срезы одной и той же рейки, и рисунок у них обязан
почти совпадать. Смещение по длине рейки не разыгрывает сердцевину заново,
а лишь медленно её уводит — так вдоль столбца получается дрейф вместо каши.

Отсюда и физика: близкая сердцевина даёт сильно изогнутые кольца, далёкая —
почти прямые. Расстояние разыгрывается квадратично, поэтому большинство реек
выглядит спокойно, а редкие — с явным центром.

Сид берётся из происхождения ячейки (`Origin`), а не из её координат в доске:
перестановки, сдвиги и обрезка рисунок дерева не меняют.
"""

import hashlib
import math
from dataclasses import dataclass

from ..core.piece import Orientation, Origin

DRIFT_NODE_MM = 400.0
"""Длина рейки, на которой дрейф проходит один узел шума."""

PITH_DRIFT_MM = 10.0
"""На сколько миллиметров уводит сердцевину за узел дрейфа.

Именно миллиметры, а не доля расстояния: ствол вдоль себя не расширяется, и у
далёкой сердцевины соседние срезы обязаны выглядеть одинаково так же, как
у близкой. Умножь этот увод на расстояние — и почти прямые кольца на соседних
ячейках разъехались бы на десяток колец.
"""

PHASE_DRIFT_RINGS = 0.8
"""Сдвиг фазы колец за узел дрейфа, в кольцах."""

NEAR_PITH = 0.7
FAR_PITH = 16.0
"""Расстояние до сердцевины в размерах ячейки: от почти внутри до почти прямых."""

RING_JITTER = 0.22
"""Разброс ширины кольца: годы неодинаковы, идеально ровный шаг выдаёт машину."""

RAY_SPACING_MM = 2.4
"""Средний шаг между лучами по касательной на уровне ячейки."""

RAY_GAP_MIN = 0.30
RAY_GAP_MAX = 2.1
"""Разброс промежутка между соседними лучами, в долях среднего шага.

Равномерный шаг — главный признак решётки: она видна с двух метров и остаётся
решёткой при отдалении, вместо того чтобы слиться в тон. Поэтому промежуток
разыгрывается, а не берётся постоянным.
"""

RAY_REACH_MIN = 0.06
RAY_REACH_BIAS = 3.0
"""Длина луча в долях радиального пролёта ячейки, смещённая к коротким:
большинство лучей обрывается, не дойдя до края."""

RAY_WIDTH_LEVELS = (0.55, 1.0, 1.7)
"""Толщины лучей относительно породной. Ступени, а не непрерывный разброс:
в SVG у каждой толщины свой путь, и плодить путь на каждый луч дорого."""

MAX_RAYS = 96
MAX_RINGS = 200
"""Потолки на случай крошечной ширины кольца — рисунок всё равно не разглядеть."""


def _unit(*key: object) -> float:
    """Псевдослучайное число [0, 1) из ключа. Хеш стабилен между запусками.

    Встроенный `hash` для строк солится при каждом старте интерпретатора,
    поэтому здесь blake2b, а не он: рендер обязан быть воспроизводимым.
    """
    payload = "\x1f".join(str(item) for item in key).encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2.0**64


def _drift(key: tuple[object, ...], position: float) -> float:
    """Плавный шум [-1, 1] вдоль рейки: узлы через `DRIFT_NODE_MM`, между ними
    сглаженная интерполяция. Близкие смещения дают близкие значения."""
    node = math.floor(position)
    fraction = position - node
    smooth = fraction * fraction * (3.0 - 2.0 * fraction)
    low = _unit(*key, node) * 2.0 - 1.0
    high = _unit(*key, node + 1) * 2.0 - 1.0
    return low + (high - low) * smooth


@dataclass(frozen=True, slots=True)
class RingField:
    """Поле колец в координатах ячейки: центр в её середине, миллиметры.

    `seed` — ключ рейки. Мелкие неровности колец и лучей разыгрываются по нему
    и по номеру кольца, но не по смещению: одно и то же кольцо на соседних
    срезах рейки обязано остаться собой.

    Поле уже развёрнуто вместе с деталью: положение сердцевины несёт и поворот,
    и отражение, а кольца концентричны, так что дуги следуют за ней сами.
    `mirrored` нужен только веерy лучей — чтобы их разбежка тоже отразилась.
    """

    pith_x: float
    pith_y: float
    ring_width_mm: float
    phase_mm: float
    seed: tuple[str, int]
    mirrored: bool = False

    @property
    def pith_distance_mm(self) -> float:
        """Расстояние от середины ячейки до сердцевины."""
        return math.hypot(self.pith_x, self.pith_y)


@dataclass(frozen=True, slots=True)
class Arc:
    """Дуга кольца в координатах ячейки. `span_deg == 360` — полное кольцо."""

    radius_mm: float
    start_deg: float
    span_deg: float

    @property
    def full(self) -> bool:
        """Замкнутое ли кольцо."""
        return self.span_deg >= 360.0


@dataclass(frozen=True, slots=True)
class RayLine:
    """Отрезок сердцевинного луча — радиальный, то есть поперёк колец."""

    x1: float
    y1: float
    x2: float
    y2: float
    width_mm: float


def ring_field(
    origin: Origin,
    ring_width_mm: float,
    size_mm: float,
    orientation: Orientation | None = None,
) -> RingField:
    """Где у этой ячейки сердцевина и с какой фазой идут кольца.

    `size_mm` — характерный размер ячейки: им меряется расстояние до
    сердцевины, чтобы мелкая ячейка не получила кольца в полдоски радиусом.

    `orientation` — как деталь положили в план. Кольца концентричны, поэтому
    развернуть рисунок — это развернуть сердцевину вокруг середины ячейки;
    всё остальное (радиусы, фаза, неровности) от поворота не зависит.
    """
    if ring_width_mm <= 0:
        raise ValueError("ширина годичного кольца должна быть положительной")

    orientation = orientation or Orientation()
    strip = origin.strip_key
    position = origin.offset_mm / DRIFT_NODE_MM

    direction = math.radians(360.0 * _unit(*strip, "direction"))
    far = _unit(*strip, "distance")
    distance = size_mm * (NEAR_PITH + (FAR_PITH - NEAR_PITH) * far * far)

    phase = ring_width_mm * (
        _unit(*strip, "phase")
        + PHASE_DRIFT_RINGS * _drift((*strip, "phase-drift"), position)
    )

    drift_x = PITH_DRIFT_MM * _drift((*strip, "drift-x"), position)
    drift_y = PITH_DRIFT_MM * _drift((*strip, "drift-y"), position)
    pith_x, pith_y = orientation.apply(
        distance * math.cos(direction) + drift_x,
        distance * math.sin(direction) + drift_y,
    )
    return RingField(
        pith_x=pith_x,
        pith_y=pith_y,
        ring_width_mm=ring_width_mm,
        phase_mm=phase % ring_width_mm,
        seed=strip,
        mirrored=orientation.mirrored,
    )


def ring_arcs(field: RingField, radius_mm: float) -> list[Arc]:
    """Дуги колец, попадающие в круг радиуса `radius_mm` вокруг центра ячейки.

    Кольцо целиком за пределами круга не рисуется вовсе, пересекающее — только
    своей дугой: полная окружность радиусом в метр раздувала бы файл и координаты.
    """
    distance = field.pith_distance_mm
    width = field.ring_width_mm
    if radius_mm <= 0:
        return []

    first = max(0, math.ceil((distance - radius_mm - field.phase_mm) / width))
    last = math.floor((distance + radius_mm - field.phase_mm) / width)
    if last - first > MAX_RINGS:
        last = first + MAX_RINGS

    toward_cell = math.degrees(math.atan2(-field.pith_y, -field.pith_x))
    arcs: list[Arc] = []
    for index in range(first, last + 1):
        wobble = width * RING_JITTER * (_unit(*field.seed, "ring", index) * 2.0 - 1.0)
        radius = field.phase_mm + index * width + wobble
        if radius <= 0:
            continue
        if distance <= 1e-9:
            if radius <= radius_mm:
                arcs.append(Arc(radius, 0.0, 360.0))
            continue
        cosine = (radius * radius + distance * distance - radius_mm * radius_mm) / (
            2.0 * radius * distance
        )
        if cosine >= 1.0:
            continue
        if cosine <= -1.0:
            arcs.append(Arc(radius, 0.0, 360.0))
            continue
        half = math.degrees(math.acos(cosine))
        arcs.append(Arc(radius, toward_cell - half, 2.0 * half))
    return arcs


def ray_lines(
    field: RingField,
    radius_mm: float,
    width_mm: float,
    spacing_mm: float = RAY_SPACING_MM,
) -> list[RayLine]:
    """Сердцевинные лучи: радиальные отрезки, расходящиеся от сердцевины.

    Луч — не линия сетки, а радиальная полоска клеток, которая где-то обрывается,
    а где-то доходит до края. Отсюда три разброса, все от сида рейки: промежуток
    между лучами, длина и толщина. Плотность на единицу площади падает с радиусом
    сама собой — лучи расходятся веером, и чем дальше от сердцевины, тем шире
    между ними просвет.
    """
    if radius_mm <= 0 or spacing_mm <= 0 or width_mm <= 0:
        return []

    distance = field.pith_distance_mm
    if distance <= radius_mm:
        half = 180.0
        inner = 0.0
    else:
        half = math.degrees(math.asin(radius_mm / distance))
        inner = distance - radius_mm
    outer = distance + radius_mm
    reach_mm = outer - inner
    if reach_mm <= 0:
        return []

    expected = max(1.0, 2.0 * radius_mm / spacing_mm)
    step = 2.0 * half / expected
    toward_cell = math.degrees(math.atan2(-field.pith_y, -field.pith_x))
    sign = -1.0 if field.mirrored else 1.0

    lines: list[RayLine] = []
    offset = -half
    for index in range(MAX_RAYS):
        gap = _unit(*field.seed, "gap", index)
        offset += step * (RAY_GAP_MIN + (RAY_GAP_MAX - RAY_GAP_MIN) * gap)
        if offset >= half:
            break

        radians = math.radians(toward_cell + sign * offset)
        cosine, sine = math.cos(radians), math.sin(radians)

        reach = _unit(*field.seed, "reach", index) ** RAY_REACH_BIAS
        span = reach_mm * (RAY_REACH_MIN + (1.0 - RAY_REACH_MIN) * reach)
        start = inner + (reach_mm - span) * _unit(*field.seed, "start", index)
        level = RAY_WIDTH_LEVELS[
            int(_unit(*field.seed, "width", index) * len(RAY_WIDTH_LEVELS))
        ]
        lines.append(
            RayLine(
                field.pith_x + start * cosine,
                field.pith_y + start * sine,
                field.pith_x + (start + span) * cosine,
                field.pith_y + (start + span) * sine,
                width_mm * level,
            )
        )
    return lines
