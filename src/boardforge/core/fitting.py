"""Обратная задача: желаемый габарит → параметры программы (Р8).

Габарит не хранится. Пользователь вводит «хочу 400×300×40», программа
переписывается, и целевой размер после этого нигде не живёт — источник истины
остаётся один, параметры операций. Поэтому здесь нет ни поля «целевой размер»,
ни попытки его запомнить: функция возвращает новую программу и то, во что она
попала на самом деле.

Попадание меряется исполнением, а не формулой. Обрезка, неполная полоса
в остатке и округление до целой рейки сдвигают результат, и предсказывать их
второй раз в этом модуле — верный способ соврать.

Разбор по осям следует геометрии, а не буквам Р8: тот текст писался до того,
как порядок осей устоялся, и называет вещи наоборот.

    высота  = шаг торцовки
    ширина  = число полос × толщина щита, то есть длина щита
    длина   = сумма ширин реек, то есть их набор
"""

from dataclasses import dataclass, replace

from .ops import Assemble, Crosscut, Glue, StandOnEnd, Strip
from .piece import Part
from .program import Program, ProgramError

MAX_STRIPS = 200
MAX_SLICES = 400
"""Потолки на случай абсурдного запроса: доска в километр не изготовима."""

MAX_PASSES = 6
"""Сколько раз уточнять набор. Считать наперёд нельзя: обрезка, сдвиги рядов
и остаток от торцовки съедают миллиметры, которые в формулу не заложить. Проще
собрать, померить и поправиться — обычно хватает двух проходов."""


class FitError(ValueError):
    """Обратная задача неразрешима для этой программы."""


@dataclass(frozen=True, slots=True)
class Fit:
    """Переписанная программа и достигнутый габарит против запрошенного."""

    program: Program
    board: Part
    target: tuple[float, float, float]

    @property
    def achieved(self) -> tuple[float, float, float]:
        """Ширина, длина и высота, которые получились."""
        return (self.board.width_mm, self.board.length_mm, self.board.thickness_mm)

    @property
    def deviation(self) -> tuple[float, float, float]:
        """Отклонение от запрошенного по каждой оси, со знаком."""
        return tuple(
            got - want for got, want in zip(self.achieved, self.target, strict=True)
        )

    @property
    def exact(self) -> bool:
        """Попали ли точно по всем трём осям."""
        return all(abs(value) < 0.05 for value in self.deviation)


def _single(program: Program, kind: type) -> object:
    found = [op for op in program.operations if isinstance(op, kind)]
    if len(found) != 1:
        raise FitError(
            f"обратная задача умеет только простую доску: один щит, одна торцовка, "
            f"одна склейка. Здесь операций {kind.__name__}: {len(found)}"
        )
    return found[0]


def _strips_of_count(pattern: tuple[Strip, ...], count: int) -> tuple[Strip, ...]:
    """Набрать `count` реек, повторяя рисунок пород по кругу.

    Ширины реек не трогаем: столяр покупает рейку в размер, а не подгоняет её
    под миллиметр. Меняется количество, последовательность пород повторяется.
    """
    if not pattern:
        raise FitError("в щите нет ни одной рейки")
    count = max(1, min(MAX_STRIPS, count))
    return tuple(pattern[index % len(pattern)] for index in range(count))


def _mean_width(pattern: tuple[Strip, ...]) -> float:
    return sum(strip.width_mm for strip in pattern) / len(pattern)


def _cycled(values: tuple, count: int) -> tuple:
    """Растянуть или обрезать раскладку под новое число деталей."""
    if not values:
        return ()
    return tuple(values[index % len(values)] for index in range(count))


def fit_dimensions(
    program: Program, width_mm: float, length_mm: float, height_mm: float
) -> Fit:
    """Переписать программу под желаемый габарит и померить, что вышло."""
    for name, value in (
        ("ширина", width_mm),
        ("длина", length_mm),
        ("высота", height_mm),
    ):
        if value <= 0:
            raise FitError(f"{name} должна быть положительной, получено {value}")

    glue: Glue = _single(program, Glue)
    crosscut: Crosscut = _single(program, Crosscut)
    assemble: Assemble = _single(program, Assemble)
    if not any(isinstance(op, StandOnEnd) for op in program.operations):
        raise FitError("это не торцевая доска: в программе нет StandOnEnd")

    strip_width = _mean_width(glue.strips)
    strips_count = max(1, round(length_mm / strip_width))
    slices = max(1, round(width_mm / glue.thickness_mm))

    best: Fit | None = None
    seen: set[tuple[int, int]] = set()
    for _ in range(MAX_PASSES):
        strips_count = max(1, min(MAX_STRIPS, strips_count))
        slices = max(1, min(MAX_SLICES, slices))
        if (strips_count, slices) in seen:
            break
        seen.add((strips_count, slices))

        candidate = _rewrite(
            program, glue, crosscut, assemble, strips_count, slices, height_mm
        )
        try:
            board = candidate.apply()
        except ProgramError as error:
            raise FitError(
                f"под такой габарит программа перестаёт исполняться: {error}"
            ) from error

        fit = Fit(candidate, board, (width_mm, length_mm, height_mm))
        if best is None or _miss(fit) < _miss(best):
            best = fit
        if fit.exact:
            break

        strips_count += round((length_mm - board.length_mm) / strip_width)
        slices += round((width_mm - board.width_mm) / glue.thickness_mm)

    assert best is not None
    return best


def _miss(fit: Fit) -> float:
    return sum(abs(value) for value in fit.deviation)


def _rewrite(
    program: Program,
    glue: Glue,
    crosscut: Crosscut,
    assemble: Assemble,
    strips_count: int,
    slices: int,
    height_mm: float,
) -> Program:
    """Программа с переписанными Glue, Crosscut и Assemble."""
    new_glue = replace(
        glue,
        strips=_strips_of_count(glue.strips, strips_count),
        length_mm=slices * height_mm,
    )
    new_crosscut = replace(crosscut, step_mm=height_mm)
    new_assemble = replace(
        assemble,
        pieces=tuple(replace(assemble.pieces[0], index=index) for index in range(slices)),
        reversed=_cycled(assemble.reversed, slices),
        offsets_mm=_cycled(assemble.offsets_mm, slices),
        flipped=_cycled(assemble.flipped, slices) if assemble.flipped else None,
    )
    swapped = {id(glue): new_glue, id(crosscut): new_crosscut, id(assemble): new_assemble}
    return Program(
        operations=tuple(swapped.get(id(op), op) for op in program.operations),
        schema_version=program.schema_version,
    )
