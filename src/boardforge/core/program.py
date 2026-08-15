"""Программа: последовательность операций, её проверка и исполнение.

Состояние — именованный набор заготовок (Р9). Заготовка живёт в одном из двух
состояний: щит (одна деталь) или пачка деталей после реза. Рез переводит из
первого во второе под тем же именем, склейка заводит новое имя.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from . import geometry
from .ops import (
    Assemble,
    Crop,
    Crosscut,
    Cut,
    Glue,
    Operation,
    StandOnEnd,
    op_from_dict,
    op_to_dict,
    target_of,
)
from .piece import Billet, Part
from .units import EPS

SCHEMA_VERSION = 2


class ProgramError(ValueError):
    """Программу нельзя исполнить."""


@dataclass(frozen=True, slots=True)
class Issue:
    """Замечание валидатора. `index` — номер операции, None для программы целиком."""

    level: str
    message: str
    index: int | None = None

    def __str__(self) -> str:
        where = "" if self.index is None else f"операция {self.index + 1}: "
        return f"{where}{self.message}"


@dataclass(frozen=True, slots=True)
class CutYield:
    """Выход деталей из одного реза — исходные данные для расчёта материала."""

    billet: str
    step_mm: float
    angle_deg: float
    count: int
    remainder_mm: float
    source_length_mm: float
    waste_mm2: float = 0.0
    """Площадь материала, не попавшего ни в одну полосу.

    Из `remainder_mm` не выводится: при угловом резе отход клиновидный.
    """
    op_index: int = -1
    """Номер операции реза в программе — по нему замечания привязываются к месту."""


@dataclass(frozen=True, slots=True)
class Execution:
    """Результат исполнения программы."""

    board: Part
    cuts: tuple[CutYield, ...]
    billets: dict[str, Billet] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Frame:
    """Что лежит на верстаке сразу после операции.

    Отличается от `_Snapshot` назначением, а не составом: снимок — внутренний
    кэш исполнения, кадр — то, что показывают человеку. Отсюда `operation`
    и `target`: инструкции надо не только состояние, но и чем оно получено
    и на какую заготовку смотреть.
    """

    index: int
    operation: Operation
    billets: dict[str, Billet]
    target: str
    """Имя заготовки, которой коснулась операция."""

    @property
    def parts(self) -> Billet:
        """Детали заготовки, над которой работали: щит — одна, после реза — пачка."""
        return self.billets[self.target]


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """Состояние исполнения после префикса программы — то, что кладём в кэш.

    Всё внутри неизменяемо: заготовки это кортежи деталей, детали заморожены,
    полигоны shapely тоже. Поэтому снимок отдаётся наружу как есть, а копируется
    только сам словарь заготовок — его исполнение дополняет.
    """

    billets: dict[str, Billet]
    crosscut_steps: dict[str, float]
    cuts: tuple[CutYield, ...]


_CACHE: OrderedDict[tuple[Operation, ...], _Snapshot] = OrderedDict()
_CACHE_LIMIT = 64
"""Сколько префиксов помним. Правка последней операции не должна пересчитывать
всю программу — ради этого кэш и заведён (см. architecture.md)."""


def clear_cache() -> None:
    """Забыть посчитанное. Нужна тестам, которые меряют время исполнения."""
    _CACHE.clear()


def cache_size() -> int:
    """Сколько префиксов сейчас в кэше."""
    return len(_CACHE)


def _remember(prefix: tuple[Operation, ...], snapshot: _Snapshot) -> None:
    _CACHE[prefix] = snapshot
    _CACHE.move_to_end(prefix)
    while len(_CACHE) > _CACHE_LIMIT:
        _CACHE.popitem(last=False)


def _longest_cached(operations: tuple[Operation, ...]) -> tuple[int, _Snapshot | None]:
    """Самый длинный уже посчитанный префикс программы."""
    for length in range(len(operations), 0, -1):
        snapshot = _CACHE.get(operations[:length])
        if snapshot is not None:
            _CACHE.move_to_end(operations[:length])
            return length, snapshot
    return 0, None


@dataclass(slots=True)
class _BilletState:
    """Что валидатор знает о заготовке, не считая геометрии."""

    is_stack: bool
    last_op: str
    stood: bool
    glues: tuple[int, ...] = ()
    """Номера операций `Glue`, из которых в итоге набран материал заготовки."""
    cut_angle_deg: float | None = None
    """Угол последнего реза; None, если заготовку после реза уже склеили."""


def _cycle_repeats(species: tuple[str, ...]) -> int:
    """Сколько раз породный набор повторяет сам себя.

    Набор `A B C A B C` — два повтора цикла длиной три; `A B C A B` — один,
    потому что целым числом циклов не выражается.
    """
    total = len(species)
    for length in range(1, total // 2 + 1):
        if total % length == 0 and all(
            species[i] == species[i % length] for i in range(total)
        ):
            return total // length
    return 1


@dataclass(frozen=True, slots=True)
class Program:
    """Проект: список операций. Узор и расчёты выводятся из него."""

    operations: tuple[Operation, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))

    def validate(self) -> list[Issue]:
        """Разбор программы: ошибки и предупреждения, а не «да/нет»."""
        issues: list[Issue] = []
        if not self.operations:
            return [Issue("error", "программа пуста")]
        if not isinstance(self.operations[0], Glue):
            issues.append(Issue("error", "программа должна начинаться с Glue", 0))

        states: dict[str, _BilletState] = {}

        for index, op in enumerate(self.operations):
            match op:
                case Glue():
                    if op.id in states:
                        issues.append(
                            Issue("error", f"заготовка {op.id} уже заведена", index)
                        )
                    states[op.id] = _BilletState(False, "glue", False, glues=(index,))

                case Crosscut():
                    state = self._require(states, op.source, issues, index)
                    if state is not None:
                        if state.is_stack:
                            issues.append(
                                Issue(
                                    "error",
                                    f"заготовка {op.source} уже разрезана: "
                                    "перед резом детали надо склеить в щит",
                                    index,
                                )
                            )
                        if state.stood:
                            issues.append(
                                Issue(
                                    "error",
                                    "торцовка после постановки на торец бессмысленна: "
                                    "волокна уже вертикальны",
                                    index,
                                )
                            )
                        state.is_stack = True
                        state.last_op = "crosscut"
                        state.cut_angle_deg = 90.0

                case StandOnEnd():
                    state = self._require(states, op.source, issues, index)
                    if state is not None:
                        if state.stood:
                            issues.append(
                                Issue(
                                    "error",
                                    f"заготовку {op.source} уже ставили на торец",
                                    index,
                                )
                            )
                        if state.last_op != "crosscut":
                            issues.append(
                                Issue(
                                    "error",
                                    "на торец ставят сразу после торцовки, иначе "
                                    "ячейки не занимают весь шаг реза",
                                    index,
                                )
                            )
                        state.stood = True
                        state.last_op = "stand_on_end"

                case Cut():
                    state = self._require(states, op.source, issues, index)
                    if state is not None:
                        if not state.stood:
                            issues.append(
                                Issue(
                                    "error",
                                    "рез под углом возможен только после StandOnEnd: "
                                    "до него угол задаёт направление волокон, "
                                    "а не узор",
                                    index,
                                )
                            )
                        if state.is_stack:
                            issues.append(
                                Issue(
                                    "error",
                                    f"заготовка {op.source} уже разрезана: "
                                    "перед резом детали надо склеить в щит",
                                    index,
                                )
                            )
                        state.is_stack = True
                        state.last_op = "cut"
                        state.cut_angle_deg = op.angle_deg

                case Assemble():
                    self._check_assemble(op, states, issues, index)

                case Crop():
                    state = self._require(states, op.source, issues, index)
                    if state is not None:
                        if state.is_stack:
                            issues.append(
                                Issue(
                                    "error",
                                    "обрезать можно только собранный щит",
                                    index,
                                )
                            )
                        state.last_op = "crop"

        result = target_of(self.operations[-1])
        final = states.get(result)
        if final is None or final.is_stack:
            issues.append(
                Issue(
                    "error",
                    f"программа должна заканчиваться собранным щитом, "
                    f"а заготовка {result} осталась россыпью деталей",
                )
            )
        if not any(state.stood for state in states.values()):
            issues.append(
                Issue("warning", "в программе нет StandOnEnd — это не торцевая доска")
            )
        return issues

    @staticmethod
    def _require(
        states: dict[str, _BilletState],
        name: str,
        issues: list[Issue],
        index: int,
    ) -> _BilletState | None:
        state = states.get(name)
        if state is None:
            issues.append(Issue("error", f"заготовка {name} ещё не заведена", index))
        return state

    def _check_assemble(
        self,
        op: Assemble,
        states: dict[str, _BilletState],
        issues: list[Issue],
        index: int,
    ) -> None:
        if op.id in states:
            issues.append(Issue("error", f"заготовка {op.id} уже заведена", index))

        stood_flags: set[bool] = set()
        glues: tuple[int, ...] = ()
        for ref in op.pieces:
            state = states.get(ref.billet)
            if state is None:
                issues.append(
                    Issue("error", f"заготовка {ref.billet} ещё не заведена", index)
                )
                continue
            if not state.is_stack and ref.index != 0:
                issues.append(
                    Issue(
                        "error",
                        f"заготовка {ref.billet} не разрезана, "
                        f"у неё есть только деталь 0, а не {ref.index}",
                        index,
                    )
                )
            stood_flags.add(state.stood)
            glues += tuple(item for item in state.glues if item not in glues)

        self._check_mirrored_composition(op, states, issues, index)

        if len(stood_flags) > 1:
            issues.append(
                Issue(
                    "error",
                    "в один щит попали детали и с торца, и с пласти: "
                    "у них разный смысл третьего измерения",
                    index,
                )
            )

        states[op.id] = _BilletState(False, "assemble", any(stood_flags), glues=glues)

    def _check_mirrored_composition(
        self,
        op: Assemble,
        states: dict[str, _BilletState],
        issues: list[Issue],
        index: int,
    ) -> None:
        """Хватает ли щиту породных циклов, чтобы зеркальный узор сошёлся.

        Ограничение состава щита, а не узора, поэтому замечание вешается
        на `Glue`, а не на склейку. Проверяется статически: исполнить такую
        программу можно, она просто соберётся с дырами на швах, и заметить это
        по превью нельзя — там будет не ошибка, а пустое место.
        """
        if not op.flipped or not any(op.flipped):
            return

        angled = {
            ref.billet
            for ref in op.pieces
            if (state := states.get(ref.billet)) is not None
            and state.cut_angle_deg is not None
            and abs(state.cut_angle_deg - 90.0) > EPS
        }
        if not angled:
            return

        reported: set[int] = set()
        for name in angled:
            for glue_index in states[name].glues:
                source = self.operations[glue_index]
                if glue_index in reported or not isinstance(source, Glue):
                    continue
                reported.add(glue_index)

                species = tuple(strip.species for strip in source.strips)
                if len(set(species)) < 2 or _cycle_repeats(species) > 1:
                    continue

                issues.append(
                    Issue(
                        "warning",
                        f"щит {source.id} набран одним породным циклом, "
                        f"а полосы из него склеиваются зеркально под углом. "
                        f"Сдвиг ряда переносится на период узора, и переносить "
                        f"его будет не на что: часть швов останется без "
                        f"материала. Повтори набор реек хотя бы дважды",
                        glue_index,
                    )
                )

    @property
    def errors(self) -> list[Issue]:
        """Только ошибки, без предупреждений."""
        return [issue for issue in self.validate() if issue.level == "error"]

    def run(self) -> Execution:
        """Исполнить программу: доска плюс данные о выходе деталей из резов.

        Результат каждого префикса кэшируется, поэтому правка последней операции
        не пересчитывает всю программу — а в редакторе правят именно последнюю.
        """
        errors = self.errors
        if errors:
            listing = "; ".join(str(issue) for issue in errors)
            raise ProgramError(f"программа неисполнима: {listing}")

        done, snapshot = _longest_cached(self.operations)
        if snapshot is not None:
            billets = dict(snapshot.billets)
            crosscut_steps = dict(snapshot.crosscut_steps)
            cuts = list(snapshot.cuts)
        else:
            billets = {}
            crosscut_steps = {}
            cuts = []

        for op_index, op in enumerate(self.operations):
            if op_index < done:
                continue
            self._advance(op, op_index, billets, crosscut_steps, cuts)
            _remember(
                self.operations[: op_index + 1],
                _Snapshot(dict(billets), dict(crosscut_steps), tuple(cuts)),
            )

        result = target_of(self.operations[-1])
        return Execution(billets[result][0], tuple(cuts), billets)

    def trace(self) -> "list[Frame]":
        """Состояние заготовок после каждой операции — по кадру на операцию.

        Нужна пошаговой инструкции: столяр видит не только готовую доску,
        но и то, что лежит на верстаке после третьего реза. Кадры берутся
        из **того же** исполнения, что и `run()` — через общий `_advance`,
        а не через вторую копию цикла: разойдись они, инструкция описывала бы
        не ту доску, которую считает смета.

        Префиксный кэш здесь намеренно не используется: он умеет отдать
        состояние только на конце запомненного префикса, а кадры нужны все.
        Цена — полный прогон, но инструкцию печатают, а не крутят в редакторе.
        """
        errors = self.errors
        if errors:
            listing = "; ".join(str(issue) for issue in errors)
            raise ProgramError(f"программа неисполнима: {listing}")

        billets: dict[str, Billet] = {}
        crosscut_steps: dict[str, float] = {}
        cuts: list[CutYield] = []
        frames = []
        for op_index, op in enumerate(self.operations):
            self._advance(op, op_index, billets, crosscut_steps, cuts)
            frames.append(Frame(op_index, op, dict(billets), target_of(op)))
        return frames

    def _advance(
        self,
        op: Operation,
        op_index: int,
        billets: dict[str, Billet],
        crosscut_steps: dict[str, float],
        cuts: list[CutYield],
    ) -> None:
        """Применить одну операцию к состоянию исполнения.

        Единственное место, где написано, что делает каждая операция. И `run`,
        и `trace` идут через него — второй такой петли в модуле быть не должно.
        """
        match op:
            case Glue():
                billets[op.id] = (
                    geometry.glue(op.strips, op.length_mm, op.thickness_mm, op.id),
                )

            case Crosscut():
                source = billets[op.source][0]
                sliced = geometry.slice_part(source, 90.0, op.step_mm, along_strip=True)
                billets[op.source] = tuple(sliced.parts)
                crosscut_steps[op.source] = op.step_mm
                cuts.append(
                    CutYield(
                        op.source,
                        op.step_mm,
                        90.0,
                        len(sliced.parts),
                        sliced.remainder_mm,
                        source.length_mm,
                        sliced.waste_mm2,
                        op_index,
                    )
                )

            case StandOnEnd():
                step = crosscut_steps[op.source]
                billets[op.source] = tuple(
                    geometry.stand_on_end(part, step) for part in billets[op.source]
                )

            case Cut():
                source = billets[op.source][0]
                sliced = geometry.slice_part(source, op.angle_deg, op.step_mm)
                billets[op.source] = tuple(sliced.parts)
                cuts.append(
                    CutYield(
                        op.source,
                        op.step_mm,
                        op.angle_deg,
                        len(sliced.parts),
                        sliced.remainder_mm,
                        source.width_mm,
                        sliced.waste_mm2,
                        op_index,
                    )
                )

            case Assemble():
                selected = [self._resolve(billets, ref) for ref in op.pieces]
                billets[op.id] = (
                    geometry.assemble(selected, op.reversed, op.offsets_mm, op.flipped),
                )

            case Crop():
                billets[op.source] = (
                    geometry.crop(
                        billets[op.source][0], op.left, op.right, op.top, op.bottom
                    ),
                )

    @staticmethod
    def _resolve(billets: dict[str, Billet], ref: Any) -> Part:
        parts = billets[ref.billet]
        if ref.index >= len(parts):
            raise ProgramError(
                f"деталь {ref} не существует: в заготовке {ref.billet} "
                f"их всего {len(parts)}"
            )
        return parts[ref.index]

    def apply(self) -> Part:
        """Исполнить программу и вернуть доску."""
        return self.run().board

    def to_dict(self) -> dict[str, Any]:
        """Программа в словарь для JSON."""
        return {
            "schema_version": self.schema_version,
            "operations": [op_to_dict(op) for op in self.operations],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Program":
        """Программа из словаря. Старые версии схемы поднимаются миграциями."""
        from .migrations import migrate

        data = migrate(data)
        operations = tuple(op_from_dict(item) for item in data["operations"])
        return cls(operations=operations, schema_version=data["schema_version"])


def program(*operations: Operation) -> Program:
    """Короткая запись для тестов и генераторов."""
    return Program(operations=operations)


__all__ = [
    "SCHEMA_VERSION",
    "CutYield",
    "Execution",
    "Issue",
    "Program",
    "ProgramError",
    "cache_size",
    "clear_cache",
    "program",
]
