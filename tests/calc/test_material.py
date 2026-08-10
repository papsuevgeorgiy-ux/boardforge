"""Обратный ход от чистовых размеров к сырью."""

import pytest

from boardforge.calc.allowances import Allowances
from boardforge.calc.material import material_report
from boardforge.core.program import Program
from tests.helpers import CELL_MM, PANEL, STRIP_COUNT

KERF = 3.2
PLANING = 2.0
END_TRIM = 15.0
EDGE_TRIM = 2.0
ALLOWANCES = Allowances(
    kerf_mm=KERF, planing_mm=PLANING, end_trim_mm=END_TRIM, edge_trim_mm=EDGE_TRIM
)


@pytest.fixture
def report(checkerboard: Program):
    return material_report(checkerboard, ALLOWANCES)


@pytest.fixture
def panel(report):
    return report.panel(PANEL)


def test_crosscut_step_covers_final_planing(panel) -> None:
    """Пилить надо выше объявленного: строгание после склейки съест высоту."""
    assert panel.crosscut_step_real_mm == pytest.approx(CELL_MM + PLANING)


def test_panel_length_covers_kerf_and_end_trim(panel) -> None:
    """Длина щита — сумма полос плюс пропилы между ними плюс обрезка торцов."""
    expected = STRIP_COUNT * (CELL_MM + PLANING) + (STRIP_COUNT - 1) * KERF + 2 * END_TRIM
    assert panel.raw_length_mm == pytest.approx(expected)


def test_panel_width_uses_edge_trim_not_end_trim(panel) -> None:
    """Кромку только равняют — по ширине припуск на порядок меньше (Р11)."""
    assert panel.raw_width_mm == pytest.approx(4 * CELL_MM + 2 * EDGE_TRIM)


def test_panel_thickness_covers_planing(panel) -> None:
    """Толщина щита в программе — после строгания, значит сырьё толще."""
    assert panel.raw_thickness_mm == pytest.approx(CELL_MM + PLANING)


def test_outer_strips_carry_edge_trim(panel) -> None:
    """Выравнивание кромок съедает крайние рейки, средние остаются чистовыми."""
    widths = [item.width_mm for item in panel.stock]
    assert widths == pytest.approx([42.0, 40.0, 40.0, 42.0])
    assert sum(widths) == pytest.approx(panel.raw_width_mm)


def test_stock_keeps_species(report) -> None:
    """Позиции закупки помнят породу — иначе по ним не сходить в магазин."""
    assert [item.species for item in report.stock] == [
        "maple_hard",
        "walnut_black",
        "maple_hard",
        "walnut_black",
    ]


def test_losses_add_up(report) -> None:
    """Разбивка потерь сходится с разницей закупки и доски до копейки."""
    assert report.losses.total_mm3 == pytest.approx(
        report.raw_volume_mm3 - report.board_volume_mm3
    )


def test_every_loss_is_accounted(report) -> None:
    """Все технологические потери ненулевые, остаток неотрицателен."""
    losses = report.losses
    assert losses.kerf_mm3 > 0
    assert losses.planing_mm3 > 0
    assert losses.end_trim_mm3 > 0
    assert losses.edge_trim_mm3 > 0
    assert losses.offcut_mm3 >= 0


def test_end_trim_dominates_edge_trim(report) -> None:
    """Торцы съедают заметно больше кромок — иначе Р11 не имел бы смысла."""
    assert report.losses.end_trim_mm3 > report.losses.edge_trim_mm3


def test_purchase_exceeds_board(report) -> None:
    """Закупка заметно больше «суммы объёмов деталей» — это и надо показывать."""
    assert report.overhead_ratio > 0.25


def test_thin_kerf_saves_material(checkerboard: Program) -> None:
    """Тонкий диск меняет расход, но не узор."""
    thick = material_report(checkerboard, ALLOWANCES)
    thin = material_report(checkerboard, Allowances(kerf_mm=1.2, planing_mm=PLANING))
    assert thin.losses.kerf_mm3 < thick.losses.kerf_mm3
    assert thin.board_volume_mm3 == pytest.approx(thick.board_volume_mm3)


def test_zero_allowances_still_valid(checkerboard: Program) -> None:
    """Идеальный станок без потерь — вырожденный, но считаемый случай."""
    ideal = material_report(checkerboard, Allowances(0.0, 0.0, 0.0, 0.0))
    assert ideal.panel(PANEL).crosscut_step_real_mm == pytest.approx(CELL_MM)
    assert ideal.losses.kerf_mm3 == pytest.approx(0.0)


def test_two_panels_are_costed_separately(two_panels: Program) -> None:
    """Каждый щит попадает в закупку своей позицией (Р9)."""
    report = material_report(two_panels, ALLOWANCES)
    assert {panel.billet for panel in report.panels} == {"A", "B"}
    assert len(report.stock) == 4
    assert report.raw_volume_mm3 == pytest.approx(
        sum(panel.raw_volume_mm3 for panel in report.panels)
    )


def test_uncut_panel_is_reported() -> None:
    """Щит, который ни разу не торцевали, — дыра в расчёте, а не молчаливый ноль."""
    from boardforge.core.ops import Assemble, Crosscut, Glue, PieceRef, Strip
    from boardforge.core.program import program
    from tests.helpers import MAPLE, WALNUT

    prog = program(
        Glue("A", (Strip(MAPLE, 40.0), Strip(WALNUT, 40.0)), 200.0, 40.0),
        Glue("B", (Strip(MAPLE, 40.0),), 200.0, 40.0),
        Crosscut("A", 40.0),
        Assemble("C", (PieceRef("A", 0), PieceRef("B", 0)), (False, False), (0.0, 0.0)),
    )
    assert prog.errors == []
    with pytest.raises(ValueError, match="ни разу не торцован"):
        material_report(prog, ALLOWANCES)
