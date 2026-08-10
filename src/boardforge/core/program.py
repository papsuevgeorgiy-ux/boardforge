"""Программа: последовательность операций, её проверка и исполнение."""

from dataclasses import dataclass
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
)
from .piece import Part

SCHEMA_VERSION = 1


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
            issues.append(Issue("error", "программа пуста"))
            return issues

        parts_count = 0
        stood_on_end = False
        previous: Operation | None = None

        for index, op in enumerate(self.operations):
            if isinstance(op, Glue):
                if index != 0:
                    issues.append(
                        Issue(
                            "error",
                            "склейка щита с нуля возможна только в начале программы",
                            index,
                        )
                    )
                parts_count = 1

            elif index == 0:
                issues.append(Issue("error", "программа должна начинаться с Glue", index))
                parts_count = 1

            if isinstance(op, Crosscut):
                if stood_on_end:
                    issues.append(
                        Issue(
                            "error",
                            "торцовка после постановки на торец бессмысленна: "
                            "волокна уже вертикальны",
                            index,
                        )
                    )
                if parts_count != 1:
                    issues.append(
                        Issue("error", "перед резом детали надо склеить в щит", index)
                    )
                parts_count = 2

            elif isinstance(op, StandOnEnd):
                if stood_on_end:
                    issues.append(
                        Issue("error", "на торец ставят один раз за программу", index)
                    )
                if not isinstance(previous, Crosscut):
                    issues.append(
                        Issue(
                            "error",
                            "на торец ставят сразу после торцовки, иначе ячейки "
                            "не занимают весь шаг реза",
                            index,
                        )
                    )
                stood_on_end = True

            elif isinstance(op, Cut):
                if not stood_on_end:
                    issues.append(
                        Issue(
                            "error",
                            "рез под углом возможен только после StandOnEnd: "
                            "до него угол задаёт направление волокон, а не узор",
                            index,
                        )
                    )
                if parts_count != 1:
                    issues.append(
                        Issue("error", "перед резом детали надо склеить в щит", index)
                    )
                parts_count = 2

            elif isinstance(op, Assemble):
                if parts_count < 2:
                    issues.append(
                        Issue(
                            "error", "склеивать нечего: перед Assemble нужен рез", index
                        )
                    )
                parts_count = 1

            elif isinstance(op, Crop):
                if parts_count != 1:
                    issues.append(
                        Issue("error", "обрезать можно только собранный щит", index)
                    )
                parts_count = 1

            previous = op

        if parts_count != 1:
            issues.append(
                Issue("error", "программа должна заканчиваться собранным щитом")
            )
        if not stood_on_end:
            issues.append(
                Issue(
                    "warning",
                    "в программе нет StandOnEnd — это не торцевая доска",
                )
            )
        return issues

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

        parts: list[Part] = []
        cuts: list[CutYield] = []
        crosscut_step: float | None = None

        for op in self.operations:
            match op:
                case Glue():
                    parts = [geometry.glue(op.strips, op.length_mm, op.thickness_mm)]

                case Crosscut():
                    source_length = parts[0].length_mm
                    parts, remainder = geometry.slice_part(parts[0], 90.0, op.step_mm)
                    crosscut_step = op.step_mm
                    cuts.append(
                        CutYield(op.step_mm, 90.0, len(parts), remainder, source_length)
                    )

                case StandOnEnd():
                    assert crosscut_step is not None  # гарантировано валидатором
                    parts = [geometry.stand_on_end(part, crosscut_step) for part in parts]

                case Cut():
                    source_length = parts[0].width_mm
                    parts, remainder = geometry.slice_part(
                        parts[0], op.angle_deg, op.step_mm
                    )
                    cuts.append(
                        CutYield(
                            op.step_mm, op.angle_deg, len(parts), remainder, source_length
                        )
                    )

                case Assemble():
                    parts = [
                        geometry.assemble(parts, op.order, op.reversed, op.offsets_mm)
                    ]

                case Crop():
                    parts = [
                        geometry.crop(parts[0], op.left, op.right, op.top, op.bottom)
                    ]

        return Execution(parts[0], tuple(cuts))

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
        """Программа из словаря."""
        version = data.get("schema_version", SCHEMA_VERSION)
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"проект версии {version} новее, чем понимает эта сборка "
                f"({SCHEMA_VERSION})"
            )
        operations = tuple(op_from_dict(item) for item in data["operations"])
        return cls(operations=operations, schema_version=version)


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
