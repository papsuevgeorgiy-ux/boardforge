"""Распечатка в мастерскую: одна страница, с которой идут пилить.

Главное требование к ней — не «красиво», а «на ней есть всё, чего без неё
не сделать»: чем пилить, из чего, куда ставить и во что это обойдётся.
"""

import re

import pytest

from boardforge.core.library import build
from boardforge.core.units import INCHES
from boardforge.io.report import collect, render_workshop, write_workshop
from tests.helpers import build_checkerboard


@pytest.fixture(scope="module")
def shop():
    return collect(build_checkerboard())


@pytest.fixture(scope="module")
def page(shop):
    return render_workshop(shop)


def test_page_is_html_with_a_drawing(page) -> None:
    """Страница — HTML со встроенным вектором, а не картинкой.

    Растр здесь был бы концом контракта «один вектор идёт и на экран,
    и в печать»: на бумаге он рассыпался бы в точки.
    """
    assert page.startswith("<!DOCTYPE html>")
    assert "<svg" in page
    assert "<img" not in page
    assert "<?xml" not in page


def test_every_stock_item_is_listed(page, shop) -> None:
    """Каждая рейка закупки — своей строкой с номером."""
    for item in shop.listing.stock:
        assert item.number in page


def test_every_part_is_listed(page, shop) -> None:
    """Каждая полоса — своей строкой: по этим номерам их и раскладывают."""
    for part in shop.listing.parts:
        assert part.number in page


def test_losses_are_broken_down(page) -> None:
    """Пропил, строгание и обрезка стоят раздельно, а не одной строкой «отход»."""
    for article in ("Пропил", "Строгание", "Обрезка торцов", "Обрезка кромок"):
        assert article in page


def test_shopping_list_is_on_the_page(page, shop) -> None:
    """Список в магазин: сколько досок какой длины."""
    assert "Что купить" in page
    assert len(shop.nesting.shopping_list) > 0
    for *_, count in shop.nesting.shopping_list:
        assert str(count) in page


def test_cost_and_weight_are_on_the_page(page, shop) -> None:
    """Себестоимость и вес — то, ради чего смету и читают."""
    assert "Себестоимость" in page
    assert f"{shop.bill.weight_kg:.1f}" in page


def test_species_are_named_by_letters(page, shop) -> None:
    """Породы обозначены буквами, и буквы разъяснены."""
    assert "Обозначения пород" in page
    assert "A" in page
    assert "Клён сахарный" in page


def test_angular_pattern_shows_where_half_the_panel_went() -> None:
    """У шеврона доля обрези видна на странице, а не спрятана в итоге.

    Это вывод Дня 3, и он должен доходить до человека **до** похода в магазин.
    """
    page = render_workshop(collect(build("chevron").program))
    assert "Обрезь и недорез" in page
    shares = [float(value) for value in re.findall(r">(\d+\.\d)%<", page)]
    assert max(shares) > 30.0


def test_cubes_report_the_second_board() -> None:
    """У кубов остаток назван комплектом, а не отходом (Р23)."""
    shop = collect(build("cubes").program)
    page = render_workshop(shop)
    assert shop.bill.boards >= 2
    assert "выйдет досок" in page
    assert "в отход он не идёт" in page


def test_species_warnings_reach_the_page() -> None:
    """Предупреждение о породах печатается до раскроя, а не после сборки."""
    page = render_workshop(
        collect(build("checkerboard", species=("cherry", "hornbeam")).program)
    )
    assert "Прежде чем пилить" in page
    assert "усыхают" in page


def test_units_reach_the_page() -> None:
    """Дюймы доходят до распечатки: чертёж и таблицы читают в одних единицах."""
    page = render_workshop(collect(build_checkerboard(), units=INCHES))
    assert "&#34;" in page or "&quot;" in page or '"' in page


def test_files_are_written(tmp_path, shop) -> None:
    """На диск ложатся страница и чертёж отдельным файлом."""
    page = write_workshop(shop, tmp_path / "shop")
    assert page.exists()
    assert (
        (tmp_path / "shop" / "blueprint.svg")
        .read_text(encoding="utf-8")
        .startswith("<?xml")
    )


def test_report_does_no_arithmetic_of_its_own(shop) -> None:
    """Числа на странице — те же, что в расчётах, а не пересчитанные.

    Стоит распечатке начать считать самой — и она разойдётся с интерфейсом,
    причём разойдётся молча.
    """
    assert shop.raw_dm3 == pytest.approx(shop.material.raw_volume_mm3 / 1e6)
    assert shop.board_dm3 == pytest.approx(shop.material.board_volume_mm3 / 1e6)
    total = sum(volume for _, volume, _ in shop.losses)
    assert total == pytest.approx(shop.material.losses.total_mm3 / 1e6)
