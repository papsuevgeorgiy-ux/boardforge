"""Геометрия отдельных операций."""

import pytest

from boardforge.core import geometry
from boardforge.core.ops import Strip

MAPLE = "maple_hard"
WALNUT = "walnut_black"


def panel(length: float = 600.0, thickness: float = 30.0):
    """Щит 160 мм из четырёх реек по 40 мм, породы через одну."""
    strips = (
        Strip(MAPLE, 40.0),
        Strip(WALNUT, 40.0),
        Strip(MAPLE, 40.0),
        Strip(WALNUT, 40.0),
    )
    return geometry.glue(strips, length, thickness, "A")


def test_glue_lays_strips_across_x() -> None:
    """Рейки идут поперёк по X, длина щита — по Y."""
    part = panel()
    assert len(part.pieces) == 4
    assert part.width_mm == pytest.approx(160.0)
    assert part.length_mm == pytest.approx(600.0)
    assert part.thickness_mm == pytest.approx(30.0)
    assert part.area_mm2 == pytest.approx(160.0 * 600.0)


def test_glue_keeps_species_order() -> None:
    """Породы стоят там, где их положили."""
    part = panel()
    assert part.species_at(20.0, 300.0) == MAPLE
    assert part.species_at(60.0, 300.0) == WALNUT
    assert part.species_at(140.0, 300.0) == WALNUT


def test_crosscut_yields_whole_strips_only() -> None:
    """Из щита 600 мм с шагом 45 выходит 13 полос, 15 мм уходит в остаток."""
    strips, remainder = geometry.slice_part(panel(), 90.0, 45.0)
    assert len(strips) == 13
    assert remainder == pytest.approx(15.0)


def test_crosscut_without_remainder() -> None:
    """Кратный шаг не оставляет обрезка и не теряет полосу на округлении."""
    strips, remainder = geometry.slice_part(panel(), 90.0, 40.0)
    assert len(strips) == 15
    assert remainder == pytest.approx(0.0, abs=1e-6)


def test_crosscut_strip_dimensions() -> None:
    """Полоса: шаг реза по X (вдоль волокон), ширина щита по Y."""
    strips, _ = geometry.slice_part(panel(), 90.0, 40.0)
    strip = strips[0]
    assert strip.width_mm == pytest.approx(40.0)
    assert strip.length_mm == pytest.approx(160.0)
    assert strip.thickness_mm == pytest.approx(30.0)
    assert len(strip.pieces) == 4


def test_crosscut_step_larger_than_panel_rejected() -> None:
    """Шаг больше детали — понятная ошибка, а не пустой список."""
    with pytest.raises(ValueError, match="резать нечего"):
        geometry.slice_part(panel(length=100.0), 90.0, 200.0)


def test_stand_on_end_swaps_dimensions() -> None:
    """Шаг торцовки уходит в высоту доски, толщина щита — в план."""
    strips, _ = geometry.slice_part(panel(thickness=30.0), 90.0, 40.0)
    standing = geometry.stand_on_end(strips[0], crosscut_step_mm=40.0)
    assert standing.width_mm == pytest.approx(30.0)
    assert standing.length_mm == pytest.approx(160.0)
    assert standing.thickness_mm == pytest.approx(40.0)


def test_stand_on_end_keeps_species_layout() -> None:
    """Смена плоскости не перемешивает породы вдоль полосы."""
    strips, _ = geometry.slice_part(panel(thickness=30.0), 90.0, 40.0)
    before = strips[0]
    after = geometry.stand_on_end(before, crosscut_step_mm=40.0)
    for y in (20.0, 60.0, 100.0, 140.0):
        assert after.species_at(15.0, y) == before.species_at(20.0, y)


def test_angled_cut_gives_parallelograms() -> None:
    """Рез под 45° даёт скошенные детали, а не прямоугольники."""
    strips, _ = geometry.slice_part(panel(length=400.0), 45.0, 50.0)
    middle = strips[len(strips) // 2]
    assert middle.width_mm == pytest.approx(50.0)
    corners = len(middle.pieces[0].polygon.exterior.coords) - 1
    assert corners >= 4
    assert middle.length_mm > 50.0


def test_assemble_stacks_across_x() -> None:
    """Склейка кладёт детали поперёк по X, как и первая склейка реек."""
    strips, _ = geometry.slice_part(panel(), 90.0, 40.0)
    board = geometry.assemble(strips[:3], (False,) * 3, (0.0,) * 3)
    assert board.width_mm == pytest.approx(120.0)
    assert board.length_mm == pytest.approx(160.0)


def test_assemble_offsets_shift_along_y() -> None:
    """Сдвиг полосы удлиняет щит: край получается рваным, его срежет Crop."""
    strips, _ = geometry.slice_part(panel(), 90.0, 40.0)
    board = geometry.assemble(strips[:2], (False, False), (0.0, 40.0))
    assert board.length_mm == pytest.approx(200.0)


def test_assemble_reversed_flips_row_order() -> None:
    """Разворот на 180° переставляет ячейки ряда задом наперёд."""
    strips, _ = geometry.slice_part(panel(), 90.0, 40.0)
    straight = geometry.assemble(strips[:1], (False,), (0.0,))
    turned = geometry.assemble(strips[:1], (True,), (0.0,))
    for y in (20.0, 60.0, 100.0, 140.0):
        assert turned.species_at(20.0, y) == straight.species_at(20.0, 160.0 - y)


def test_assemble_rejects_mixed_thickness() -> None:
    """Детали разной толщины в один щит не идут — и об этом говорится с числами."""
    thick, _ = geometry.slice_part(panel(thickness=30.0), 90.0, 40.0)
    thin, _ = geometry.slice_part(panel(thickness=20.0), 90.0, 40.0)
    with pytest.raises(ValueError, match="разной толщины"):
        geometry.assemble([thick[0], thin[0]], (False, False), (0.0, 0.0))


def test_stand_on_end_guards_its_precondition() -> None:
    """Масштаб по X равен повороту только сразу после торцовки — иначе падаем."""
    strips, _ = geometry.slice_part(panel(), 90.0, 40.0)
    narrowed = geometry.crop(strips[0], left=5.0, right=0.0, top=0.0, bottom=0.0)
    with pytest.raises(ValueError, match="не сводится к масштабу|шагу торцовки"):
        geometry.stand_on_end(narrowed, crosscut_step_mm=40.0)


def test_stand_on_end_guards_against_angled_cut() -> None:
    """Косая ячейка не прямоугольна — поворот на торец для неё не масштаб."""
    strips, _ = geometry.slice_part(panel(length=400.0), 45.0, 50.0)
    with pytest.raises(ValueError, match="не сводится к масштабу|шагу торцовки"):
        geometry.stand_on_end(strips[len(strips) // 2], crosscut_step_mm=50.0)


def test_crop_cuts_cells() -> None:
    """Обрезка режет ячейки, а не только пустоту по краям."""
    part = panel(length=600.0)
    cropped = geometry.crop(part, left=20.0, right=0.0, top=100.0, bottom=0.0)
    assert cropped.width_mm == pytest.approx(140.0)
    assert cropped.length_mm == pytest.approx(500.0)
    assert cropped.species_at(5.0, 250.0) == MAPLE


def test_crop_everything_rejected() -> None:
    """Обрезка в ноль — ошибка, а не деталь без ячеек."""
    with pytest.raises(ValueError, match="ничего"):
        geometry.crop(panel(), left=80.0, right=80.0, top=0.0, bottom=0.0)
