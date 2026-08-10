"""Обратный ход от чистовых размеров к сырью."""

import pytest

from boardforge.calc.allowances import Allowances
from boardforge.calc.material import material_report
from boardforge.core.program import Program
from tests.helpers import CELL_MM, STRIP_COUNT

ALLOWANCES = Allowances(kerf_mm=3.2, planing_mm=2.0, edge_trim_mm=15.0)


@pytest.fixture
def report(checkerboard: Program):
    return material_report(checkerboard, ALLOWANCES)


def test_crosscut_step_covers_final_planing(report) -> None:
    """Пилить надо выше объявленного: строгание после склейки съест высоту."""
    assert report.crosscut_step_real_mm == pytest.approx(CELL_MM + 2.0)


def test_panel_length_covers_kerf_and_trim(report) -> None:
    """Длина щита — сумма полос плюс пропилы между ними плюс обрезка торцов."""
    expected = STRIP_COUNT * (CELL_MM + 2.0) + (STRIP_COUNT - 1) * 3.2 + 2 * 15.0
    assert report.panel_raw_length_mm == pytest.approx(expected)


def test_panel_thickness_covers_planing(report) -> None:
    """Толщина щита в программе — после строгания, значит сырьё толще."""
    assert report.panel_raw_thickness_mm == pytest.approx(CELL_MM + 2.0)


def test_outer_strips_carry_edge_trim(report) -> None:
    """Обрезка кромок съедает крайние рейки, средние остаются чистовыми."""
    widths = [item.width_mm for item in report.stock]
    assert widths == pytest.approx([55.0, 40.0, 40.0, 55.0])
    assert sum(widths) == pytest.approx(report.panel_raw_width_mm)


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
    """Все три технологические потери ненулевые, остаток неотрицателен."""
    assert report.losses.kerf_mm3 > 0
    assert report.losses.planing_mm3 > 0
    assert report.losses.edge_trim_mm3 > 0
    assert report.losses.offcut_mm3 >= 0


def test_purchase_exceeds_board(report) -> None:
    """Закупка заметно больше «суммы объёмов деталей» — это и надо показывать."""
    assert report.overhead_ratio > 0.25


def test_thin_kerf_saves_material(checkerboard: Program) -> None:
    """Тонкий диск меняет расход, но не узор."""
    thick = material_report(checkerboard, ALLOWANCES)
    thin = material_report(checkerboard, Allowances(kerf_mm=1.2, planing_mm=2.0))
    assert thin.losses.kerf_mm3 < thick.losses.kerf_mm3
    assert thin.board_volume_mm3 == pytest.approx(thick.board_volume_mm3)


def test_zero_allowances_still_valid(checkerboard: Program) -> None:
    """Идеальный станок без потерь — вырожденный, но считаемый случай."""
    ideal = material_report(checkerboard, Allowances(0.0, 0.0, 0.0))
    assert ideal.crosscut_step_real_mm == pytest.approx(CELL_MM)
    assert ideal.losses.kerf_mm3 == pytest.approx(0.0)
