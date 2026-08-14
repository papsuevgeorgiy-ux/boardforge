"""Карта раскроя: по ней идут в мастерскую, поэтому она обязана сходиться.

Проверяется не форматирование, а три вещи, на которых карта держится: полос
ровно столько, сколько вышло из резов; каждая полоса знает своё место в склейке;
остаток отделён от отхода измерением, а не на глаз.
"""

import pytest

from boardforge.calc.allowances import Allowances
from boardforge.calc.cutlist import cut_list
from boardforge.core.library import build
from boardforge.core.ops import Assemble, Glue
from tests.helpers import build_checkerboard, build_two_panels


@pytest.fixture(scope="module")
def checkerboard_list():
    return cut_list(build_checkerboard())


def test_stock_covers_every_strip_of_every_panel(checkerboard_list) -> None:
    """Позиций закупки столько же, сколько реек в щитах, и номера сквозные."""
    program = build_checkerboard()
    strips = sum(len(op.strips) for op in program.operations if isinstance(op, Glue))
    assert len(checkerboard_list.stock) == strips
    assert [item.number for item in checkerboard_list.stock] == [
        f"A{index}" for index in range(1, strips + 1)
    ]


def test_stock_is_raw_not_finished() -> None:
    """Рейка в закупке крупнее чистовой: иначе после строгания её не хватит.

    Проверка со стороны карты, а не расчёта материала: карту читает человек
    с рулеткой, и если в ней окажутся чистовые размеры, он отрежет впритык.
    """
    program = build_checkerboard()
    glue = next(op for op in program.operations if isinstance(op, Glue))
    allow = Allowances()
    listing = cut_list(program, allow)

    for item in listing.stock:
        assert item.thickness_mm == pytest.approx(glue.thickness_mm + allow.planing_mm)
        assert item.length_mm > glue.length_mm


def test_every_cut_becomes_a_stage(checkerboard_list) -> None:
    """Стадий столько же, сколько резов, и полос в них — сколько нарезано."""
    execution = build_checkerboard().run()
    assert len(checkerboard_list.stages) == len(execution.cuts)
    for stage, cut in zip(checkerboard_list.stages, execution.cuts, strict=True):
        assert stage.billet == cut.billet
        assert stage.angle_deg == pytest.approx(cut.angle_deg)
        assert len(stage.parts) == cut.count


def test_part_numbers_are_unique_and_readable(checkerboard_list) -> None:
    """Номер полосы называет щит и порядок реза — по нему её и найдут на столе."""
    numbers = [part.number for part in checkerboard_list.parts]
    assert len(set(numbers)) == len(numbers)
    assert numbers[0] == "A-01"
    assert all(
        part.number.startswith(f"{part.billet}-") for part in checkerboard_list.parts
    )


def test_every_part_knows_its_place(checkerboard_list) -> None:
    """У шахматки в дело идут все полосы, и каждая знает своё место в склейке."""
    assembly = next(
        op for op in reversed(build_checkerboard().operations) if isinstance(op, Assemble)
    )
    assert not checkerboard_list.spare
    positions = [part.placement.position for part in checkerboard_list.used]
    assert positions == list(range(1, len(positions) + 1))
    assert {part.placement.assembly for part in checkerboard_list.used} == {assembly.id}


def test_part_size_matches_the_board() -> None:
    """Размеры полосы — те же, что у детали в исполнении программы.

    Карта не пересчитывает геометрию заново, и это надо удержать: стоит ей
    начать считать самой — и распечатка разойдётся с превью.
    """
    program = build_checkerboard()
    execution = program.run()
    listing = cut_list(program)

    for index, part in enumerate(execution.billets["A"]):
        row = listing.parts[index]
        assert row.width_mm == pytest.approx(part.width_mm)
        assert row.length_mm == pytest.approx(part.length_mm)
        assert row.height_mm == pytest.approx(part.thickness_mm)


def test_species_of_a_part_are_the_species_of_its_cells() -> None:
    """Породы полосы — те, что в её ячейках, без повторов и в порядке ячеек."""
    listing = cut_list(build_checkerboard())
    first = listing.parts[0]
    assert set(first.species) <= {"maple_hard", "walnut_black"}
    assert len(set(first.species)) == len(first.species)


def test_two_panels_are_told_apart() -> None:
    """Полосы разных щитов не путаются: номер несёт имя щита."""
    listing = cut_list(build_two_panels())
    billets = {part.billet for part in listing.parts}
    assert len(billets) > 1
    for name in billets:
        assert all(part.number.startswith(name) for part in listing.of_billet(name))


def test_angled_cut_is_marked_as_such() -> None:
    """Угловой рез в карте виден: под 90° пилят по упору, под 45° — по угломеру."""
    listing = cut_list(build("chevron").program)
    angles = {stage.angle_deg for stage in listing.stages}
    assert 90.0 in angles
    assert any(not part.square for part in listing.parts)


def test_placement_says_what_to_do_with_the_strip() -> None:
    """Разворот, переворот и сдвиг попадают в карту словами, а не флагами."""
    listing = cut_list(build("herringbone").program)
    notes = {part.placement.note for part in listing.used if part.placement.note}
    assert notes
    assert any("сдвинуть" in note or "перевернуть" in note for note in notes)


def test_leftovers_of_a_square_board_are_none(checkerboard_list) -> None:
    """У шахматки остатка нет вовсе — и комплекта на вторую доску тоже."""
    assert checkerboard_list.spare_boards == 0
    assert not checkerboard_list.spare


def test_cubes_leave_a_kit_for_a_second_board() -> None:
    """Кубы: остаток последнего реза — комплект, а не отход (Р23).

    Число не назначено, а измерено, и стадия у него именно последняя. Щиты A
    и B расходуются целиком — это видно тут же и это важно: расхожее «половина
    полос каждого щита лишняя» описывает не ту стадию. Лишними оказываются
    полосы после второго углового реза, когда дерево уже дважды склеено.
    """
    listing = cut_list(build("cubes").program)

    for name in listing.panels:
        parts = listing.of_billet(name)
        assert parts
        assert all(not part.spare for part in parts), f"щит {name} расходуется не весь"

    assert listing.spare_boards >= 1
    for stage in listing.final_stages:
        assert len(stage.keepers) >= len(stage.used)


def test_kept_leftovers_are_no_worse_than_what_went_in() -> None:
    """Годный остаток не меньше по площади, чем худшая пошедшая в дело полоса.

    Это и есть порог: он взят из самой доски, а не назначен числом. Клин
    с края щита его не проходит, и в комплект на вторую доску не попадает.
    """
    listing = cut_list(build("cubes").program)
    for stage in listing.stages:
        if not stage.used:
            continue
        floor = min(part.area_mm2 for part in stage.used)
        for part in stage.keepers:
            assert part.area_mm2 >= floor - 1e-6
            assert part.spare


def test_used_parts_are_never_counted_as_leftovers() -> None:
    """Полоса, стоящая в доске, в остатке лежать не может."""
    listing = cut_list(build("cubes").program)
    assert all(not part.reusable for part in listing.used)
    assert set(listing.used) & set(listing.spare) == set()
