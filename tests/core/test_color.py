"""CIELAB: опорные точки и то, ради чего модуль заведён.

Числа сверяются с определением формулы, а не с самим модулем: тест, который
меряет реализацию её же результатами, ничего не проверяет.
"""

import pytest

from boardforge.core.color import (
    Lab,
    hex_to_lab,
    lightness_spread,
    nearest,
    parse_hex,
    rgb_to_lab,
)
from boardforge.core.species import load_species


def test_white_and_black_are_the_ends_of_the_scale() -> None:
    """Опорные точки D65: белый — 100, чёрный — 0, оба без цветности."""
    white = hex_to_lab("#ffffff")
    assert white.lightness == pytest.approx(100.0, abs=1e-3)
    assert white.a == pytest.approx(0.0, abs=1e-3)
    assert white.b == pytest.approx(0.0, abs=1e-3)

    black = hex_to_lab("#000000")
    assert black.lightness == pytest.approx(0.0, abs=1e-6)


def test_middle_grey_sits_where_the_gamma_puts_it() -> None:
    """Серый 50% — светлота около 53.6, а не 50: гамма снята правильно."""
    assert hex_to_lab("#808080").lightness == pytest.approx(53.585, abs=1e-2)


def test_primaries_match_the_reference_values() -> None:
    """Чистые красный и синий — контроль всей цепочки матрицы."""
    red = hex_to_lab("#ff0000")
    assert (red.lightness, red.a, red.b) == pytest.approx((53.24, 80.09, 67.20), abs=0.05)

    blue = hex_to_lab("#0000ff")
    assert (blue.lightness, blue.a, blue.b) == pytest.approx(
        (32.30, 79.19, -107.86), abs=0.05
    )


def test_distance_is_symmetric_and_zero_on_itself() -> None:
    first, second = hex_to_lab("#c3a274"), hex_to_lab("#3b2f2a")
    assert first.distance(first) == pytest.approx(0.0)
    assert first.distance(second) == pytest.approx(second.distance(first))
    assert first.distance(second) > 30.0, "дуб и венге обязаны быть далеко"


def test_parse_hex_refuses_garbage() -> None:
    with pytest.raises(ValueError, match="#rrggbb"):
        parse_hex("c3a274")
    with pytest.raises(ValueError, match="#rrggbb"):
        parse_hex("#c3a2")


def test_lightness_spread_takes_the_closest_pair() -> None:
    """Разброс — минимум по парам, а не размах: слипается узкое место."""
    spread = lightness_spread(["#000000", "#808080", "#8a8a8a"])
    close = hex_to_lab("#8a8a8a").lightness - hex_to_lab("#808080").lightness
    assert spread == pytest.approx(close)


def test_nearest_finds_the_species_of_the_same_tone() -> None:
    """Тёмно-фиолетовый пиксель обязан уйти в амарант, а не в клён."""
    catalogue = load_species()
    palette = {key: hex_to_lab(item.color) for key, item in catalogue.items()}

    key, distance = nearest(Lab(35.0, 18.0, -20.0), palette)
    assert key == "purpleheart", (key, distance)


def test_nearest_is_deterministic_on_ties() -> None:
    """Одинаковые расстояния разрешаются именем — иначе подбор не повторяется."""
    palette = {"b": Lab(50.0, 0.0, 0.0), "a": Lab(50.0, 0.0, 0.0)}
    assert nearest(Lab(50.0, 0.0, 0.0), palette)[0] == "a"


def test_rgb_and_hex_agree() -> None:
    assert rgb_to_lab(*parse_hex("#5a3f2d")) == hex_to_lab("#5a3f2d")
