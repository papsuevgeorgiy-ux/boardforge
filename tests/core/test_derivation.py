"""Выводимость рядов из имеющихся щитов — то, ради чего сделан мульти-щит."""

import pytest

from boardforge.core.derivation import (
    cell_sequence,
    closest_billet,
    explain_row,
    find_row_source,
    rows,
)
from boardforge.core.program import Program
from tests.helpers import CELL_MM, CHERRY, MAPLE, PANEL, WALNUT


@pytest.fixture
def billets(checkerboard: Program):
    return checkerboard.run().billets


def test_cell_sequence_reads_strip(billets) -> None:
    """Полоса несёт последовательность пород вдоль своей длины."""
    sequence = cell_sequence(billets[PANEL][0])
    assert [species for species, _ in sequence] == [WALNUT, MAPLE, WALNUT, MAPLE]
    assert all(length == pytest.approx(CELL_MM) for _, length in sequence)


def test_all_strips_of_a_billet_are_identical(billets) -> None:
    """Главное ограничение домена: после торцовки полосы щита неотличимы."""
    sequences = {cell_sequence(part) for part in billets[PANEL]}
    assert len(sequences) == 1


def test_adjacent_same_species_merge() -> None:
    """Шов между рейками одной породы в узоре не читается — ячейки сливаются."""
    from boardforge.core.geometry import glue, slice_part, stand_on_end
    from boardforge.core.ops import Strip

    panel = glue(
        (Strip(MAPLE, 40.0), Strip(MAPLE, 30.0), Strip(WALNUT, 20.0)), 100.0, 20.0, "A"
    )
    strips, _ = slice_part(panel, 90.0, 50.0)
    strip = stand_on_end(strips[0], crosscut_step_mm=50.0)
    assert cell_sequence(strip) == ((WALNUT, 20.0), (MAPLE, 70.0))


def test_cell_sequence_refuses_a_panel() -> None:
    """Щит — не ряд: последовательности вдоль Y у него нет, и молчать нельзя."""
    from boardforge.core.geometry import glue
    from boardforge.core.ops import Strip

    panel = glue((Strip(MAPLE, 40.0), Strip(WALNUT, 20.0)), 100.0, 20.0, "A")
    with pytest.raises(ValueError, match="это щит, а не полоса"):
        cell_sequence(panel)


def test_rows_splits_the_board(checkerboard: Program) -> None:
    """Доска разбирается на ряды, каждый — со своей последовательностью."""
    board_rows = rows(checkerboard.apply())
    assert len(board_rows) == 15
    assert board_rows[0] != board_rows[1]


def test_row_derives_from_its_own_billet(billets) -> None:
    """Ряд, взятый из щита, в нём же и находится."""
    target = cell_sequence(billets[PANEL][0])
    source = find_row_source(target, billets)
    assert source is not None
    assert source.billet == PANEL
    assert source.offset_mm == pytest.approx(0.0)


def test_truncated_row_derives_with_offset(billets) -> None:
    """Обрезанный ряд выводится со сдвигом: края режет Crop."""
    target = ((MAPLE, CELL_MM), (WALNUT, CELL_MM))
    source = find_row_source(target, billets)
    assert source is not None
    assert source.offset_mm == pytest.approx(CELL_MM)


def test_reversed_row_is_recognised(billets) -> None:
    """Развёрнутая полоса — та же полоса, и валидатор это знает."""
    straight = cell_sequence(billets[PANEL][0])
    source = find_row_source(tuple(reversed(straight)), billets)
    assert source is not None
    assert source.reversed


def test_partial_edge_cell_allowed(billets) -> None:
    """Крайняя ячейка может быть короче — её подрезали."""
    target = ((WALNUT, 10.0), (MAPLE, CELL_MM), (WALNUT, 25.0))
    assert find_row_source(target, billets) is not None


def test_longer_interior_cell_rejected(billets) -> None:
    """Внутренняя ячейка обязана совпасть точно: иначе это другая раскладка."""
    target = ((WALNUT, CELL_MM), (MAPLE, CELL_MM + 5.0), (WALNUT, CELL_MM))
    assert find_row_source(target, billets) is None


def test_foreign_species_not_derivable(billets) -> None:
    """Ряд с породой, которой в щите нет, не выводится — нужен другой щит."""
    target = ((MAPLE, CELL_MM), (CHERRY, CELL_MM))
    assert find_row_source(target, billets) is None


def test_second_billet_supplies_the_row(two_panels: Program) -> None:
    """С двумя щитами ряд находится — до Р9 это было невыразимо."""
    billets = two_panels.run().billets
    target = ((CHERRY, CELL_MM), (MAPLE, CELL_MM))
    source = find_row_source(target, billets)
    assert source is not None
    assert source.billet == "B"


def test_closest_billet_points_at_the_divergence(billets) -> None:
    """Ближайший щит называет ячейку, на которой расходится."""
    target = ((MAPLE, CELL_MM), (CHERRY, CELL_MM))
    nearest = closest_billet(target, billets)
    assert nearest is not None
    assert nearest.matched_cells == 1
    assert nearest.wanted == CHERRY
    assert nearest.found == WALNUT


def test_explain_row_names_the_source(billets) -> None:
    """Разбор выводимого ряда говорит, откуда его брать."""
    target = ((MAPLE, CELL_MM), (WALNUT, CELL_MM))
    text = explain_row(target, billets, row_number=1)
    assert "Ряд 1 выводится из щита A" in text
    assert "сдвиг" in text


def test_explain_row_demands_another_panel(billets) -> None:
    """Разбор невыводимого ряда прямо требует отдельного щита."""
    target = ((MAPLE, CELL_MM), (CHERRY, CELL_MM))
    text = explain_row(target, billets, row_number=7)
    assert text.startswith("Ряд 7")
    assert "не выводится ни из одного щита" in text
    assert "Ближайший" in text
    assert "Нужен отдельный щит" in text
