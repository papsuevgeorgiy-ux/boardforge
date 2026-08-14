"""Импорт картинки: подбор по цвету и подгон под то, что можно склеить.

Проверяется не «похоже», а два конкретных обещания: породу выбирают в CIELAB,
а результат обязан быть изготовим — то есть каждый столбец доски обязан
совпадать с набором реек какого-то щита, и щитов ровно столько, сколько
заказано.
"""

import pytest

from boardforge.core.imaging import Mosaic, downsample, quantise
from boardforge.core.safety import inspect
from boardforge.core.species import load_species

WHITE = (255, 255, 255)
BLACK = (20, 16, 14)


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


def _solid(colour, width=24, height=24):
    return [[colour] * width for _ in range(height)]


def _halves(top, bottom, width=24, height=24):
    return [[top if row < height // 2 else bottom] * width for row in range(height)]


def test_downsample_flips_rows_to_strip_order(catalogue) -> None:
    """У растра первая строка сверху, у щита первая рейка снизу."""
    pixels = _halves(WHITE, BLACK)
    grid = downsample(pixels, columns=2, rows=2)

    # Нижняя рейка (индекс 0) обязана взять тёмный низ картинки.
    assert grid[0][0].lightness < grid[0][1].lightness


def test_downsample_averages_in_light_not_in_numbers() -> None:
    """Среднее чёрного и белого светлее, чем среднее их чисел в файле.

    Если усреднять в sRGB, серединой выйдет тон около L*=54; в линейном
    свете — около L*=76. Второе физически верно, и разница видна глазом.
    """
    pixels = [[(0, 0, 0), (255, 255, 255)]]
    (cell,) = downsample(pixels, columns=1, rows=1)
    assert cell[0].lightness > 70.0


def test_solid_white_goes_to_the_lightest_species(catalogue) -> None:
    mosaic = quantise(_solid(WHITE), catalogue, columns=4, rows=4, billets=1)
    used = {species for strips in mosaic.billets for species in strips}
    assert used == {"hornbeam"}, used


def test_solid_dark_goes_to_the_darkest_species(catalogue) -> None:
    mosaic = quantise(_solid(BLACK), catalogue, columns=4, rows=4, billets=1)
    used = {species for strips in mosaic.billets for species in strips}
    assert used == {"wenge"}, used


def test_choice_is_perceptual_not_arithmetic(catalogue) -> None:
    """Подбор идёт в CIELAB — на этом и стоит модуль.

    Проверяется через светлоту: тёмный пиксель обязан уйти в породу, чья
    светлота к нему ближе всех, а не в ту, чьи байты ближе.
    """
    from boardforge.core.color import hex_to_lab, rgb_to_lab

    pixel = (140, 90, 60)
    mosaic = quantise(_solid(pixel), catalogue, columns=2, rows=2, billets=1)
    chosen = mosaic.billets[0][0]

    want = rgb_to_lab(*(channel / 255 for channel in pixel))
    distances = {
        key: want.distance(hex_to_lab(item.color)) for key, item in catalogue.items()
    }
    assert chosen == min(distances, key=lambda key: distances[key])


def test_every_column_is_a_real_billet(catalogue) -> None:
    """Главное ограничение: столбец — это срез щита, а не свободный набор."""
    pixels = [
        [WHITE if (column // 6 + row // 6) % 2 else BLACK for column in range(24)]
        for row in range(24)
    ]
    mosaic = quantise(pixels, catalogue, columns=10, rows=8, billets=3)

    assert 1 < len(mosaic.billets) <= 3
    assert set(mosaic.columns) <= set(range(len(mosaic.billets)))
    for column in mosaic.result:
        assert column in mosaic.billets


def test_identical_columns_need_only_one_billet(catalogue) -> None:
    """Щитов выходит не больше заказанного, а сколько нужно.

    Картинка из одинаковых столбцов делается одним щитом; клеить три
    одинаковых — три склейки, три строгания и три обрезки впустую.
    """
    mosaic = quantise(_halves(WHITE, BLACK), catalogue, columns=10, rows=8, billets=3)
    assert len(mosaic.billets) == 1
    assert mosaic.fidelity == pytest.approx(1.0)


def test_result_is_makeable(catalogue) -> None:
    """И собирается: валидатор и проверка изготовимости молчат."""
    mosaic = quantise(_halves(WHITE, BLACK), catalogue, columns=12, rows=10, billets=2)

    assert not mosaic.program.errors, [str(i) for i in mosaic.program.errors]
    execution = mosaic.program.run()
    errors = [i for i in inspect(mosaic.program, execution) if i.level == "error"]
    assert not errors, [str(i) for i in errors]


def test_fidelity_is_honest_about_what_was_lost(catalogue) -> None:
    """Точность — доля совпавших ячеек, и она обязана падать с числом щитов.

    Один щит не может передать картинку, у которой столбцы разные; два могут
    больше. Инструмент, который этого не показывает, обещает фотографию.
    """
    pixels = [
        [WHITE if (column // 4 + row // 4) % 2 else BLACK for column in range(24)]
        for row in range(24)
    ]
    poor = quantise(pixels, catalogue, columns=12, rows=8, billets=1)
    rich = quantise(pixels, catalogue, columns=12, rows=8, billets=4)

    assert 0.0 <= poor.fidelity <= 1.0
    assert rich.fidelity > poor.fidelity, (poor.fidelity, rich.fidelity)


def test_one_billet_gives_identical_columns(catalogue) -> None:
    """Вырожденный случай честен: из одного щита выходят вертикальные полосы."""
    pixels = [
        [WHITE if column < 12 else BLACK for column in range(24)] for _ in range(24)
    ]
    mosaic = quantise(pixels, catalogue, columns=8, rows=6, billets=1)
    assert len(set(mosaic.result)) == 1


def test_quantisation_is_deterministic(catalogue) -> None:
    pixels = _halves(WHITE, BLACK)
    first = quantise(pixels, catalogue, columns=9, rows=7, billets=2)
    second = quantise(pixels, catalogue, columns=9, rows=7, billets=2)
    assert first.billets == second.billets
    assert first.columns == second.columns
    assert first.program.operations == second.program.operations


def test_allowed_species_are_respected(catalogue) -> None:
    """Столяр покупает то, что есть в мастерской, а не что подберёт солвер."""
    mosaic = quantise(
        _halves(WHITE, BLACK),
        catalogue,
        columns=8,
        rows=6,
        billets=2,
        allowed=("maple_hard", "wenge"),
    )
    used = {species for strips in mosaic.billets for species in strips}
    assert used <= {"maple_hard", "wenge"}


def test_more_billets_than_columns_is_refused(catalogue) -> None:
    with pytest.raises(ValueError, match="больше"):
        quantise(_solid(WHITE), catalogue, columns=4, rows=4, billets=5)


def test_unknown_species_is_reported(catalogue) -> None:
    with pytest.raises(ValueError, match="нет в справочнике"):
        quantise(_solid(WHITE), catalogue, allowed=("unobtainium",))


def test_empty_image_is_reported(catalogue) -> None:
    with pytest.raises(ValueError, match="пуста"):
        quantise([], catalogue)


def test_mosaic_result_matches_its_billets(catalogue) -> None:
    mosaic: Mosaic = quantise(_halves(WHITE, BLACK), catalogue, columns=6, rows=5)
    assert mosaic.result == tuple(mosaic.billets[i] for i in mosaic.columns)
    assert len(mosaic.target) == 6
    assert all(len(column) == 5 for column in mosaic.target)
