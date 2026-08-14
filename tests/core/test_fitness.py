"""Меры узора: каждая проверяется случаем, где ответ известен заранее.

Мера, которую нельзя обмануть нарочно подобранным случаем, ничего не меряет.
Поэтому здесь на каждую меру есть пара «должно быть много» / «должно быть
мало», а не только «функция что-то вернула».
"""

import pytest

from boardforge.core.fitness import (
    REFERENCE_DELTA_E,
    Scores,
    Weights,
    contrast,
    economy,
    feasibility,
    rhythm,
    score,
    species_grid,
    symmetry,
)
from boardforge.core.library import build
from boardforge.core.species import load_species


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


@pytest.fixture
def unfinished():
    """Программа, кончающаяся россыпью деталей: валидатор обязан её отвергнуть."""
    from boardforge.core.ops import Crosscut, Glue, Strip
    from boardforge.core.program import Program

    return Program(
        operations=(
            Glue("A", (Strip("oak", 40.0), Strip("maple_hard", 40.0)), 200.0, 20.0),
            Crosscut("A", 40.0),
        )
    )


LETTERS = {"m": "maple_hard", "w": "walnut_black", "c": "cherry", "o": "oak"}


def _grid(rows: list[str]) -> list[list[str | None]]:
    """Сетка из букв: удобно выписать руками и видно глазом.

    Буквы разворачиваются в настоящие ключи справочника — мера контраста
    берёт цвет из него, и на выдуманной породе молча вернула бы ноль.
    """
    return [
        [None if letter == "." else LETTERS[letter] for letter in row] for row in rows
    ]


def test_contrast_is_full_on_a_maple_walnut_checkerboard(catalogue) -> None:
    """Клён с орехом — эталон контраста: на шахматке мера обязана дойти до края."""
    rows = [
        "".join("mw"[(row + column) % 2] for column in range(16)) for row in range(16)
    ]
    assert contrast(_grid(rows), catalogue) == pytest.approx(1.0, abs=0.02)


def test_stripes_are_half_as_contrasty_as_a_checkerboard(catalogue) -> None:
    """У полос граница только поперёк, вдоль её нет — и мера это видит.

    Не придирка: полосатая доска из тех же двух пород действительно спокойнее
    шахматки, и оценка, не различающая их, ничего не решает.
    """
    rows = [
        "".join("mw"[(row + column) % 2] for column in range(16)) for row in range(16)
    ]
    checker = contrast(_grid(rows), catalogue)
    striped = contrast(_grid(["mw" * 8] * 16), catalogue)
    assert striped == pytest.approx(checker / 2, rel=0.1)


def test_contrast_is_zero_on_one_species(catalogue) -> None:
    grid = _grid(["mmmm"] * 4)
    assert contrast(grid, catalogue) == pytest.approx(0.0)


def test_contrast_counts_how_often_the_border_happens(catalogue) -> None:
    """Редкая граница даёт меньший контраст, чем частая, при тех же породах."""
    dense = _grid(["mw" * 8] * 16)
    sparse = _grid(["m" * 15 + "w"] * 16)
    assert contrast(sparse, catalogue) < contrast(dense, catalogue)


def test_contrast_reference_pair_is_what_the_constant_claims(catalogue) -> None:
    """Порог REFERENCE_DELTA_E обязан отвечать паре, ради которой заведён."""
    from boardforge.core.color import hex_to_lab

    pair = hex_to_lab(catalogue["maple_hard"].color).distance(
        hex_to_lab(catalogue["walnut_black"].color)
    )
    assert pair == pytest.approx(REFERENCE_DELTA_E, abs=1.0)


def test_rhythm_is_high_for_a_repeating_pattern() -> None:
    assert rhythm(_grid(["mwmw" * 6] * 24)) > 0.9


def test_rhythm_is_zero_on_a_blank_board() -> None:
    """Одноцветная доска совпадает сама с собой при любом сдвиге — но ритма
    в ней нет, и поправка на случайное совпадение обязана это увидеть."""
    assert rhythm(_grid(["mmmm"] * 4)) == 0.0


def test_rhythm_is_low_on_noise() -> None:
    import random

    rng = random.Random(7)
    grid = [[rng.choice(["m", "w", "c"]) for _ in range(24)] for _ in range(24)]
    grid = _grid(["".join(row) for row in grid])
    assert rhythm(grid) < 0.35


def test_symmetry_sees_a_mirror() -> None:
    assert symmetry(_grid(["mwccwm"] * 6)) == pytest.approx(1.0)


def test_symmetry_is_low_on_a_one_way_staircase() -> None:
    letters = "mwco"
    rows = [
        "".join(letters[(row + column) % len(letters)] for column in range(20))
        for row in range(20)
    ]
    assert symmetry(_grid(rows)) < 0.6


def test_economy_is_a_fraction_and_orthogonal_beats_angled() -> None:
    """Ортогональный узор экономичнее углового — это и есть вывод Дня 3.

    Проверяется не абсолютное число (оно зависит от припусков), а порядок:
    два угловых реза обязаны стоить дороже, чем ни одного.
    """
    plain = economy(build("checkerboard").program)
    angled = economy(build("chevron").program)

    assert 0.0 < angled < plain < 1.0, (plain, angled)


def test_feasibility_is_one_when_the_validator_is_silent() -> None:
    assert feasibility(build("checkerboard").program) == pytest.approx(1.0)


def test_feasibility_is_zero_for_a_broken_program(unfinished) -> None:
    assert feasibility(unfinished) == pytest.approx(0.0)


def test_repeated_complaints_count_once() -> None:
    """Одна жалоба на сорока полосах — одна проблема, а не сорок.

    У кубов волосяная линия задумана, и валидатор поминает её на каждой полосе.
    Считай их поштучно — узор получил бы оценку неизготовимого, хотя он всего
    лишь дорогой; за дорого отвечает экономичность, а не реализуемость.
    """
    from boardforge.core.library import build
    from boardforge.core.safety import inspect

    program = build("cubes").program
    warnings = [
        issue for issue in inspect(program, program.run()) if issue.level == "warning"
    ]
    assert len(warnings) > 20, "тест потерял смысл: жалоб стало мало"
    assert feasibility(program) > 0.5, "повторы жалоб не схлопнулись"


def test_score_of_a_broken_program_is_zero_everywhere(unfinished) -> None:
    """Мерить контраст у того, что не собирается, бессмысленно."""
    assert score(unfinished) == Scores(0.0, 0.0, 0.0, 0.0, 0.0)


def test_weights_normalise_the_total() -> None:
    scores = Scores(1.0, 1.0, 1.0, 1.0, 1.0)
    assert scores.total() == pytest.approx(1.0)
    assert scores.total(Weights(contrast=3.0, rhythm=1.0)) == pytest.approx(1.0)

    only_contrast = Scores(1.0, 0.0, 0.0, 0.0, 0.0)
    assert only_contrast.total(
        Weights(contrast=1.0, rhythm=0.0, symmetry=0.0, economy=0.0, feasibility=0.0)
    ) == pytest.approx(1.0)


def test_zero_weights_everywhere_is_refused() -> None:
    with pytest.raises(ValueError, match="хотя бы один вес"):
        Weights(0.0, 0.0, 0.0, 0.0, 0.0)


def test_grid_is_measured_by_area_not_by_cells() -> None:
    """Сетка проб — не список ячеек: у неё фиксированный размер."""
    grid = species_grid(build("checkerboard").program, steps=12)
    assert len(grid) == 12
    assert all(len(row) == 12 for row in grid)


def test_every_library_pattern_gets_a_finite_score() -> None:
    """Ни один шаблон библиотеки не должен ронять или ломать оценку."""
    from boardforge.core.library import LIBRARY

    for key in sorted(LIBRARY):
        scores = score(LIBRARY[key]().program)
        for name, value in scores.as_dict().items():
            assert 0.0 <= value <= 1.0, (key, name, value)
        assert scores.feasibility > 0.0, key
