"""Происхождение ячейки: щит, рейка, смещение по длине рейки, порода.

На этом держится текстура: сид берётся из происхождения, а не из места ячейки
в доске, иначе последовательные срезы одной рейки нарисуются как чужие друг
другу куски дерева.
"""

from collections import defaultdict

import pytest

from boardforge.core.geometry import glue, slice_part
from boardforge.core.ops import Strip
from boardforge.core.piece import Origin, Part
from boardforge.core.program import Program
from tests.helpers import CELL_MM, MAPLE, PANEL, STRIP_COUNT, WALNUT


def test_glue_numbers_strips_in_order() -> None:
    """Номер рейки — её место в щите, слева направо."""
    panel = glue((Strip(MAPLE, 40.0), Strip(WALNUT, 30.0)), 100.0, 20.0, "A")
    assert [piece.origin.strip for piece in panel.pieces] == [0, 1]
    assert [piece.origin.billet for piece in panel.pieces] == ["A", "A"]
    assert [piece.origin.offset_mm for piece in panel.pieces] == [0.0, 0.0]


def test_crosscut_advances_offset_along_the_strip() -> None:
    """Каждая следующая полоса отрезана глубже по рейке ровно на шаг."""
    panel = glue((Strip(MAPLE, 40.0),), 200.0, 20.0, "A")
    parts, _ = slice_part(panel, 90.0, 50.0, along_strip=True)
    offsets = [part.pieces[0].origin.offset_mm for part in parts]
    assert offsets == pytest.approx([0.0, 50.0, 100.0, 150.0])


def test_plan_cut_keeps_offset() -> None:
    """Рез в плане делит один и тот же срез рейки: смещению меняться неоткуда."""
    panel = glue((Strip(MAPLE, 120.0),), 100.0, 20.0, "A")
    parts, _ = slice_part(panel, 90.0, 40.0)
    assert {part.pieces[0].origin.offset_mm for part in parts} == {0.0}


def test_board_pieces_carry_origin(checkerboard: Program) -> None:
    """После run() каждая ячейка знает, откуда она."""
    board = checkerboard.apply()
    for piece in board.pieces:
        origin = piece.origin
        assert origin.billet == PANEL
        assert 0 <= origin.strip < 4
        assert origin.species == piece.species
        assert origin.offset_mm == pytest.approx(
            round(origin.offset_mm / CELL_MM) * CELL_MM
        )


def test_origin_survives_assemble(checkerboard: Program) -> None:
    """Сдвиги и обрезка не путают рейки: никакой кусок дерева не задвоен.

    Пара (рейка, смещение) адресует конкретный срез конкретной рейки. Если бы
    сдвиг или обрезка теряли происхождение, пары начали бы повторяться.
    """
    board = checkerboard.apply()
    slices = [
        (piece.origin.strip, round(piece.origin.offset_mm, 6)) for piece in board.pieces
    ]
    assert len(set(slices)) == len(board.pieces)
    assert {strip for strip, _ in slices} == {0, 1, 2, 3}
    for _, offset in slices:
        assert offset % CELL_MM == pytest.approx(0.0)
        assert 0.0 <= offset <= (STRIP_COUNT - 1) * CELL_MM


def test_same_strip_neighbours_are_consecutive_slices(checkerboard: Program) -> None:
    """Соседние срезы одной рейки стоят рядом в доске.

    В принятом порядке осей полоса после торцовки — это столбец доски, поэтому
    последовательные срезы рейки соседствуют по X. Отсюда требование к текстуре:
    их рисунок обязан почти совпадать.
    """
    board = checkerboard.apply()
    by_strip: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for piece in board.pieces:
        left = round(piece.polygon.bounds[0], 6)
        by_strip[piece.origin.strip].append((left, piece.origin.offset_mm))

    for placed in by_strip.values():
        placed.sort()
        for (_, first), (_, second) in zip(placed, placed[1:], strict=False):
            assert second > first


def test_origin_names_its_billet(two_panels: Program) -> None:
    """При нескольких щитах ячейка помнит, из какого именно приехала."""
    board = two_panels.apply()
    assert {piece.origin.billet for piece in board.pieces} == {"A", "B"}
    for piece in board.pieces:
        if piece.species == "cherry":
            assert piece.origin.billet == "B"


def test_reversed_row_keeps_origins() -> None:
    """Разворот детали меняет порядок ячеек, но не их происхождение."""
    from boardforge.core.geometry import assemble

    panel = glue(
        (Strip(MAPLE, 40.0), Strip(WALNUT, 30.0), Strip(MAPLE, 20.0)), 100.0, 20.0, "A"
    )
    straight = assemble([panel], (False,), (0.0,))
    turned = assemble([panel], (True,), (0.0,))

    def strips(part: Part) -> list[int]:
        ordered = sorted(part.pieces, key=lambda piece: piece.polygon.bounds[0])
        return [piece.origin.strip for piece in ordered]

    assert strips(straight) == [0, 1, 2]
    assert strips(turned) == [2, 1, 0]


def test_origin_rejects_nonsense() -> None:
    """Происхождение без породы или с отрицательной рейкой — ошибка на месте."""
    with pytest.raises(ValueError, match="рейки"):
        Origin("A", -1, 0.0, MAPLE)
    with pytest.raises(ValueError, match="порода"):
        Origin("A", 0, 0.0, "")
