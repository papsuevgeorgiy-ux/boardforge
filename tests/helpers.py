"""Эталонные программы, на которых держится половина тестов."""

from boardforge.core.ops import (
    Assemble,
    Crop,
    Crosscut,
    Glue,
    PieceRef,
    StandOnEnd,
    Strip,
)
from boardforge.core.program import Program

MAPLE = "maple_hard"
WALNUT = "walnut_black"
CHERRY = "cherry"

CELL_MM = 40.0
PANEL_LENGTH_MM = 600.0
STRIP_COUNT = 15
ROW_COUNT = 3
PANEL = "A"
BOARD = "B"


def build_checkerboard() -> Program:
    """Шахматка 15×3 ячейки по 40 мм.

    Щит 160×600×40 из четырёх реек, торцовка с шагом 40 даёт 15 полос,
    нечётные сдвигаются на ячейку, рваные края срезает `Crop`.
    """
    return Program(
        operations=(
            Glue(
                id=PANEL,
                strips=(
                    Strip(MAPLE, CELL_MM),
                    Strip(WALNUT, CELL_MM),
                    Strip(MAPLE, CELL_MM),
                    Strip(WALNUT, CELL_MM),
                ),
                length_mm=PANEL_LENGTH_MM,
                thickness_mm=CELL_MM,
            ),
            Crosscut(source=PANEL, step_mm=CELL_MM),
            StandOnEnd(source=PANEL),
            Assemble(
                id=BOARD,
                pieces=tuple(PieceRef(PANEL, index) for index in range(STRIP_COUNT)),
                reversed=(False,) * STRIP_COUNT,
                offsets_mm=tuple(
                    0.0 if index % 2 == 0 else CELL_MM for index in range(STRIP_COUNT)
                ),
            ),
            Crop(source=BOARD, bottom=CELL_MM, top=CELL_MM),
        )
    )


def build_two_panels() -> Program:
    """Доска из двух разных щитов: ряды чередуются составом, а не сдвигом.

    Щит A — клён/орех, щит B — клён/вишня. Ни один ряд из B не выводится
    из A: ради таких случаев и заведён именованный набор заготовок.
    """
    strips_a = (Strip(MAPLE, CELL_MM), Strip(WALNUT, CELL_MM))
    strips_b = (Strip(MAPLE, CELL_MM), Strip(CHERRY, CELL_MM))
    picks = tuple(
        PieceRef("A" if index % 2 == 0 else "B", index // 2) for index in range(6)
    )
    return Program(
        operations=(
            Glue(id="A", strips=strips_a, length_mm=200.0, thickness_mm=CELL_MM),
            Glue(id="B", strips=strips_b, length_mm=200.0, thickness_mm=CELL_MM),
            Crosscut(source="A", step_mm=CELL_MM),
            StandOnEnd(source="A"),
            Crosscut(source="B", step_mm=CELL_MM),
            StandOnEnd(source="B"),
            Assemble(
                id="BOARD",
                pieces=picks,
                reversed=(False,) * len(picks),
                offsets_mm=(0.0,) * len(picks),
            ),
        )
    )
