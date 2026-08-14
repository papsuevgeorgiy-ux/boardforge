"""Одномерный раскрой: рейки из досок стандартной длины.

Задача та, что стоит перед походом в магазин. Рейки известны — их выдала карта
раскроя, каждая со своей длиной. Доски продаются мерными: два, два с половиной,
три метра. Вопрос — сколько досок какой длины взять, чтобы обрезков осталось
поменьше.

## Что здесь одномерно, а что упрощено

Режется **длина**. Ширину рейки получают роспуском доски вдоль, и в модели
этого нет: считается, что доска нужной толщины достаточно широка, чтобы из неё
вышла рейка нужной ширины. Упрощение осознанное — задача роспуска двумерная,
а двумерный раскрой на неделю не помещается. Что оно означает на практике:
план даёт нижнюю оценку по метражу, и реальная закупка будет не меньше.

Толщина в модели есть: доски разной толщины — разный товар, и смешивать их
в одну кучу нельзя. Поэтому рейки группируются по паре «порода и толщина».

## Почему FFD, а не оптимум

Раскрой в одномерном виде — задача об упаковке в контейнеры, она NP-трудна,
и точный ответ на сотне реек считается неприлично долго. FFD (первый
подходящий, по убыванию длины) даёт результат, который **видно глазами**:
берём самую длинную рейку, кладём в первую доску, где она помещается, не
поместилась нигде — берём новую доску. Столяр делает ровно так же.

Локальный поиск сверху — тот же FFD, но с переставленным порядком реек; лучший
результат запоминается. Он не превращает решение в оптимум, а подчищает
случаи, где жадность промахнулась на одну доску. Улучшение всегда объяснимо:
это по-прежнему FFD, просто с другого конца.

## Воспроизводимость

При заданном сиде и не исчерпанном бюджете времени план один и тот же. Если
бюджет кончился раньше перебора, `stopped_early` говорит об этом прямо —
молча отдать другой ответ на другой машине хуже, чем отдать худший.
"""

import random
import time
from dataclasses import dataclass

from .cutlist import CutList

STANDARD_LENGTHS_MM = (2000.0, 2500.0, 3000.0, 4000.0)
"""Мерные длины пиломатериала, которые есть почти везде."""

DEFAULT_TRIES = 200
DEFAULT_BUDGET_S = 1.0


@dataclass(frozen=True, slots=True)
class Demand:
    """Одна рейка, которую надо выкроить."""

    number: str
    species: str
    thickness_mm: float
    length_mm: float

    @property
    def kind(self) -> tuple[str, float]:
        """Товар, из которого её кроят: порода и толщина."""
        return (self.species, self.thickness_mm)


@dataclass(frozen=True, slots=True)
class StockBoard:
    """Купленная доска и что из неё выходит."""

    species: str
    thickness_mm: float
    length_mm: float
    parts: tuple[Demand, ...]
    kerf_mm: float

    @property
    def used_mm(self) -> float:
        """Длина, ушедшая в рейки, вместе с пропилами между ними."""
        cuts = max(0, len(self.parts) - 1)
        return sum(part.length_mm for part in self.parts) + cuts * self.kerf_mm

    @property
    def offcut_mm(self) -> float:
        """Остаток доски после последнего реза."""
        return self.length_mm - self.used_mm

    @property
    def numbers(self) -> str:
        """Номера реек из этой доски — так и пишут на самой доске карандашом."""
        return ", ".join(part.number for part in self.parts)


@dataclass(frozen=True, slots=True)
class NestingPlan:
    """Что купить и как это распилить."""

    boards: tuple[StockBoard, ...]
    kerf_mm: float
    tries: int
    """Сколько порядков реек перебрано — суммарно по всем товарам."""
    improvements: int
    """Сколько раз перестановка выиграла у чистого FFD.

    Ноль — обычное дело и не признак неработающего поиска: рейки одного щита
    все одной длины, а на одинаковых длинах перестановка ничего не меняет
    и FFD уже оптимален. Выигрыш появляется там, где щитов несколько
    и длины у них разные."""
    stopped_early: bool
    seconds: float

    @property
    def total_length_mm(self) -> float:
        """Метраж закупки — величина, за которую платят."""
        return sum(board.length_mm for board in self.boards)

    @property
    def offcut_mm(self) -> float:
        """Сколько длины уйдёт в обрезки."""
        return sum(board.offcut_mm for board in self.boards)

    @property
    def offcut_share(self) -> float:
        """Доля метража, уходящая в обрезки."""
        total = self.total_length_mm
        return self.offcut_mm / total if total else 0.0

    def of_kind(self, species: str, thickness_mm: float) -> tuple[StockBoard, ...]:
        """Доски одного товара."""
        return tuple(
            board
            for board in self.boards
            if board.species == species and abs(board.thickness_mm - thickness_mm) < 1e-9
        )

    @property
    def shopping_list(self) -> tuple[tuple[str, float, float, int], ...]:
        """Список в магазин: порода, толщина, длина, сколько досок."""
        counts: dict[tuple[str, float, float], int] = {}
        for board in self.boards:
            key = (board.species, board.thickness_mm, board.length_mm)
            counts[key] = counts.get(key, 0) + 1
        return tuple(
            (species, thickness, length, count)
            for (species, thickness, length), count in sorted(counts.items())
        )


def demands_of(listing: CutList) -> tuple[Demand, ...]:
    """Рейки закупки из карты раскроя — вход одномерной задачи."""
    return tuple(
        Demand(
            number=item.number,
            species=item.species,
            thickness_mm=item.thickness_mm,
            length_mm=item.length_mm,
        )
        for item in listing.stock
    )


def _pack(items: list[Demand], length_mm: float, kerf_mm: float) -> list[StockBoard]:
    """Первый подходящий: кладём рейку в первую доску, где она помещается."""
    shelves: list[list[Demand]] = []
    filled: list[float] = []

    for item in items:
        for index, used in enumerate(filled):
            addition = item.length_mm + (kerf_mm if shelves[index] else 0.0)
            if used + addition <= length_mm + 1e-9:
                shelves[index].append(item)
                filled[index] = used + addition
                break
        else:
            shelves.append([item])
            filled.append(item.length_mm)

    return [
        StockBoard(
            species=shelf[0].species,
            thickness_mm=shelf[0].thickness_mm,
            length_mm=length_mm,
            parts=tuple(shelf),
            kerf_mm=kerf_mm,
        )
        for shelf in shelves
    ]


def _cost(boards: list[StockBoard]) -> tuple[float, int]:
    """Чем план лучше: сперва метраж, при равенстве — меньше досок в руках."""
    return (sum(board.length_mm for board in boards), len(boards))


def _best_for_kind(
    items: list[Demand],
    lengths: tuple[float, ...],
    kerf_mm: float,
    tries: int,
    deadline: float,
    rng: random.Random,
) -> tuple[list[StockBoard], int, int, bool]:
    """Лучший план для одного товара: FFD по каждой мерной длине плюс перестановки."""
    usable = [length for length in lengths if length >= max(i.length_mm for i in items)]
    if not usable:
        longest = max(item.length_mm for item in items)
        raise ValueError(
            f"рейка длиной {longest:.0f} мм не выходит ни из одной мерной доски "
            f"(самая длинная {max(lengths):.0f} мм) — возьми щит короче или "
            f"склей рейку по длине"
        )

    ordered = sorted(items, key=lambda item: -item.length_mm)

    def sweep(order: list[Demand]) -> list[StockBoard]:
        """Лучшая мерная длина при этом порядке реек."""
        return min((_pack(order, length, kerf_mm) for length in usable), key=_cost)

    # Чистый FFD — то, с чем сравнивается всё остальное. Он же ответ, если
    # перестановки ничего не дадут: план обязан быть не хуже жадного.
    best = sweep(ordered)
    attempts = 1
    improvements = 0
    stopped = False

    while attempts < tries:
        if time.perf_counter() > deadline:
            stopped = True
            break
        candidate = sweep(_almost_sorted(ordered, rng))
        attempts += 1
        if _cost(candidate) < _cost(best):
            best = candidate
            improvements += 1

    return best, attempts, improvements, stopped


LOOKAHEAD = 3
"""Из скольких самых длинных реек выбирает возмущение."""


def _almost_sorted(ordered: list[Demand], rng: random.Random) -> list[Demand]:
    """Порядок «почти по убыванию»: иногда берём не самую длинную, а вторую.

    Простая перестановка здесь не работала бы вовсе: FFD пересортирует список
    по убыванию, и перемешивание меняло бы только порядок реек одной длины —
    а они взаимозаменяемы, и раскрой от такой перестановки не меняется.
    Соседство должно ломать сам порядок убывания, иначе поиска нет.
    """
    pool = ordered[:]
    order: list[Demand] = []
    while pool:
        order.append(pool.pop(rng.randrange(min(LOOKAHEAD, len(pool)))))
    return order


def nest(
    items: tuple[Demand, ...],
    lengths: tuple[float, ...] = STANDARD_LENGTHS_MM,
    kerf_mm: float = 3.2,
    tries: int = DEFAULT_TRIES,
    budget_s: float = DEFAULT_BUDGET_S,
    seed: int = 0,
) -> NestingPlan:
    """Разложить рейки по мерным доскам."""
    if not items:
        raise ValueError("нечего кроить: список реек пуст")
    if not lengths:
        raise ValueError("не задано ни одной мерной длины")

    started = time.perf_counter()
    deadline = started + budget_s
    rng = random.Random(seed)

    kinds: dict[tuple[str, float], list[Demand]] = {}
    for item in items:
        kinds.setdefault(item.kind, []).append(item)

    boards: list[StockBoard] = []
    attempts = 0
    improvements = 0
    stopped = False
    for _, group in sorted(kinds.items()):
        packed, tried, better, early = _best_for_kind(
            group, tuple(sorted(lengths)), kerf_mm, tries, deadline, rng
        )
        boards.extend(packed)
        attempts += tried
        improvements += better
        stopped = stopped or early

    return NestingPlan(
        boards=tuple(boards),
        kerf_mm=kerf_mm,
        tries=attempts,
        improvements=improvements,
        stopped_early=stopped,
        seconds=time.perf_counter() - started,
    )


def nest_stock(listing: CutList, **options: object) -> NestingPlan:
    """Разложить по доскам то, что заказала карта раскроя."""
    return nest(demands_of(listing), **options)  # type: ignore[arg-type]


__all__ = [
    "DEFAULT_BUDGET_S",
    "DEFAULT_TRIES",
    "STANDARD_LENGTHS_MM",
    "Demand",
    "NestingPlan",
    "StockBoard",
    "demands_of",
    "nest",
    "nest_stock",
]
