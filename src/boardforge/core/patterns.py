"""Параметрические генераторы угловых узоров.

Узор здесь не рисуется, а **выписывается программой**: генератор считает углы
и сдвиги из геометрии и возвращает `Program`. Инвариант проекта не нарушается —
доска остаётся программой, просто её параметры посчитал не человек.

Сдвиги обязаны считаться, а не задаваться константами. Рез нормализует каждую
полосу к началу координат (полоса не помнит, откуда приехала), поэтому фаза
узора в полосах разная, и чтобы рисунок сошёлся на стыках, её надо вернуть.
Опорный сдвиг — тот, что кладёт полосу ровно туда, где она лежала; всё
остальное считается от него.

Обратная задача для углов сюда не относится: по `decisions.md` солвер работает
только с ортогональными узорами, а угловые задаются параметрами.
"""

import math
from dataclasses import dataclass

from shapely.geometry import LineString

from . import geometry
from .ops import (
    Assemble,
    Crop,
    Crosscut,
    Cut,
    Glue,
    PieceRef,
    StandOnEnd,
    Strip,
    target_of,
)
from .program import Program
from .units import EPS

_PANEL = "P"
_BOARD = "BOARD"


@dataclass(frozen=True, slots=True)
class StripedPanel:
    """Полосатый щит — заготовка под любой угловой узор.

    В плане это горизонтальные породные полосы шириной `strip_width_mm` во всю
    доску. Вертикальные швы между столбцами разделяют куски одной породы
    и в узоре не читаются: широкий торцевой щит иначе и не собрать.
    """

    species: tuple[str, ...]
    strip_width_mm: float = 40.0
    board_height_mm: float = 40.0
    column_width_mm: float = 20.0
    columns: int = 12
    repeats: int = 4
    """Сколько раз повторить породный цикл по высоте щита.

    Не украшение. Сдвиг полосы считается по модулю периода узора, и перенос
    на период обязан переводить породную линию в такую же соседнюю — а для
    этого соседняя должна существовать. При одном цикле переносить не на что,
    и на части швов просто нет материала.
    """

    def __post_init__(self) -> None:
        if not self.species:
            raise ValueError("полосатому щиту нужна хотя бы одна порода")
        if self.columns < 1:
            raise ValueError("в щите должен быть хотя бы один столбец")
        if self.repeats < 1:
            raise ValueError("породный цикл должен повториться хотя бы раз")

    @property
    def height_mm(self) -> float:
        """Высота полосатого щита в плане — сумма ширин полос."""
        return self.strip_width_mm * len(self.species) * self.repeats

    def operations(self) -> tuple[object, ...]:
        """Операции до собранного полосатого щита включительно."""
        strips = tuple(
            Strip(name, self.strip_width_mm)
            for _ in range(self.repeats)
            for name in self.species
        )
        return (
            Glue(
                id="A",
                strips=strips,
                # Столбец в плане — одна полоса торцовки, поэтому длины щита
                # нужно ровно `columns` шагов торцовки, а не ширин столбца.
                length_mm=self.board_height_mm * self.columns,
                thickness_mm=self.column_width_mm,
            ),
            Crosscut(source="A", step_mm=self.board_height_mm),
            StandOnEnd(source="A"),
            Assemble(
                id=_PANEL,
                pieces=tuple(PieceRef("A", index) for index in range(self.columns)),
                reversed=(False,) * self.columns,
                offsets_mm=(0.0,) * self.columns,
            ),
        )


def _cut_frame_offsets(
    panel: StripedPanel, angle_deg: float, step_mm: float
) -> tuple[list[float], int]:
    """Сдвиги, возвращающие каждую полосу на своё место, и число полос.

    Меряется исполнением, а не формулой: та же логика, что у обратной задачи
    по габаритам (Р18). Формула не знает про клинья на краях щита, из-за
    которых габарит полосы, а с ним и нормализация, у всех разные.
    """
    program = Program(operations=tuple(panel.operations()))
    board = program.run().board
    sliced = geometry.slice_part(board, angle_deg, step_mm)
    base = sliced.placements_mm[0][1]
    return [y - base for _, y in sliced.placements_mm], len(sliced.parts)


def _stripe_pitch_mm(panel: StripedPanel, angle_deg: float) -> float:
    """Шаг породных линий вдоль оси полосы.

    Породные линии горизонтальны; в системе координат реза их направление
    (cos θ, −sin θ), и расстояние между соседними вдоль оси полосы получается
    `w / |cos θ|`.
    """
    cosine = abs(math.cos(math.radians(angle_deg)))
    if cosine < 1e-9:
        raise ValueError(
            f"при угле {angle_deg}° рез идёт вдоль породных полос — узора не будет"
        )
    return panel.strip_width_mm / cosine


def _wrapped(value: float, period: float) -> float:
    """Сдвиг по модулю периода узора, представитель ближайший к нулю."""
    return value - period * round(value / period)


def _zigzag(
    panel: StripedPanel,
    angle_deg: float,
    step_mm: float,
    phase_mm: float,
    trim: int,
    square: bool,
) -> Program:
    """Общее тело ёлочки и шеврона: зеркальные полосы через одну.

    `phase_mm` — добавка к сдвигу зеркальных полос. Ноль даёт сплошной зигзаг
    (шеврон), половина шага породных линий — разорванный (ёлочка).
    """
    placements, count = _cut_frame_offsets(panel, angle_deg, step_mm)

    usable = range(trim, count - trim)
    if len(usable) < 2:
        raise ValueError(
            f"после отбраковки клиньев осталось {len(usable)} полос — "
            "щиту не хватает ширины на этот угол"
        )

    # Поправка к укладке «полоса на своё место» **накапливается**, а не
    # чередуется: приравнивание высот породной линии на шве даёт одну и ту же
    # рекурренту `d_k = d_{k−1} + s·tg θ` и для стыка «прямая|зеркальная»,
    # и для «зеркальная|прямая». Отсюда же видно, почему альтернирующая
    # поправка закрывает только каждый второй шов.
    drift = step_mm * math.tan(math.radians(angle_deg))

    # Сдвиг определён с точностью до периода узора по оси полосы (правило
    # сдвигов, Р22): прибавка целого периода переводит породную линию в такую
    # же соседнюю. Берём представителя, ближайшего к нулю, иначе доска уезжает
    # в параллелограмм и полезной площади не остаётся.
    period = len(panel.species) * _stripe_pitch_mm(panel, angle_deg)

    pieces: list[PieceRef] = []
    flipped: list[bool] = []
    offsets: list[float] = []
    correction = 0.0
    for slot, index in enumerate(usable):
        mirror = slot % 2 == 1
        pieces.append(PieceRef(_PANEL, index))
        flipped.append(mirror)
        # Сворачивается **весь** сдвиг, а не одна поправка. Опорный член
        # «положить полосу туда, где она лежала» растёт линейно, и без свёртки
        # щит воспроизводит повёрнутый прямоугольник — то есть лестницу,
        # от которой после обрезки почти ничего не остаётся.
        offsets.append(
            _wrapped(
                placements[index] + correction + (phase_mm if mirror else 0.0), period
            )
        )
        correction = _wrapped(correction + drift, period)

    program = Program(
        operations=(
            *panel.operations(),
            Cut(source=_PANEL, angle_deg=angle_deg, step_mm=step_mm),
            Assemble(
                id=_BOARD,
                pieces=tuple(pieces),
                reversed=(False,) * len(pieces),
                offsets_mm=tuple(offsets),
                flipped=tuple(flipped),
            ),
        )
    )
    return squared(program) if square else program


def squared(program: Program) -> Program:
    """Дописать обрезку до прямоугольника без ступенек по краям.

    Сдвиги рядов оставляют щит рваным сверху и снизу — это не брак узора,
    а нормальное состояние перед обрезкой в размер. Полоса, торчащая над
    соседями, доски не образует: доска кончается там, где кончается самый
    короткий ряд.

    Обрезка **дизайнерская** (Р5), поэтому она операция программы, а не припуск.
    Размер меряется исполнением, как и обратная задача по габаритам (Р18):
    формула не знает, куда именно уехал каждый ряд.
    """
    board = program.run().board
    xmin, ymin, xmax, ymax = board.bounds
    outline = board.outline

    # Прямоугольник во всю ширину кончается там, где кончается самый короткий
    # ряд. Меряем вертикальными сечениями: у полос концы скошены, поэтому
    # габарита ряда недостаточно — важна самая низкая точка его верхней кромки.
    samples = 240
    lows: list[float] = []
    highs: list[float] = []
    for index in range(1, samples):
        x = xmin + (xmax - xmin) * index / samples
        column = outline.intersection(LineString([(x, ymin - 1.0), (x, ymax + 1.0)]))
        if column.is_empty:
            raise ValueError(
                f"щит не сплошной: на {x:.1f} мм от кромки нет материала — "
                "обрезать до прямоугольника нечего"
            )
        lows.append(column.bounds[1])
        highs.append(column.bounds[3])

    covered_bottom, covered_top = max(lows), min(highs)
    if covered_top - covered_bottom <= EPS:
        # Молча вернуть необрезанный щит нельзя: получится лестница, выданная
        # за доску. Либо прямоугольник есть, либо об этом надо сказать.
        raise ValueError(
            "ряды разъехались так, что прямоугольника во всю ширину не остаётся: "
            f"нижние кромки доходят до {covered_bottom:.0f} мм, верхние "
            f"начинаются с {covered_top:.0f} мм. Возьми щит длиннее или "
            "шаг реза мельче"
        )

    return Program(
        operations=(
            *program.operations,
            Crop(
                source=target_of(program.operations[-1]),
                bottom=covered_bottom - ymin,
                top=ymax - covered_top,
            ),
        )
    )


def chevron(
    panel: StripedPanel,
    angle_deg: float = 45.0,
    step_mm: float = 40.0,
    trim: int = 1,
    square: bool = False,
) -> Program:
    """Шеврон: породные линии сходятся на стыке в непрерывный зигзаг.

    `trim` — сколько полос отбросить с каждого края: при угловом резе крайние
    полосы вырождаются в клинья, и чем ближе рез к продольному, тем острее нос.
    `square` — дописать обрезку до прямоугольника. По умолчанию нет: обрезка
    дизайнерская (Р5), то есть осознанное решение, а не автоматика. Щит после
    склейки рваный сверху и снизу — это нормальное состояние до обрезки
    в размер, и прямоугольник из него выходит не всегда: `squared` про это
    скажет, а не подгонит молча.
    """
    return _zigzag(panel, angle_deg, step_mm, phase_mm=0.0, trim=trim, square=square)


def herringbone(
    panel: StripedPanel,
    angle_deg: float = 45.0,
    step_mm: float = 40.0,
    trim: int = 1,
    square: bool = False,
) -> Program:
    """Ёлочка: тот же рез и то же зеркало, зигзаг разорван на полшага.

    От шеврона отличается ровно одним числом — сдвигом зеркальных полос
    на половину шага породных линий.
    """
    return _zigzag(
        panel,
        angle_deg,
        step_mm,
        phase_mm=_stripe_pitch_mm(panel, angle_deg) / 2,
        trim=trim,
        square=square,
    )


__all__ = ["StripedPanel", "chevron", "herringbone"]
