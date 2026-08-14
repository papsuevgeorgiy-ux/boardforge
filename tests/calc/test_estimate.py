"""Смета: цена, клей, масло и вес.

Проверяется не арифметика умножения, а то, чем смета отличается от наивной:
считает по закупке, а не по доске; делит стоимость на все доски, что из этой
закупки выйдут; берёт плотность каждой породы отдельно.
"""

import pytest

from boardforge.calc.estimate import DEFAULT_PRICE_PER_M3, Prices, estimate
from boardforge.calc.material import material_report
from boardforge.core.library import build
from boardforge.core.program import Program
from boardforge.core.species import load_species


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


@pytest.fixture
def bill(checkerboard: Program):
    return estimate(checkerboard)


def test_every_species_of_the_catalogue_has_a_price(catalogue) -> None:
    """Прайс покрывает справочник: ставка «для незнакомой» не рабочий режим."""
    assert set(DEFAULT_PRICE_PER_M3) == set(catalogue)


def test_volume_is_the_purchase_not_the_board(bill, checkerboard: Program) -> None:
    """Считаем по объёму закупки. По доске вышло бы дешевле, чем в магазине."""
    report = material_report(checkerboard)
    assert bill.volume_m3 * 1e9 == pytest.approx(report.raw_volume_mm3)
    assert bill.volume_m3 * 1e9 > report.board_volume_mm3


def test_species_line_matches_its_price(bill) -> None:
    """Строка породы — объём на её цену, а не доля общего."""
    for item in bill.species:
        assert item.cost == pytest.approx(item.volume_m3 * item.price_per_m3)
    assert bill.wood_cost == pytest.approx(sum(item.cost for item in bill.species))


def test_prices_are_editable(checkerboard: Program) -> None:
    """Цены — параметр, а не константа: вдвое дороже дерево — вдвое дороже доска."""
    cheap = estimate(checkerboard, Prices(per_m3=dict(DEFAULT_PRICE_PER_M3)))
    dear = estimate(
        checkerboard,
        Prices(per_m3={key: value * 2 for key, value in DEFAULT_PRICE_PER_M3.items()}),
    )
    assert dear.wood_cost == pytest.approx(cheap.wood_cost * 2)
    assert dear.glue_cost == pytest.approx(cheap.glue_cost)


def test_unknown_species_is_not_free() -> None:
    """Порода вне прайса считается по общей ставке, а не по нулю."""
    prices = Prices(per_m3={})
    bill = estimate(build("checkerboard").program, prices)
    assert bill.wood_cost > 0
    assert all(item.price_per_m3 == prices.unknown_per_m3 for item in bill.species)


def test_total_adds_up(bill) -> None:
    """Итог — дерево плюс клей плюс масло, без незаметных слагаемых."""
    assert bill.total == pytest.approx(bill.wood_cost + bill.glue_cost + bill.oil_cost)


def test_glue_and_oil_are_not_zero(bill) -> None:
    """Расходники в смете есть: без них итог занижен на заметную величину."""
    assert bill.glue_kg > 0
    assert bill.oil_l > 0


def test_glue_grows_with_the_number_of_seams(checkerboard: Program) -> None:
    """Клея тем больше, чем больше швов, а не чем больше щит.

    Щит из десяти реек и щит из двух той же ширины склеиваются разным
    количеством клея — на этом и держится расчёт по швам.
    """
    from dataclasses import replace

    from boardforge.core.ops import Glue, Strip

    glue = next(op for op in checkerboard.operations if isinstance(op, Glue))
    halved = replace(
        glue,
        strips=tuple(
            Strip(strip.species, strip.width_mm * 2) for strip in glue.strips[::2]
        ),
    )
    fewer = Program(
        operations=tuple(halved if op is glue else op for op in checkerboard.operations)
    )
    assert estimate(fewer).glue_kg < estimate(checkerboard).glue_kg


def test_weight_uses_each_species_density(catalogue) -> None:
    """Вес считается по породам ячеек, а не по средней плотности.

    Клён с венге и клён с орехом дают одну и ту же геометрию и разный вес —
    поднимать доску будут руками, и разница в четверть заметна.
    """
    light = estimate(build("checkerboard", species=("maple_hard", "cherry")).program)
    heavy = estimate(build("checkerboard", species=("maple_hard", "wenge")).program)
    assert heavy.weight_kg > light.weight_kg * 1.1


def test_weight_is_plausible_for_a_cutting_board(bill) -> None:
    """Вес в килограммах, а не в тоннах: проверка порядка величины."""
    assert 1.0 < bill.weight_kg < 20.0


def test_cubes_cost_is_split_between_two_boards() -> None:
    """У кубов закупка даёт комплект на вторую доску, и цена делится (Р23).

    Записать всю стоимость на первую доску — соврать вдвое. Число досок берётся
    из карты раскроя измерением, а не из предположения про узор.
    """
    bill = estimate(build("cubes").program)
    assert bill.boards >= 2
    assert bill.per_board == pytest.approx(bill.total / bill.boards)
    assert bill.per_board < bill.total


def test_ordinary_board_is_not_divided(bill) -> None:
    """Там, где остатка нет, себестоимость доски равна итогу сметы."""
    assert bill.boards == 1
    assert bill.per_board == pytest.approx(bill.total)


def test_negative_price_is_rejected() -> None:
    """Отрицательная цена — ошибка ввода, а не скидка."""
    with pytest.raises(ValueError, match="цена породы"):
        Prices(per_m3={"maple_hard": -1.0})
