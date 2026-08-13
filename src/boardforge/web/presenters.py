"""Программа человеческим языком: операции и замечания валидатора.

Валидатор — главная функция инструмента, и разбор от него должен читаться,
а не расшифровываться. Поэтому здесь операции превращаются в строки вида
«Торцовка щита A с шагом 40 мм — это задаёт высоту доски», а замечание всегда
знает, к какой операции оно относится.
"""

from dataclasses import dataclass

from ..core.ops import Assemble, Crop, Crosscut, Cut, Glue, Operation, StandOnEnd
from ..core.program import Issue, Program
from ..core.species import Species
from ..core.units import Units

LEVELS = {"error": "ошибка", "warning": "предупреждение"}


@dataclass(frozen=True, slots=True)
class OperationView:
    """Операция для показа: номер, название, суть и подробности."""

    number: int
    kind: str
    title: str
    detail: str
    issues: tuple[str, ...]

    @property
    def broken(self) -> bool:
        """Есть ли к этой операции замечания."""
        return bool(self.issues)


@dataclass(frozen=True, slots=True)
class IssueView:
    """Замечание валидатора: уровень, текст и к чему относится."""

    level: str
    level_label: str
    message: str
    where: str


def _species_name(key: str, catalogue: dict[str, Species]) -> str:
    found = catalogue.get(key)
    return found.name if found else key


def describe(
    op: Operation, catalogue: dict[str, Species], units: Units
) -> tuple[str, str, str]:
    """Название операции, её суть и подробности — тремя строками."""
    match op:
        case Glue():
            rails = ", ".join(
                f"{_species_name(strip.species, catalogue)} "
                f"{units.format(strip.width_mm)}"
                for strip in op.strips
            )
            return (
                "Склейка",
                f"Щит {op.id} из {len(op.strips)} реек",
                f"{rails}. Длина {units.format(op.length_mm)}, "
                f"толщина {units.format(op.thickness_mm)}",
            )
        case Crosscut():
            return (
                "Торцовка",
                f"Щит {op.source} режется поперёк с шагом {units.format(op.step_mm)}",
                "Шаг торцовки становится высотой доски",
            )
        case StandOnEnd():
            return (
                "На торец",
                f"Полосы щита {op.source} ставятся на торец",
                "Волокна становятся вертикальными: это и делает доску торцевой",
            )
        case Cut():
            return (
                "Рез в плане",
                f"Щит {op.source} под {op.angle_deg:g}° "
                f"с шагом {units.format(op.step_mm)}",
                "Волокна уже вертикальны, поэтому угол задаёт узор, а не текстуру",
            )
        case Assemble():
            turned = sum(1 for value in op.reversed if value)
            shifted = sum(1 for value in op.offsets_mm if abs(value) > 1e-9)
            notes = [f"{len(op.pieces)} деталей из {', '.join(op.sources)}"]
            if turned:
                notes.append(f"развёрнуто {turned}")
            if shifted:
                notes.append(f"со сдвигом {shifted}")
            if op.flipped and any(op.flipped):
                notes.append(f"перевёрнуто {sum(1 for v in op.flipped if v)}")
            return ("Склейка деталей", f"Щит {op.id}", ", ".join(notes))
        case Crop():
            sides = [
                (name, value)
                for name, value in (
                    ("слева", op.left),
                    ("справа", op.right),
                    ("сверху", op.top),
                    ("снизу", op.bottom),
                )
                if value
            ]
            detail = ", ".join(f"{name} {units.format(value)}" for name, value in sides)
            return (
                "Обрезка",
                f"Щит {op.source} в размер",
                detail or "ничего не срезается",
            )
    return ("Операция", type(op).__name__, "")


def operation_views(
    program: Program, catalogue: dict[str, Species], units: Units
) -> list[OperationView]:
    """Список операций с привязанными к ним замечаниями."""
    issues = program.validate()
    attached: dict[int, list[str]] = {}
    for issue in issues:
        if issue.index is not None:
            attached.setdefault(issue.index, []).append(issue.message)

    views = []
    for index, op in enumerate(program.operations):
        kind, title, detail = describe(op, catalogue, units)
        views.append(
            OperationView(
                number=index + 1,
                kind=kind,
                title=title,
                detail=detail,
                issues=tuple(attached.get(index, ())),
            )
        )
    return views


def issue_views(program: Program, failure: str = "") -> list[IssueView]:
    """Замечания валидатора с человеческой привязкой к месту.

    `failure` — то, на чём программа сломалась при исполнении. Валидатор такого
    не видит: он читает последовательность операций, а не считает геометрию.
    Обрезка, съедающая щит целиком, законна по последовательности и невозможна
    по числам, и сказать об этом надо в том же списке, а не в отдельном углу.
    """
    views = []
    if failure and not program.errors:
        views.append(
            IssueView(
                level="error",
                level_label=LEVELS["error"],
                message=f"Программа не исполняется: {failure}",
                where="При сборке доски",
            )
        )
    for issue in program.validate():
        if issue.index is None:
            where = "Программа целиком"
        else:
            where = f"Операция {issue.index + 1}"
            if issue.index < len(program.operations):
                where += f" — {type(program.operations[issue.index]).__name__}"
        views.append(
            IssueView(
                level=issue.level,
                level_label=LEVELS.get(issue.level, issue.level),
                message=issue.message,
                where=where,
            )
        )
    return views


def verdict(issues: list[IssueView]) -> str:
    """Одна строка сверху: можно ли идти в мастерскую."""
    errors = sum(1 for issue in issues if issue.level == "error")
    warnings = len(issues) - errors
    if errors:
        return f"Доска неизготовима: {errors} ошибк(и). Исправьте, чтобы увидеть узор."
    if warnings:
        return f"Доска изготовима, но есть замечания: {warnings}."
    return "Доска изготовима, замечаний нет."


def issue_of(program: Program) -> list[Issue]:
    """Сырой разбор — для тех, кому нужны уровни, а не текст."""
    return program.validate()
