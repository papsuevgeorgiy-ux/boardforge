"""Генератор в пространстве программ: случайный и эволюционный.

Генерируется не картинка, а **геном** — имя шаблона библиотеки, набор пород
и значения параметров. Программа из него выводится, поэтому неизготовимый узор
получить нельзя по построению: шаблоны библиотеки законны, а параметры
проверяются валидатором до того, как результат отдан наружу.

Один сид — один узор. Не «похожий», а тот же самый: `random.Random(seed)`
и никаких обращений ко времени, множествам без порядка и адресам объектов.
Породы выбираются из **отсортированного** списка справочника по той же
причине — порядок словаря приходит из файла и может измениться.

Отбраковка честная: если геном дал программу, на которую ругается валидатор
или проверка изготовимости, он выбрасывается и берётся следующий. Генератор
не имеет права предлагать то, за что сам же и отчитает.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from .fitness import Scores, Weights, score
from .library import LIBRARY, Pattern
from .program import Program
from .species import Species, load_species

MAX_ATTEMPTS = 40
"""Сколько геномов перебрать, прежде чем признать, что не выходит.

Не бесконечный цикл: с диким набором пород или порогами цеха законного узора
может не быть вовсе, и об этом надо сказать, а не крутиться."""

_INT_RANGES: dict[str, tuple[int, int]] = {
    "columns": (10, 20),
    "rows": (8, 16),
    "width": (2, 4),
    "arm": (2, 5),
    "gap": (3, 7),
    "run": (3, 6),
    "step": (1, 3),
    "thickness": (1, 2),
    "repeats": (4, 7),
}
"""Границы целых параметров. Не вкус: за ними узор либо вырождается
(один столбец), либо доска перестаёт быть доской (сорок рядов по 40 мм)."""

_CELL_RANGE = (26.0, 44.0)
"""Ячейка мельче 26 мм даёт деталь, которую опасно вести по станку, крупнее
44 — узор из десятка пятен. Оба края проверяются валидатором, здесь просто
не тратим на них попытки."""

_ANGLES = (35.0, 40.0, 45.0, 50.0, 55.0, 60.0)
"""Углы реза кратны пяти: столяр выставляет угломер, а не решает уравнение."""


@dataclass(frozen=True, slots=True)
class Genome:
    """Что именно сгенерировано: шаблон и его параметры.

    Хранится отдельно от программы, потому что мутировать удобно его, а не
    двадцать операций. Программа — производная, как и всё в проекте.
    """

    template: str
    params: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        if self.template not in LIBRARY:
            raise ValueError(f"нет такого шаблона: {self.template!r}")
        object.__setattr__(self, "params", tuple(sorted(self.params)))

    @property
    def values(self) -> dict[str, Any]:
        """Параметры словарём."""
        return dict(self.params)

    def with_values(self, **changes: Any) -> "Genome":
        """Тот же геном с изменёнными параметрами."""
        return replace(self, params=tuple(sorted({**self.values, **changes}.items())))

    def pattern(self) -> Pattern:
        """Собрать узор."""
        return LIBRARY[self.template](**self.values)

    def program(self) -> Program:
        """Собрать программу."""
        return self.pattern().program


def _species_pool(catalogue: dict[str, Species]) -> list[str]:
    """Породы в устойчивом порядке: воспроизводимость важнее удобства."""
    return sorted(catalogue)


def _pick_species(rng: random.Random, pool: Sequence[str], count: int) -> tuple[str, ...]:
    """Несколько разных пород. Повтор в наборе — это узор из меньшего числа
    пород, притворяющийся более сложным, и генератору он не нужен."""
    if count > len(pool):
        raise ValueError(f"в справочнике {len(pool)} пород, а узору нужно {count} разных")
    return tuple(rng.sample(list(pool), count))


def random_genome(
    rng: random.Random, catalogue: dict[str, Species], template: str | None = None
) -> Genome:
    """Случайный геном: шаблон, породы и все его параметры."""
    pool = _species_pool(catalogue)
    key = template if template is not None else rng.choice(sorted(LIBRARY))
    defaults = dict(LIBRARY[key].defaults)

    values: dict[str, Any] = {}
    for name, value in defaults.items():
        if name == "species":
            values[name] = _pick_species(rng, pool, len(value))
        elif name in ("cell_mm", "side_mm"):
            values[name] = round(rng.uniform(*_CELL_RANGE), 1)
        elif name == "angle_deg":
            values[name] = rng.choice(_ANGLES)
        elif name in _INT_RANGES:
            values[name] = rng.randint(*_INT_RANGES[name])
        else:
            values[name] = value
    return Genome(key, tuple(values.items()))


def mutate(genome: Genome, rng: random.Random, catalogue: dict[str, Species]) -> Genome:
    """Одна правка генома: состав щита, угол, шаг, сдвиг или зеркало.

    Мутирует ровно один параметр за раз. Мутировать несколько — значит
    потерять связь между правкой и её ценой, а вместе с ней и смысл отбора.
    """
    pool = _species_pool(catalogue)
    values = genome.values
    knobs = [name for name in values if name != "species"] + ["species", "species"]
    # Породы попадают в список дважды: смена дерева меняет доску сильнее
    # любого числа, и отбор без неё быстро упирается в один набор.
    name = rng.choice(sorted(knobs))

    if name == "species":
        current = list(values["species"])
        spare = [key for key in pool if key not in current]
        if not spare:
            return genome
        current[rng.randrange(len(current))] = rng.choice(spare)
        return genome.with_values(species=tuple(current))
    if name in ("cell_mm", "side_mm"):
        low, high = _CELL_RANGE
        shifted = values[name] + rng.choice((-4.0, -2.0, 2.0, 4.0))
        return genome.with_values(**{name: round(min(high, max(low, shifted)), 1)})
    if name == "angle_deg":
        return genome.with_values(angle_deg=rng.choice(_ANGLES))
    if name in _INT_RANGES:
        low, high = _INT_RANGES[name]
        shifted = values[name] + rng.choice((-1, 1))
        return genome.with_values(**{name: min(high, max(low, shifted))})
    return genome


def _acceptable(genome: Genome) -> Program | None:
    """Программа генома, если она законна и изготовима; иначе `None`."""
    from .safety import inspect

    try:
        program = genome.program()
    except (ValueError, KeyError, ZeroDivisionError):
        # Крайние параметры дают геометрию, которой не бывает: щит уже реза,
        # обрезка съедает доску целиком. Это законный отказ, а не сбой.
        return None
    if program.errors:
        return None
    try:
        execution = program.run()
    except ValueError:
        return None
    if any(issue.level == "error" for issue in inspect(program, execution)):
        return None
    return program


def generate(
    seed: int,
    catalogue: dict[str, Species] | None = None,
    template: str | None = None,
) -> tuple[Genome, Program]:
    """Случайный изготовимый узор по сиду.

    Возвращает и геном, и программу: геном нужен, чтобы узор можно было
    доработать или показать в интерфейсе, программа — чтобы его сделать.
    """
    catalogue = catalogue if catalogue is not None else load_species()
    rng = random.Random(seed)
    for _ in range(MAX_ATTEMPTS):
        genome = random_genome(rng, catalogue, template)
        program = _acceptable(genome)
        if program is not None:
            return genome, program
    raise ValueError(
        f"за {MAX_ATTEMPTS} попыток не вышло ни одного изготовимого узора. "
        f"Скорее всего слишком строгие пороги цеха или слишком бедный "
        f"справочник пород"
    )


@dataclass(frozen=True, slots=True)
class Evolved:
    """Итог отбора: геном, его программа и оценки."""

    genome: Genome
    program: Program
    scores: Scores

    @property
    def total(self) -> float:
        """Общая оценка по весам по умолчанию."""
        return self.scores.total()


def evolve(
    seed: int,
    generations: int = 6,
    population: int = 8,
    weights: Weights | None = None,
    catalogue: dict[str, Species] | None = None,
    template: str | None = None,
) -> Evolved:
    """Эволюционный режим: мутируем лучших, оставляем лучших.

    Отбор элитарный и без скрещивания. Скрещивать геномы разных шаблонов
    нечего — у кубов и шахматки нет общих параметров, — а внутри одного
    шаблона мутации хватает: пространство маленькое и почти всё осмысленное.
    """
    if generations < 1 or population < 2:
        raise ValueError("нужно хотя бы одно поколение и хотя бы двое в популяции")

    catalogue = catalogue if catalogue is not None else load_species()
    weights = weights or Weights()
    rng = random.Random(seed)

    def rated(genome: Genome) -> Evolved | None:
        program = _acceptable(genome)
        if program is None:
            return None
        return Evolved(genome, program, score(program, catalogue))

    current: list[Evolved] = []
    for _ in range(population * 3):
        if len(current) >= population:
            break
        candidate = rated(random_genome(rng, catalogue, template))
        if candidate is not None:
            current.append(candidate)
    if not current:
        raise ValueError(
            "не удалось собрать стартовую популяцию: ни один случайный узор "
            "не прошёл валидатор"
        )

    for _ in range(generations):
        current.sort(key=lambda item: item.scores.total(weights), reverse=True)
        survivors = current[: max(2, population // 2)]
        children: list[Evolved] = list(survivors)
        for parent in survivors:
            for _ in range(2):
                if len(children) >= population:
                    break
                child = rated(mutate(parent.genome, rng, catalogue))
                if child is not None:
                    children.append(child)
        current = children

    return max(current, key=lambda item: item.scores.total(weights))


__all__ = [
    "MAX_ATTEMPTS",
    "Evolved",
    "Genome",
    "evolve",
    "generate",
    "mutate",
    "random_genome",
]
