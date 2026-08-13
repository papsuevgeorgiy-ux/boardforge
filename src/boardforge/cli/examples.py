"""Доски для просмотра глазами: узоры и диагностические фикстуры.

`EXAMPLES` — узоры. Живут здесь временно: библиотека узоров это День 4, тогда
они уедут в неё, и порог «узор — это не пара ячеек» уедет вместе с ними.

`DIAGNOSTICS` — не узоры, а стенды: доска, собранная так, чтобы одно свойство
рендера было видно глазом и ничем другим не объяснялось. Шаблоном такое
предлагать нельзя, поэтому набор отдельный.
"""

from collections.abc import Callable, Sequence

from ..core.ops import Assemble, Crop, Crosscut, Glue, PieceRef, StandOnEnd, Strip
from ..core.program import Program

PANEL = "A"
BOARD = "B"


def _brick(
    species: Sequence[str],
    cell_mm: float,
    columns: int,
    strips_count: int,
    shift: int,
    period: int,
) -> Program:
    """Щит из реек `species`, торцовка с шагом ячейки, кладка со сдвигом.

    Породы повторяются по кругу, пока не наберётся `strips_count` реек. Ряд
    номер n сдвигается на `n * shift % period` ячеек; рваные после сдвига края
    срезает `Crop`, и на него же уходит `period - 1` ряд сверху и снизу.
    """
    strips = tuple(
        Strip(species[index % len(species)], cell_mm) for index in range(strips_count)
    )
    offsets = tuple((index * shift % period) * cell_mm for index in range(columns))
    margin = max(offsets)
    return Program(
        operations=(
            Glue(
                id=PANEL,
                strips=strips,
                length_mm=cell_mm * columns,
                thickness_mm=cell_mm,
            ),
            Crosscut(source=PANEL, step_mm=cell_mm),
            StandOnEnd(source=PANEL),
            Assemble(
                id=BOARD,
                pieces=tuple(PieceRef(PANEL, index) for index in range(columns)),
                reversed=(False,) * columns,
                offsets_mm=offsets,
            ),
            Crop(source=BOARD, bottom=margin, top=margin),
        )
    )


def checkerboard() -> Program:
    """Эталонная шахматка: клён и орех, ячейка 40 мм."""
    return _brick(
        ("maple_hard", "walnut_black"),
        40.0,
        columns=15,
        strips_count=6,
        shift=1,
        period=2,
    )


def strong_rings() -> Program:
    """Породы с резкими кольцами: ясень, дуб, граб — проверка текстуры."""
    return _brick(
        ("ash", "oak", "hornbeam"), 34.0, columns=13, strips_count=6, shift=1, period=3
    )


def tropical() -> Program:
    """Тропические: падук, амарант, венге, ятоба, сапеле — проверка цвета."""
    return _brick(
        ("padauk", "purpleheart", "wenge", "jatoba", "sapele"),
        30.0,
        columns=14,
        strips_count=10,
        shift=2,
        period=5,
    )


STAND_SPECIES = "ash"
STAND_CELLS = 8
STAND_CELL_MM = 55.0
"""Общая заготовка стендов: ясень взят за резкие кольца, размер — чтобы ячейка
была крупной при любом разумном масштабе."""


def _one_rail(turn_odd: bool) -> Program:
    """Ряд из `STAND_CELLS` подряд идущих срезов одной и той же рейки.

    Щит из **одной** рейки, поэтому каждая деталь — ровно одна ячейка, а ячейки
    в ряду — последовательные срезы одного куска дерева. Порода одна, сдвигов
    нет: узор вырождается, и всё, чем ячейки отличаются, — рисунок волокон.

    Ряд, а не столбец: в принятом порядке осей срез после торцовки встаёт
    столбцом доски, а следующий срез клеится к нему **сбоку**. Соседи по длине
    рейки идут по X, и вертикально их не выложить, не соврав про изготовление.
    """
    return Program(
        operations=(
            Glue(
                id=PANEL,
                strips=(Strip(STAND_SPECIES, STAND_CELL_MM),),
                length_mm=STAND_CELL_MM * STAND_CELLS,
                thickness_mm=STAND_CELL_MM,
            ),
            Crosscut(source=PANEL, step_mm=STAND_CELL_MM),
            StandOnEnd(source=PANEL),
            Assemble(
                id=BOARD,
                pieces=tuple(PieceRef(PANEL, index) for index in range(STAND_CELLS)),
                reversed=tuple(
                    turn_odd and index % 2 == 1 for index in range(STAND_CELLS)
                ),
                offsets_mm=(0.0,) * STAND_CELLS,
            ),
        )
    )


def reversed_check() -> Program:
    """Стенд для проверки разворота: чётные ячейки прямые, нечётные развёрнуты.

    Не узор и не шаблон: доска в один ряд из одной рейки никому не нужна как
    изделие. Её задача — показать, что `reversed` доходит до текстуры.

    Соседние ячейки — почти одно и то же дерево по построению, узор от разворота
    не меняется, значит всё различие между ними это поворот волокон на 180°.
    Контроль к этому стенду — `column_check`, та же рейка без разворотов.
    """
    return _one_rail(turn_odd=True)


def column_check() -> Program:
    """Стенд для проверки перетекания: те же срезы рейки подряд, без разворотов.

    Показывает, что текстура сеется от рейки, а не от места ячейки в доске:
    кольца обязаны плавно перетекать от ячейки к ячейке с медленным дрейфом
    вдоль рейки, а не начинаться в каждой заново.

    Смотреть слева направо — именно туда растёт смещение по длине рейки.
    """
    return _one_rail(turn_odd=False)


type Board = tuple[str, Callable[[], Program]]

EXAMPLES: dict[str, Board] = {
    "checkerboard": ("шахматка клён / орех", checkerboard),
    "strong-rings": ("ясень, дуб, граб — сильные кольца", strong_rings),
    "tropical": ("падук, амарант, венге, ятоба, сапеле", tropical),
}

DIAGNOSTICS: dict[str, Board] = {
    "reversed-check": ("стенд: ясень, нечётные ячейки развёрнуты", reversed_check),
    "column-check": ("стенд: ясень, срезы одной рейки подряд", column_check),
}
