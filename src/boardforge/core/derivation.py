"""Выводится ли ряд доски из имеющихся щитов.

После торцовки все полосы одного щита идентичны: несут одну и ту же
последовательность пород вдоль длины. Значит любой ряд доски обязан быть этой
последовательностью — максимум развёрнутой и сдвинутой, с обрезанными краями.
Ряд, который так не получается, требует отдельного щита.

Это обратный ход: в прямом (программа → доска) ряды выводимы по построению.
Модуль нужен там, где узор задан желаемым, а не программой.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .piece import Billet, Part
from .units import EPS

type CellRun = tuple[str, float]
"""Ячейка ряда: порода и длина вдоль Y."""


@dataclass(frozen=True, slots=True)
class RowSource:
    """Откуда берётся ряд: заготовка, деталь, разворот и сдвиг вдоль полосы."""

    billet: str
    index: int
    reversed: bool
    offset_mm: float
    """Расстояние от начала полосы до первой ячейки ряда."""


@dataclass(frozen=True, slots=True)
class RowMismatch:
    """Ближайшая заготовка и место, где она расходится с желаемым рядом."""

    billet: str
    reversed: bool
    matched_cells: int
    wanted: str
    found: str | None
    """Порода в щите на месте расхождения; None — полоса просто кончилась."""


def cell_sequence(part: Part) -> tuple[CellRun, ...]:
    """Породы и длины ячеек полосы вдоль Y, снизу вверх.

    Соседние ячейки одной породы сливаются: физически это один кусок дерева,
    и шов между рейками одной породы в узоре не читается.

    Ждёт именно полосу — ячейки в один столбец. На щите, где детали стоят
    рядом по X, понятия «последовательность ряда» нет, и молча выдать длины
    было бы хуже, чем упасть.
    """
    _require_single_column(part)
    ordered = sorted(part.pieces, key=lambda piece: piece.polygon.bounds[1])
    runs: list[CellRun] = []
    for piece in ordered:
        _, bottom, _, top = piece.polygon.bounds
        length = top - bottom
        if runs and runs[-1][0] == piece.species:
            runs[-1] = (piece.species, runs[-1][1] + length)
        else:
            runs.append((piece.species, length))
    return tuple(runs)


def is_single_column(part: Part) -> bool:
    """Полоса ли это — все ячейки в один столбец, каждая во всю ширину."""
    xmin, _, xmax, _ = part.bounds
    return all(
        abs(piece.polygon.bounds[0] - xmin) <= EPS
        and abs(piece.polygon.bounds[2] - xmax) <= EPS
        for piece in part.pieces
    )


def _require_single_column(part: Part) -> None:
    """Все ячейки полосы обязаны занимать её ширину целиком."""
    xmin, _, xmax, _ = part.bounds
    for index, piece in enumerate(part.pieces):
        left, _, right, _ = piece.polygon.bounds
        if abs(left - xmin) > EPS or abs(right - xmax) > EPS:
            raise ValueError(
                f"ячейка №{index} занимает по X {left:.1f}–{right:.1f} мм из "
                f"{xmin:.1f}–{xmax:.1f}: это щит, а не полоса — "
                f"разберите его на ряды через rows()"
            )


def rows(part: Part) -> tuple[tuple[CellRun, ...], ...]:
    """Разобрать щит на ряды: каждый ряд — полоса, стоящая поперёк по X."""
    columns: dict[tuple[float, float], list] = {}
    for piece in part.pieces:
        left, _, right, _ = piece.polygon.bounds
        key = (round(left, 6), round(right, 6))
        columns.setdefault(key, []).append(piece)
    return tuple(
        cell_sequence(Part(tuple(pieces), part.thickness_mm))
        for _, pieces in sorted(columns.items())
    )


def _matches_at(target: Sequence[CellRun], source: Sequence[CellRun], start: int) -> bool:
    """Ложится ли ряд на последовательность щита начиная с ячейки `start`.

    Крайние ячейки могут быть короче: их режет `Crop`. Внутренние обязаны
    совпадать точно — иначе это уже другая раскладка реек.
    """
    if start + len(target) > len(source):
        return False
    for offset, (species, length) in enumerate(target):
        found_species, found_length = source[start + offset]
        if species != found_species:
            return False
        edge = offset == 0 or offset == len(target) - 1
        if edge:
            if length > found_length + EPS:
                return False
        elif abs(length - found_length) > EPS:
            return False
    return True


def _offset_of(source: Sequence[CellRun], start: int, first_length: float) -> float:
    consumed = sum(length for _, length in source[:start])
    return consumed + (source[start][1] - first_length)


def _variants(billets: dict[str, Billet]):
    """Все полосы всех заготовок, прямые и развёрнутые.

    Собранные щиты пропускаются: рядом может быть только полоса, а щит —
    это уже результат, из которого ряд не выкроить, не разрезав его заново.
    """
    for name, parts in billets.items():
        for index, part in enumerate(parts):
            if not is_single_column(part):
                continue
            sequence = cell_sequence(part)
            yield name, index, False, sequence
            if len(sequence) > 1:
                yield name, index, True, tuple(reversed(sequence))


def find_row_source(
    target: Sequence[CellRun], billets: dict[str, Billet]
) -> RowSource | None:
    """Из какой заготовки, с каким разворотом и сдвигом получается ряд."""
    if not target:
        return None
    for name, index, is_reversed, sequence in _variants(billets):
        for start in range(len(sequence) - len(target) + 1):
            if _matches_at(target, sequence, start):
                return RowSource(
                    billet=name,
                    index=index,
                    reversed=is_reversed,
                    offset_mm=_offset_of(sequence, start, target[0][1]),
                )
    return None


def closest_billet(
    target: Sequence[CellRun], billets: dict[str, Billet]
) -> RowMismatch | None:
    """Заготовка, совпадающая с рядом дольше прочих, и место расхождения."""
    best: RowMismatch | None = None
    for name, _, is_reversed, sequence in _variants(billets):
        for start in range(max(len(sequence), 1)):
            matched = 0
            while (
                matched < len(target)
                and start + matched < len(sequence)
                and sequence[start + matched][0] == target[matched][0]
            ):
                matched += 1
            if matched >= len(target):
                continue
            position = start + matched
            candidate = RowMismatch(
                billet=name,
                reversed=is_reversed,
                matched_cells=matched,
                wanted=target[matched][0],
                found=sequence[position][0] if position < len(sequence) else None,
            )
            if best is None or candidate.matched_cells > best.matched_cells:
                best = candidate
    return best


def explain_row(
    target: Sequence[CellRun], billets: dict[str, Billet], row_number: int | None = None
) -> str:
    """Человекочитаемый разбор: откуда берётся ряд или чего не хватает."""
    label = "Ряд" if row_number is None else f"Ряд {row_number}"
    if not target:
        return f"{label} пуст."

    source = find_row_source(target, billets)
    if source is not None:
        turn = ", развёрнутая" if source.reversed else ""
        return (
            f"{label} выводится из щита {source.billet}: "
            f"деталь №{source.index}{turn}, сдвиг {source.offset_mm:.1f} мм."
        )

    wanted = ", ".join(f"{species} {length:.0f}" for species, length in target)
    nearest = closest_billet(target, billets)
    if nearest is None:
        return f"{label} ({wanted}) не выводится: щитов нет вовсе."

    turn = " развёрнутый" if nearest.reversed else ""
    if nearest.found is None:
        detail = f"полоса кончается после {nearest.matched_cells} ячеек"
    else:
        detail = (
            f"ячейка {nearest.matched_cells + 1}: нужен {nearest.wanted}, "
            f"а в щите {nearest.found}"
        )
    return (
        f"{label} ({wanted}) не выводится ни из одного щита. "
        f"Ближайший —{turn} щит {nearest.billet}, {detail}. "
        f"Нужен отдельный щит с этой последовательностью."
    )
