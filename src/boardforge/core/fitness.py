"""Чем узор хорош: пять мер, каждая от нуля до единицы.

Мера — не мнение, а число, которое можно проверить. Поэтому здесь нет
«красиво»: есть контраст в перцептивных координатах, ритм как автокорреляция,
симметрия как доля совпавших проб, экономичность как отношение доски к закупке
и реализуемость как молчание валидатора.

Экономичность стоит наравне с остальными не из бухгалтерии. На Дне 3 выяснилось,
что угловой узор уводит в отход около половины щита; генератор, который этого
не видит, будет уверенно выдавать красивое и разорительное. Оценка обязана
знать цену.

Все меры считаются по **сетке проб**, а не по ячейкам: ячеек в угловом узоре
тысячи, они разного размера, и усреднять по ним значит взвешивать узор числом
резов. Проба на сетке взвешивает его площадью, как и смотрит глаз.
"""

import re
from dataclasses import dataclass

from .color import hex_to_lab
from .program import Program
from .safety import Limits, inspect
from .species import Species, load_species

GRID_STEPS = 40
"""Сторона сетки проб. Сорок на сорок — 1600 точек: мельче узора на любой
разумной доске и достаточно грубо, чтобы сотня программ считалась за секунды."""

REFERENCE_DELTA_E = 57.0
"""ΔE, которое считается полным контрастом.

Столько между клёном и орехом — парой, на которой стоит половина всех
разделочных досок. Выше бывает (клён с венге — 67), но за единицу берётся
не рекорд, а образец: узор из клёна с орехом контрастен полностью, и
требовать от меры «ещё контрастнее» незачем."""


@dataclass(frozen=True, slots=True)
class Weights:
    """Что важнее. Сумма не обязана равняться единице — оценка нормируется."""

    contrast: float = 0.25
    rhythm: float = 0.20
    symmetry: float = 0.15
    economy: float = 0.20
    feasibility: float = 0.20

    def __post_init__(self) -> None:
        if self.total <= 0:
            raise ValueError("хотя бы один вес должен быть положительным")
        for name in ("contrast", "rhythm", "symmetry", "economy", "feasibility"):
            if getattr(self, name) < 0:
                raise ValueError(f"вес {name} не может быть отрицательным")

    @property
    def total(self) -> float:
        return (
            self.contrast + self.rhythm + self.symmetry + self.economy + self.feasibility
        )


@dataclass(frozen=True, slots=True)
class Scores:
    """Пять мер узора и общая оценка по весам."""

    contrast: float
    rhythm: float
    symmetry: float
    economy: float
    feasibility: float

    def total(self, weights: Weights | None = None) -> float:
        """Взвешенная сумма, приведённая к 0–1."""
        weights = weights or Weights()
        return (
            weights.contrast * self.contrast
            + weights.rhythm * self.rhythm
            + weights.symmetry * self.symmetry
            + weights.economy * self.economy
            + weights.feasibility * self.feasibility
        ) / weights.total

    def as_dict(self) -> dict[str, float]:
        """Меры словарём — для показа в интерфейсе и в отчётах."""
        return {
            "контраст": self.contrast,
            "ритм": self.rhythm,
            "симметрия": self.symmetry,
            "экономичность": self.economy,
            "реализуемость": self.feasibility,
        }


def species_grid(program: Program, steps: int = GRID_STEPS) -> list[list[str | None]]:
    """Породы по равномерной сетке проб. `None` — материала в точке нет."""
    board = program.run().board
    xmin, ymin, xmax, ymax = board.bounds
    inset = 1e-6
    return [
        [
            board.species_at(
                xmin + inset + (xmax - xmin - 2 * inset) * column / (steps - 1),
                ymin + inset + (ymax - ymin - 2 * inset) * row / (steps - 1),
            )
            for column in range(steps)
        ]
        for row in range(steps)
    ]


def _shares(grid: list[list[str | None]]) -> dict[str, float]:
    counts: dict[str, int] = {}
    total = 0
    for row in grid:
        for species in row:
            if species is not None:
                counts[species] = counts.get(species, 0) + 1
                total += 1
    return {key: value / total for key, value in counts.items()} if total else {}


def contrast(grid: list[list[str | None]], catalogue: dict[str, Species]) -> float:
    """Средняя перцептивная разница между соседями по сетке.

    Считается по соседям, а не по всему набору пород: доска из светлого поля
    с одной тёмной линией по краю набора контрастна, а на вид почти однотонна.
    Пары одной породы дают ноль и участвуют в среднем — так частота границ
    входит в оценку сама.
    """
    cache: dict[tuple[str, str], float] = {}

    def delta(first: str, second: str) -> float:
        if first == second:
            return 0.0
        key = (first, second) if first < second else (second, first)
        if key not in cache:
            missing = [name for name in key if name not in catalogue]
            if missing:
                cache[key] = 0.0
            else:
                cache[key] = hex_to_lab(catalogue[key[0]].color).distance(
                    hex_to_lab(catalogue[key[1]].color)
                )
        return cache[key]

    total = 0.0
    pairs = 0
    height = len(grid)
    for row in range(height):
        for column in range(len(grid[row])):
            here = grid[row][column]
            if here is None:
                continue
            for other_row, other_column in ((row, column + 1), (row + 1, column)):
                if other_row >= height or other_column >= len(grid[other_row]):
                    continue
                there = grid[other_row][other_column]
                if there is None:
                    continue
                total += delta(here, there)
                pairs += 1
    if not pairs:
        return 0.0
    return min(1.0, total / pairs / REFERENCE_DELTA_E)


def rhythm(grid: list[list[str | None]]) -> float:
    """Повторяемость узора: лучшая автокорреляция сверх случайного совпадения.

    Поправка на случайность обязательна. Доска в одну породу совпадает сама
    с собой при любом сдвиге, и без поправки получила бы высший балл за ритм,
    которого в ней нет вовсе.
    """
    shares = _shares(grid)
    if not shares:
        return 0.0
    chance = sum(value * value for value in shares.values())
    if chance >= 0.999:
        return 0.0

    steps = len(grid)
    best = 0.0
    for shift in range(1, steps // 2 + 1):
        for horizontal in (True, False):
            matched = checked = 0
            for row in range(steps):
                for column in range(steps):
                    other = (row, column + shift) if horizontal else (row + shift, column)
                    if other[0] >= steps or other[1] >= steps:
                        continue
                    here = grid[row][column]
                    there = grid[other[0]][other[1]]
                    if here is None or there is None:
                        continue
                    checked += 1
                    matched += here == there
            if checked:
                best = max(best, matched / checked)
    return max(0.0, (best - chance) / (1.0 - chance))


def symmetry(grid: list[list[str | None]]) -> float:
    """Лучшая из трёх симметрий: поворот на 180° и два зеркала."""
    steps = len(grid)

    def share(mapper) -> float:  # type: ignore[no-untyped-def]
        matched = checked = 0
        for row in range(steps):
            for column in range(steps):
                other_row, other_column = mapper(row, column)
                here = grid[row][column]
                there = grid[other_row][other_column]
                if here is None or there is None:
                    continue
                checked += 1
                matched += here == there
        return matched / checked if checked else 0.0

    last = steps - 1
    return max(
        share(lambda r, c: (last - r, last - c)),
        share(lambda r, c: (r, last - c)),
        share(lambda r, c: (last - r, c)),
    )


def economy(program: Program) -> float:
    """Какая доля купленного дерева доехала до доски.

    Считается через тот же обратный ход припусков, что и смета (`calc/`):
    другого источника истины про расход быть не должно. Единица — доска
    равна закупке, что физически недостижимо; половина — на доску ушла
    половина дерева.
    """
    from ..calc.material import material_report

    try:
        report = material_report(program)
    except (ValueError, KeyError):
        # Расход не определён — например, щит ни разу не торцован. Это не ноль
        # экономичности, а отсутствие оценки; хуже всего измеримого варианта.
        return 0.0
    if report.raw_volume_mm3 <= 0:
        return 0.0
    return max(0.0, min(1.0, report.board_volume_mm3 / report.raw_volume_mm3))


def _complaint(message: str) -> str:
    """Замечание без чисел и имён деталей — его «род», а не отдельный случай."""
    return re.sub(r"[\d.,]+|[A-Z]+#\S*", "", message)


def feasibility(program: Program, limits: Limits | None = None) -> float:
    """Молчит ли валидатор. Ошибка — ноль, предупреждения снижают плавно.

    Считаются **роды** замечаний, а не их число. Одна и та же жалоба на сорока
    полосах углового узора — это одна проблема, а не сорок; без этого кубы,
    у которых волосяная линия задумана, получали бы оценку неизготовимых.
    Дорогие они, а не невозможные, и за дорого отвечает экономичность.
    """
    issues = list(program.validate())
    if any(issue.level == "error" for issue in issues):
        return 0.0
    try:
        issues += inspect(program, program.run(), limits)
    except (ValueError, KeyError):
        return 0.0
    if any(issue.level == "error" for issue in issues):
        return 0.0
    kinds = {_complaint(issue.message) for issue in issues if issue.level == "warning"}
    return 1.0 / (1.0 + 0.25 * len(kinds))


def score(
    program: Program,
    catalogue: dict[str, Species] | None = None,
    limits: Limits | None = None,
) -> Scores:
    """Все пять мер разом.

    Неисполнимая программа — не ноль по всем мерам, а ноль по реализуемости
    и отсутствие остальных: мерить контраст у того, что не собирается,
    бессмысленно.
    """
    catalogue = catalogue if catalogue is not None else load_species()
    workable = feasibility(program, limits)
    if workable <= 0.0:
        return Scores(0.0, 0.0, 0.0, 0.0, 0.0)

    grid = species_grid(program)
    return Scores(
        contrast=contrast(grid, catalogue),
        rhythm=rhythm(grid),
        symmetry=symmetry(grid),
        economy=economy(program),
        feasibility=workable,
    )


__all__ = [
    "GRID_STEPS",
    "REFERENCE_DELTA_E",
    "Scores",
    "Weights",
    "contrast",
    "economy",
    "feasibility",
    "rhythm",
    "score",
    "species_grid",
    "symmetry",
]
