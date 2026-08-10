"""Программа: последовательность операций, её проверка и исполнение.

Состояние — именованный набор заготовок (Р9). Заготовка живёт в одном из двух
состояний: щит (одна деталь) или пачка деталей после реза. Рез переводит из
первого во второе под тем же именем, склейка заводит новое имя.
"""

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


@dataclass(frozen=True, slots=True)
class Execution:
    """Результат исполнения программы."""

    board: Part
    cuts: tuple[CutYield, ...]
    billets: dict[str, Billet] = field(default_factory=dict)


@dataclass(slots=True)
class _BilletState:
    """Что валидатор знает о заготовке, не считая геометрии."""

    is_stack: bool
    last_op: str
    stood: bool


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
                    states[op.id] = _BilletState(False, "glue", False)

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

        if len(stood_flags) > 1:
            issues.append(
                Issue(
                    "error",
                    "в один щит попали детали и с торца, и с пласти: "
                    "у них разный смысл третьего измерения",
                    index,
                )
            )

        states[op.id] = _BilletState(False, "assemble", any(stood_flags))

    @property
    def errors(self) -> list[Issue]:
        """Только ошибки, без предупреждений."""
        return [issue for issue in self.validate() if issue.level == "error"]

    def run(self) -> Execution:
        """Исполнить программу: доска плюс данные о выходе деталей из резов."""
        errors = self.errors
        if errors:
            listing = "; ".join(str(issue) for issue in errors)
            raise ProgramError(f"программа неисполнима: {listing}")

        billets: dict[str, Billet] = {}
        crosscut_steps: dict[str, float] = {}
        cuts: list[CutYield] = []

        for op in self.operations:
            match op:
                case Glue():
                    billets[op.id] = (
                        geometry.glue(op.strips, op.length_mm, op.thickness_mm),
                    )

                case Crosscut():
                    source = billets[op.source][0]
                    parts, remainder = geometry.slice_part(source, 90.0, op.step_mm)
                    billets[op.source] = tuple(parts)
                    crosscut_steps[op.source] = op.step_mm
                    cuts.append(
                        CutYield(
                            op.source,
                            op.step_mm,
                            90.0,
                            len(parts),
                            remainder,
                            source.length_mm,
                        )
                    )

                case StandOnEnd():
                    step = crosscut_steps[op.source]
                    billets[op.source] = tuple(
                        geometry.stand_on_end(part, step) for part in billets[op.source]
                    )

                case Cut():
                    source = billets[op.source][0]
                    parts, remainder = geometry.slice_part(
                        source, op.angle_deg, op.step_mm
                    )
                    billets[op.source] = tuple(parts)
                    cuts.append(
                        CutYield(
                            op.source,
                            op.step_mm,
                            op.angle_deg,
                            len(parts),
                            remainder,
                            source.width_mm,
                        )
                    )

                case Assemble():
                    selected = [self._resolve(billets, ref) for ref in op.pieces]
                    billets[op.id] = (
                        geometry.assemble(selected, op.reversed, op.offsets_mm),
                    )

                case Crop():
                    billets[op.source] = (
                        geometry.crop(
                            billets[op.source][0], op.left, op.right, op.top, op.bottom
                        ),
                    )

        result = target_of(self.operations[-1])
        return Execution(billets[result][0], tuple(cuts), billets)

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
    "program",
]
