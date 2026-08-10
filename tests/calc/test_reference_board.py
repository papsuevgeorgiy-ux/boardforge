"""Снапшот контрольной доски.

Смета — производная от геометрии, припусков и десятка формул. Любая из них
может сдвинуться при рефакторинге незаметно: тесты на инварианты («потери
сходятся», «закупка больше доски») останутся зелёными, а числа поедут.
Здесь они прибиты гвоздями.

Если тест упал — сначала объясни, почему число изменилось, и только потом
правь эталон. Молча обновлять его нельзя.

Доска: шахматка 600 × 120 × 40 мм, 45 ячеек по 40 мм, один щит из четырёх
реек 40 мм (клён / орех), торцовка с шагом 40, одна вторая склейка.
Припуски: диск 3.2, строгание 2.0, торцы 15.0, кромки 2.0.
"""

import pytest

from boardforge.calc.allowances import Allowances
from boardforge.calc.material import material_report
from boardforge.core.program import Program
from tests.helpers import PANEL

ALLOWANCES = Allowances(kerf_mm=3.2, planing_mm=2.0, end_trim_mm=15.0, edge_trim_mm=2.0)

BOARD_MM = (600.0, 120.0, 40.0)
CELL_COUNT = 45

PANEL_RAW_MM = (164.0, 704.8, 42.0)
TRIMMED_LENGTH_MM = 674.8
CROSSCUT_STEP_REAL_MM = 42.0
STRIP_COUNT = 15

STOCK = [
    ("maple_hard", 42.0, 42.0, 704.8),
    ("walnut_black", 40.0, 42.0, 704.8),
    ("maple_hard", 40.0, 42.0, 704.8),
    ("walnut_black", 42.0, 42.0, 704.8),
]

BOARD_VOLUME_MM3 = 2_880_000.0
RAW_VOLUME_MM3 = 4_854_662.4
LOSSES_MM3 = {
    "kerf": 286_720.0,
    "planing": 375_174.4,
    "end_trim": 196_800.0,
    "edge_trim": 107_968.0,
    "offcut": 1_008_000.0,
}
OVERHEAD_RATIO = 0.6856

TOLERANCE = {"rel": 1e-9}


def _report(checkerboard: Program):
    return material_report(checkerboard, ALLOWANCES)


def test_board_dimensions(checkerboard: Program) -> None:
    """Габарит доски и число ячеек."""
    board = checkerboard.apply()
    assert (board.width_mm, board.length_mm, board.thickness_mm) == pytest.approx(
        BOARD_MM, **TOLERANCE
    )
    assert len(board.pieces) == CELL_COUNT


def test_panel_raw_dimensions(checkerboard: Program) -> None:
    """Сырой размер щита: ширина, длина, толщина."""
    panel = _report(checkerboard).panel(PANEL)
    actual = (panel.raw_width_mm, panel.raw_length_mm, panel.raw_thickness_mm)
    assert actual == pytest.approx(PANEL_RAW_MM, **TOLERANCE)
    assert panel.trimmed_length_mm == pytest.approx(TRIMMED_LENGTH_MM, **TOLERANCE)
    assert panel.crosscut_step_real_mm == pytest.approx(
        CROSSCUT_STEP_REAL_MM, **TOLERANCE
    )
    assert panel.strip_count == STRIP_COUNT


def test_stock_list(checkerboard: Program) -> None:
    """Список закупки: порода и сырое сечение каждой рейки."""
    actual = [
        (item.species, item.width_mm, item.thickness_mm, item.length_mm)
        for item in _report(checkerboard).stock
    ]
    assert [row[0] for row in actual] == [row[0] for row in STOCK]
    assert [row[1:] for row in actual] == pytest.approx(
        [row[1:] for row in STOCK], **TOLERANCE
    )


def test_volumes(checkerboard: Program) -> None:
    """Объём доски и объём закупки."""
    report = _report(checkerboard)
    assert report.board_volume_mm3 == pytest.approx(BOARD_VOLUME_MM3, **TOLERANCE)
    assert report.raw_volume_mm3 == pytest.approx(RAW_VOLUME_MM3, **TOLERANCE)


def test_loss_breakdown(checkerboard: Program) -> None:
    """Разбивка потерь по причинам — та самая, что уходит в смету."""
    losses = _report(checkerboard).losses
    actual = {
        "kerf": losses.kerf_mm3,
        "planing": losses.planing_mm3,
        "end_trim": losses.end_trim_mm3,
        "edge_trim": losses.edge_trim_mm3,
        "offcut": losses.offcut_mm3,
    }
    assert actual == pytest.approx(LOSSES_MM3, **TOLERANCE)


def test_overhead_ratio(checkerboard: Program) -> None:
    """Насколько закупка превышает доску — главное число сметы."""
    assert _report(checkerboard).overhead_ratio == pytest.approx(OVERHEAD_RATIO, abs=5e-5)


def test_edge_trim_split_is_visible(checkerboard: Program) -> None:
    """Р11 в числах: раздельные припуски дают вчетверо меньше потерь на кромки.

    Со старым общим припуском 15 мм по всем осям кромки съедали 0.810 л
    и закупка выходила +95%; после разделения — 0.108 л и +69%.
    """
    lumped = material_report(
        checkerboard,
        Allowances(kerf_mm=3.2, planing_mm=2.0, end_trim_mm=15.0, edge_trim_mm=15.0),
    )
    split = _report(checkerboard)

    assert lumped.losses.edge_trim_mm3 == pytest.approx(810_000.0, rel=1e-3)
    assert split.losses.edge_trim_mm3 == pytest.approx(108_000.0, rel=1e-3)
    assert lumped.overhead_ratio == pytest.approx(0.953, abs=5e-4)
    assert split.overhead_ratio == pytest.approx(0.686, abs=5e-4)
