"""Предупреждения о породах: то, что видно не в геометрии, а в справочнике.

Отдельно от `core/safety.py` намеренно. Там — изготовимость: та же программа
с любым справочником даёт ту же геометрию, и опасность клина от пород не
зависит. Здесь наоборот: геометрия ни при чём, всё решает, какое дерево
поставили рядом. Поэтому и живёт в `calc/`, рядом со сметой, а не в ядре.

В оценку узора эти замечания не входят. Реализуемость (`core/fitness.py`) — про
то, соберётся ли доска; породы собираются любые. Смешать одно с другим значит
заставить генератор избегать вишни с грабом так же, как неизготовимого клина.

## Порог по короблению

Разница тангенциальной усушки соседних реек — та величина, что рвёт шов при
смене влажности: рейки сохнут и разбухают на разную долю, а склеены намертво.

Порог **3.0 процентных пункта** подобран по данным, а не назначен. Якорь —
клён с орехом: на нём стоит половина всех торцевых досок в мире, разница
у пары 2.1, и предупреждение, которое ругается на неё, читать перестанут.
Порог обязан лежать выше. Сверху его держит вишня с дубом (3.4) и вишня
с грабом (4.4) — пары, которые действительно ведут себя хуже.

На библиотеке из 14 узоров порог 3.0 срабатывает на трёх (`brick`, `basket`,
`ladder`). Для сравнения: 2.0 срабатывает на одиннадцати из четырнадцати,
2.5 — на восьми, 3.5 — на одном. Проверка зафиксирована тестом: уедет вниз —
предупреждение обесценится, уедет вверх — замолчит совсем.
"""

from dataclasses import dataclass

from ..core.ops import Glue
from ..core.program import Issue, Program
from ..core.species import Species, load_species

MAX_SHRINKAGE_GAP = 3.0
"""Допустимая разница тангенциальной усушки соседних реек, процентных пунктов."""


@dataclass(frozen=True, slots=True)
class WoodLimits:
    """Пороги по дереву. Как и пороги цеха — параметры, а не числа в коде."""

    max_shrinkage_gap: float = MAX_SHRINKAGE_GAP

    def __post_init__(self) -> None:
        if self.max_shrinkage_gap <= 0:
            raise ValueError("порог разницы усушки должен быть положительным")


def _names(catalogue: dict[str, Species], keys: list[str]) -> str:
    return ", ".join(catalogue[key].name for key in keys)


def _glued_neighbours(prog: Program) -> list[tuple[int, str, str]]:
    """Пары пород, склеенных кромка-к-кромке, с номером операции склейки.

    Только соседи внутри щита: у них общий шов во всю длину рейки, и разница
    в подвижках работает именно на нём. Ячейки, встретившиеся на шве между
    полосами, склеены торцами — там шов короткий и подвижка вдоль волокон,
    а она на порядок меньше поперечной.
    """
    found: list[tuple[int, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, op in enumerate(prog.operations):
        if not isinstance(op, Glue):
            continue
        species = [strip.species for strip in op.strips]
        for first, second in zip(species, species[1:], strict=False):
            if first == second:
                continue
            key = (first, second) if first < second else (second, first)
            if key in seen:
                continue
            seen.add(key)
            found.append((index, *key))
    return found


def _species_used(prog: Program) -> list[str]:
    """Породы доски в устойчивом порядке — по первому появлению в программе."""
    order: dict[str, None] = {}
    for op in prog.operations:
        if isinstance(op, Glue):
            for strip in op.strips:
                order.setdefault(strip.species, None)
    return list(order)


def shrinkage_issues(
    prog: Program,
    catalogue: dict[str, Species] | None = None,
    limits: WoodLimits | None = None,
) -> list[Issue]:
    """Пары соседних реек, чья разница усушки грозит швом."""
    catalogue = catalogue if catalogue is not None else load_species()
    limits = limits or WoodLimits()

    issues: list[Issue] = []
    for index, first, second in _glued_neighbours(prog):
        if first not in catalogue or second not in catalogue:
            continue
        one, other = catalogue[first], catalogue[second]
        gap = abs(one.shrinkage_tangential - other.shrinkage_tangential)
        if gap <= limits.max_shrinkage_gap:
            continue
        issues.append(
            Issue(
                "warning",
                f"{one.name} и {other.name} стоят в щите рядом, а усыхают "
                f"по-разному: {one.shrinkage_tangential:.1f}% против "
                f"{other.shrinkage_tangential:.1f}%, разница {gap:.1f}. "
                f"При смене влажности шов между ними работает сильнее прочих — "
                f"выдержи обе породы в мастерской до одной влажности перед "
                f"склейкой и держи готовую доску подальше от батареи",
                index,
            )
        )
    return issues


def species_issues(
    prog: Program,
    catalogue: dict[str, Species] | None = None,
    limits: WoodLimits | None = None,
) -> list[Issue]:
    """Всё, что стоит знать о выбранных породах, одним списком.

    Каждый признак даёт **одно** замечание на все породы разом, а не по одному
    на породу: три строки про три аллергена — это способ добиться, чтобы список
    замечаний перестали читать.
    """
    catalogue = catalogue if catalogue is not None else load_species()
    used = [key for key in _species_used(prog) if key in catalogue]

    issues = shrinkage_issues(prog, catalogue, limits)

    porous = [key for key in used if catalogue[key].open_pores]
    if porous:
        issues.append(
            Issue(
                "warning",
                f"крупные поры: {_names(catalogue, porous)}. На торце поры "
                f"открыты вверх и держат влагу и остатки пищи; для разделочной "
                f"поверхности такие породы не берут. Если берёшь — только "
                f"под масло с воском и не в рабочую зону",
            )
        )

    allergens = [key for key in used if catalogue[key].allergen]
    if allergens:
        issues.append(
            Issue(
                "warning",
                f"пыль раздражает кожу и дыхание: {_names(catalogue, allergens)}. "
                f"Шлифуй в респираторе и с вытяжкой. На готовой доске под маслом "
                f"это уже не важно — важно, пока пилишь",
            )
        )

    fading = [key for key in used if catalogue[key].fades]
    if fading:
        issues.append(
            Issue(
                "warning",
                f"цвет со временем изменится: {_names(catalogue, fading)}. "
                f"Через год-другой узор будет не тот, что на превью: падук "
                f"буреет, амарант выцветает, вишня темнеет. Это не дефект, "
                f"но покупателю об этом лучше сказать заранее",
            )
        )
    return issues


__all__ = [
    "MAX_SHRINKAGE_GAP",
    "WoodLimits",
    "shrinkage_issues",
    "species_issues",
]
