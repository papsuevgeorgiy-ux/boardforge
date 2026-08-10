"""Эталонная программа, на которой держится половина тестов."""

from boardforge.core.ops import Assemble, Crop, Crosscut, Glue, StandOnEnd, Strip
from boardforge.core.program import Program

MAPLE = "maple_hard"
WALNUT = "walnut_black"

CELL_MM = 40.0
PANEL_LENGTH_MM = 600.0
STRIP_COUNT = 15
ROW_COUNT = 3


def build_checkerboard() -> Program:
    """Шахматка 15×3 ячейки по 40 мм.

    Щит 160×600×40 из четырёх реек, торцовка с шагом 40 даёт 15 полос,
    нечётные сдвигаются на ячейку, рваные края срезает `Crop`.
    """
    return Program(
        operations=(
            Glue(
                strips=(
                    Strip(MAPLE, CELL_MM),
                    Strip(WALNUT, CELL_MM),
                    Strip(MAPLE, CELL_MM),
                    Strip(WALNUT, CELL_MM),
                ),
                length_mm=PANEL_LENGTH_MM,
                thickness_mm=CELL_MM,
            ),
            Crosscut(step_mm=CELL_MM),
            StandOnEnd(),
            Assemble(
                order=tuple(range(STRIP_COUNT)),
                reversed=(False,) * STRIP_COUNT,
                offsets_mm=tuple(
                    0.0 if index % 2 == 0 else CELL_MM for index in range(STRIP_COUNT)
                ),
            ),
            Crop(bottom=CELL_MM, top=CELL_MM),
        )
    )
