"""Доски для просмотра глазами: узоры библиотеки и диагностические фикстуры.

`EXAMPLES` — вся библиотека узоров Дня 4. Раньше здесь лежали три доски,
выписанные руками; теперь это вид на `core/library.py`, и добавить узор
в набор для показа можно только добавив его в библиотеку. Так и надо: демо,
которое расходится с библиотекой, врёт про инструмент.

`DIAGNOSTICS` — не узоры, а стенды: доска, собранная так, чтобы одно свойство
рендера было видно глазом и ничем другим не объяснялось. Шаблоном такое
предлагать нельзя, поэтому набор отдельный.
"""

from collections.abc import Callable

from ..core.library import LIBRARY
from ..core.ops import Assemble, Crosscut, Glue, PieceRef, StandOnEnd, Strip
from ..core.program import Program

PANEL = "A"
BOARD = "B"

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


def _from_library() -> dict[str, Board]:
    """Библиотека в виде набора демо-досок, в порядке объявления шаблонов."""
    return {
        key: (
            f"{template.title.lower()}: {template.summary.lower()}",
            (lambda item=template: item().program),
        )
        for key, template in LIBRARY.items()
    }


EXAMPLES: dict[str, Board] = _from_library()

DIAGNOSTICS: dict[str, Board] = {
    "reversed-check": ("стенд: ясень, нечётные ячейки развёрнуты", reversed_check),
    "column-check": ("стенд: ясень, срезы одной рейки подряд", column_check),
}
