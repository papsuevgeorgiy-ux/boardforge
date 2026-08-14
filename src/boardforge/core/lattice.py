"""Правило сдвигов (Р22) арифметикой, а не глазом.

До реза узор — мозаика с решёткой трансляций `Λ`. Рез делит её на полосы
вдоль оси `b`, склейка сдвигает полосу на `o`. Линия узора снова становится
сквозной тогда и только тогда, когда

    o · b ∈ Λ

Отсюда весь модуль: найти кратчайший вектор решётки, параллельный оси реза.
Он же минимальный шаг сдвига, а все допустимые сдвиги — его кратные.

**Если вдоль оси вектора решётки нет — решения нет.** Не «почти сошлось»,
не ближайшее приближение: узор не сойдётся ни при каком сдвиге, и сказать
это надо словами до того, как человек начнёт пилить. Приближение здесь
хуже отказа — оно даёт щит, который на превью выглядит правильным,
а в дереве расходится на каждом шве.

Рекуррента шеврона (`patterns.py`) — частный случай с одним условием
и известной формулой. У кубов условий два и формулы нет, поэтому подбор
общий: перебор по решётке с проверкой исполнением.
"""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fractions import Fraction

_PARALLEL_TOL = 1e-7
"""Синус угла между вектором решётки и осью. 1e-7 — это 0.1 мкм на метре:
меньше любого столярного допуска и много больше ошибки округления."""

_MAX_DENOMINATOR = 512
"""Докуда искать целые коэффициенты. Вектор решётки с числами крупнее
означает период в сотни ячеек — такой узор не узор, а случайность."""


class NoLatticeSolution(ValueError):
    """Вдоль этой оси вектора решётки нет — сдвига, который сведёт узор, тоже."""


def _cross(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]


@dataclass(frozen=True, slots=True)
class Lattice:
    """Решётка трансляций узора: два вектора, узор переносится их суммами."""

    first: tuple[float, float]
    second: tuple[float, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "first", (float(self.first[0]), float(self.first[1])))
        object.__setattr__(self, "second", (float(self.second[0]), float(self.second[1])))
        scale = math.hypot(*self.first) * math.hypot(*self.second)
        if scale <= 0.0:
            raise ValueError("вектор решётки не может быть нулевым")
        if abs(_cross(self.first, self.second)) / scale < _PARALLEL_TOL:
            raise ValueError(
                "векторы решётки параллельны — это не решётка, а один ряд точек"
            )

    def vector(self, first_count: int, second_count: int) -> tuple[float, float]:
        """Узел решётки по целым коэффициентам."""
        return (
            first_count * self.first[0] + second_count * self.second[0],
            first_count * self.first[1] + second_count * self.second[1],
        )

    def shortest_along(self, direction_deg: float) -> float | None:
        """Длина кратчайшего ненулевого вектора решётки вдоль направления.

        `None` — решения нет: ни одна целочисленная комбинация не ложится
        на это направление. Возвращается именно `None`, а не ближайшее
        значение: см. заголовок модуля.
        """
        radians = math.radians(direction_deg)
        axis = (math.cos(radians), math.sin(radians))

        along_first = _cross(self.first, axis)
        along_second = _cross(self.second, axis)
        scale = max(math.hypot(*self.first), math.hypot(*self.second))

        if abs(along_first) < _PARALLEL_TOL * scale:
            return math.hypot(*self.first)
        if abs(along_second) < _PARALLEL_TOL * scale:
            return math.hypot(*self.second)

        ratio = Fraction(-along_first / along_second).limit_denominator(_MAX_DENOMINATOR)
        counts = (ratio.denominator, ratio.numerator)
        if counts == (0, 0):
            return None

        candidate = self.vector(*counts)
        length = math.hypot(*candidate)
        if length <= 0.0:
            return None
        if abs(_cross(candidate, axis)) / length > _PARALLEL_TOL:
            return None
        return length

    def quantum_along(self, direction_deg: float, what: str) -> float:
        """То же, но отказ — исключение с человеческим объяснением.

        `what` — чем занимается вызывающий, чтобы в сообщении было видно,
        какой именно узор не сходится.
        """
        step = self.shortest_along(direction_deg)
        if step is None:
            raise NoLatticeSolution(
                f"{what}: вдоль оси реза под {direction_deg:.1f}° у узора нет "
                f"вектора трансляции. Сдвиг полосы не сведёт линии ни при каком "
                f"значении — нужен другой угол реза или другой состав щита"
            )
        return step


@dataclass(frozen=True, slots=True)
class LineFamily:
    """Семейство параллельных линий узора: направление и шаг поперёк.

    Отдельно от `Lattice`, потому что условие другое. Решётка отвечает,
    когда сдвиг переводит **узор** в себя; семейство — когда сдвиг оставляет
    **прямыми** конкретные линии. Второе слабее и потому полезнее: у кубов
    линии обязаны остаться сквозными, а породы поперёк них меняются нарочно.
    """

    direction_deg: float
    pitch_mm: float

    def __post_init__(self) -> None:
        if self.pitch_mm <= 0:
            raise ValueError("шаг семейства линий должен быть положительным")

    def shift_quantum(self, axis_deg: float) -> float:
        """Наименьший сдвиг вдоль оси, после которого линии снова сквозные.

        Сдвиг раскладывается на составляющую вдоль линий (её линии не
        замечают) и поперёк — вот она и обязана быть кратной шагу.
        """
        across = abs(math.sin(math.radians(axis_deg - self.direction_deg)))
        if across < _PARALLEL_TOL:
            raise NoLatticeSolution(
                f"ось реза под {axis_deg:.1f}° идёт вдоль самих линий узора "
                f"({self.direction_deg:.1f}°) — сдвиг вдоль неё ничего не меняет, "
                f"и узора из такого реза не выйдет"
            )
        return self.pitch_mm / across


def common_quantum(quanta: Iterable[float], what: str) -> float:
    """Наименьший сдвиг, удовлетворяющий сразу нескольким условиям.

    У шеврона условие одно и вопроса нет. У кубов их два — сквозными обязаны
    остаться и породные линии, и швы предыдущего реза, — и общий шаг существует
    только если отношение шагов рационально. Если нет, узор не сойдётся ни при
    каком сдвиге, и это надо сказать, а не подобрать ближайшее.
    """
    values = [float(value) for value in quanta]
    if not values:
        raise ValueError("нечего согласовывать: список шагов пуст")
    if any(value <= 0 for value in values):
        raise ValueError("шаг сдвига должен быть положительным")

    result = values[0]
    for value in values[1:]:
        ratio = Fraction(result / value).limit_denominator(_MAX_DENOMINATOR)
        if ratio.numerator == 0:
            raise NoLatticeSolution(f"{what}: шаг сдвига выродился в ноль")
        candidate = result * ratio.denominator
        if abs(candidate / value - round(candidate / value)) > _PARALLEL_TOL:
            raise NoLatticeSolution(
                f"{what}: два условия на сдвиг несовместимы — шаги {result:.4f} "
                f"и {value:.4f} мм несоизмеримы. Общего сдвига, при котором "
                f"сойдутся оба семейства линий, не существует"
            )
        result = candidate
    return result


def striped_lattice(strip_width_mm: float, cycle: int, column_width_mm: float) -> Lattice:
    """Решётка полосатого щита, каким он выходит после `StandOnEnd`.

    По вертикали переносит породный цикл целиком, по горизонтали — столбец.
    Столбец считается частью решётки, хотя шов между столбцами и не виден:
    решётка описывает **рисунок**, а волосяная линия — тоже рисунок, просто
    слабый. Без второго вектора это была бы не решётка, а один ряд точек.
    """
    if strip_width_mm <= 0 or column_width_mm <= 0:
        raise ValueError("ширины полосы и столбца должны быть положительными")
    if cycle < 1:
        raise ValueError("породный цикл должен состоять хотя бы из одной полосы")
    return Lattice((column_width_mm, 0.0), (0.0, strip_width_mm * cycle))


@dataclass(frozen=True, slots=True)
class ShiftGrid:
    """Сетка допустимых сдвигов полосы: шаг и сколько шагов до повтора.

    Сдвиг на `size` шагов возвращает узор в исходную фазу, поэтому перебирать
    надо ровно `size` вариантов, а не бесконечность.
    """

    quantum_mm: float
    size: int

    def __post_init__(self) -> None:
        if self.quantum_mm <= 0:
            raise ValueError("шаг сдвига должен быть положительным")
        if self.size < 1:
            raise ValueError("в сетке сдвигов должен быть хотя бы один вариант")

    @property
    def period_mm(self) -> float:
        """Сдвиг, после которого узор повторяет сам себя."""
        return self.quantum_mm * self.size

    def offset(self, phase: int) -> float:
        """Сдвиг по номеру фазы; номер берётся по модулю размера сетки."""
        return self.quantum_mm * (phase % self.size)

    def wrapped(self, value_mm: float) -> float:
        """Представитель сдвига, ближайший к нулю.

        Без свёртки накопленный сдвиг уводит щит в параллелограмм, и после
        обрезки от доски ничего не остаётся — это уже ловилось на шевроне.
        """
        period = self.period_mm
        return value_mm - period * round(value_mm / period)


def affine_phases(size: int, count: int, slope: int, start: int) -> tuple[int, ...]:
    """Фазы `start + slope · k` по модулю размера сетки.

    Перебирать произвольные наборы фаз бессмысленно: их `size ** count`, и
    почти все дают мусор. Узор, который вообще может сойтись, повторяется
    по полосам, а значит фаза линейна по номеру полосы — перебора остаётся
    `size²` вариантов вместо экспоненты.
    """
    if count < 0:
        raise ValueError("число полос не может быть отрицательным")
    return tuple((start + slope * index) % size for index in range(count))


def search_affine_phases(
    grid: ShiftGrid,
    count: int,
    score: Callable[[tuple[int, ...]], float | None],
    slopes: Iterable[int] | None = None,
) -> tuple[int, ...] | None:
    """Перебрать линейные наборы фаз и вернуть лучший по `score`.

    `score` возвращает `None`, если набор не годится вовсе (например, узор
    не собрался). Если не годится ни один — возвращается `None`: решения нет,
    и приближать нечего.
    """
    best: tuple[int, ...] | None = None
    best_score = -math.inf
    for slope in range(grid.size) if slopes is None else slopes:
        for start in range(grid.size):
            phases = affine_phases(grid.size, count, slope, start)
            value = score(phases)
            if value is None:
                continue
            if value > best_score:
                best, best_score = phases, value
    return best


__all__ = [
    "Lattice",
    "LineFamily",
    "NoLatticeSolution",
    "ShiftGrid",
    "affine_phases",
    "common_quantum",
    "search_affine_phases",
    "striped_lattice",
]
