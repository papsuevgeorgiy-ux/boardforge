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


def build_grid(columns: int, rows: int, cell_mm: float = 20.0) -> Program:
    """Доска `columns` × `rows` ячеек из одного щита — нагрузка для рендера.

    Породы чередуются по рейкам, поэтому у каждого ряда своя текстура: рендер
    не может сжульничать, нарисовав всё одним элементом.
    """
    palette = (MAPLE, WALNUT, CHERRY)
    strips = tuple(Strip(palette[index % len(palette)], cell_mm) for index in range(rows))
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
                offsets_mm=(0.0,) * columns,
            ),
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
