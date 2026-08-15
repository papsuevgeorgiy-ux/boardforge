"""Программа человеческим языком: операции и замечания валидатора.

Валидатор — главная функция инструмента, и разбор от него должен читаться,
а не расшифровываться. Поэтому здесь операции превращаются в строки вида
«Торцовка щита A с шагом 40 мм — это задаёт высоту доски», а замечание всегда
знает, к какой операции оно относится.
"""

from dataclasses import dataclass

from ..core import safety
from ..core.program import Issue, Program, ProgramError
from ..core.species import Species
from ..core.units import Units
from ..io.steps import describe, species_name

# `describe` живёт в `io/steps.py`, а не здесь: теми же словами говорит
# пошаговая инструкция в распечатке, и расходиться им нельзя. Направление
# импорта законное — веб стоит над `io/`.

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
    for issue in program.validate() + _safety_issues(program) + _wood_issues(program):
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


def _safety_issues(program: Program) -> list[Issue]:
    """Замечания об изготовимости — те, что видны только после исполнения.

    Программу здесь могло и не собрать: пользователь крутит параметры, и
    промежуточное состояние бывает неисполнимым. Про это уже сказано выше
    строкой `failure`, второй раз падать незачем.
    """
    if program.errors:
        return []
    try:
        return safety.inspect(program, program.run())
    except (ProgramError, ValueError):
        return []


def _wood_issues(program: Program) -> list[Issue]:
    """Замечания о самих породах: коробление, поры, аллергены, выцветание.

    Не изготовимость: такая доска собирается, вопрос в том, как она проживёт
    следующие годы. Валидатору о породах знать неоткуда — он читает операции,
    а свойство приезжает из справочника.
    """
    from ..calc.warnings import species_issues

    return species_issues(program)


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


@dataclass(frozen=True, slots=True)
class ScoreView:
    """Одна мера узора: как зовётся, чему равна и во сколько процентов длины."""

    name: str
    value: float
    percent: int

    @property
    def label(self) -> str:
        """Число для показа: две цифры после запятой, как в CLI."""
        return f"{self.value:.2f}"


def score_views(scores: object) -> list[ScoreView]:
    """Оценки узора столбиками. Порядок берётся из `Scores.as_dict` и не
    сортируется: он там осмысленный, а не алфавитный."""
    return [
        ScoreView(name, value, round(value * 100))
        for name, value in scores.as_dict().items()  # type: ignore[attr-defined]
    ]


def genome_summary(genome: object, catalogue: dict[str, Species]) -> str:
    """Из чего собран сгенерированный узор — одной строкой под названием."""
    values = genome.values  # type: ignore[attr-defined]
    species = values.get("species", ())
    names = ", ".join(species_name(key, catalogue) for key in species)
    numbers = ", ".join(
        f"{name} {value:g}" if isinstance(value, int | float) else f"{name} {value}"
        for name, value in sorted(values.items())
        if name != "species"
    )
    return f"{names}. {numbers}" if numbers else names
