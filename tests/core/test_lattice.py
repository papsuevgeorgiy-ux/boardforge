"""Правило сдвигов: проверка на случаях, где ответ известен заранее.

Главное здесь — не то, что функция считает, а то, что она **отказывается**
считать. Приближение вместо отказа даёт щит, красивый на превью и рваный
в дереве.
"""

import math

import pytest

from boardforge.core.lattice import (
    Lattice,
    NoLatticeSolution,
    ShiftGrid,
    affine_phases,
    search_affine_phases,
    striped_lattice,
)


def test_checkerboard_shift_is_one_cell() -> None:
    """Контроль из Р22: у шахматки сдвиг вдоль вертикали — одна ячейка."""
    lattice = striped_lattice(strip_width_mm=40.0, cycle=2, column_width_mm=40.0)
    # Породный цикл клён/орех — две полосы по 40, вертикальный вектор 80.
    assert lattice.shortest_along(90.0) == pytest.approx(80.0)


def test_axis_along_a_basis_vector_gives_that_vector() -> None:
    lattice = Lattice((20.0, 0.0), (0.0, 120.0))
    assert lattice.shortest_along(0.0) == pytest.approx(20.0)
    assert lattice.shortest_along(180.0) == pytest.approx(20.0)


def test_diagonal_axis_finds_the_integer_combination() -> None:
    """Ось 45° на квадратной решётке — диагональ ячейки."""
    lattice = Lattice((10.0, 0.0), (0.0, 10.0))
    assert lattice.shortest_along(45.0) == pytest.approx(10.0 * math.sqrt(2))


def test_shallow_rational_axis_needs_a_longer_vector() -> None:
    """Ось с наклоном 1:3 — вектор (30, 10), а не ближайший короткий."""
    lattice = Lattice((10.0, 0.0), (0.0, 10.0))
    angle = math.degrees(math.atan2(10.0, 30.0))
    assert lattice.shortest_along(angle) == pytest.approx(math.hypot(30.0, 10.0))


def test_irrational_axis_has_no_solution() -> None:
    """Наклон tg θ = 1/√2 нецелочислен — узор не сойдётся ни при каком сдвиге."""
    lattice = Lattice((10.0, 0.0), (0.0, 10.0))
    angle = math.degrees(math.atan2(1.0, math.sqrt(2)))
    assert lattice.shortest_along(angle) is None


def test_no_solution_is_explained_in_words() -> None:
    """Отказ обязан объяснять, что делать: угол или состав, а не «ошибка»."""
    lattice = Lattice((10.0, 0.0), (0.0, 10.0))
    angle = math.degrees(math.atan2(1.0, math.sqrt(2)))
    with pytest.raises(NoLatticeSolution) as error:
        lattice.quantum_along(angle, "кубы")
    assert "кубы" in str(error.value)
    assert "другой угол реза" in str(error.value)


def test_degenerate_basis_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="параллельны"):
        Lattice((10.0, 0.0), (20.0, 0.0))
    with pytest.raises(ValueError, match="нулевым"):
        Lattice((0.0, 0.0), (0.0, 10.0))


def test_found_vector_really_lies_on_the_axis() -> None:
    """Не длина сама по себе: вектор обязан быть узлом решётки и лежать на оси."""
    lattice = striped_lattice(strip_width_mm=36.0, cycle=3, column_width_mm=20.0)
    for angle in (0.0, 90.0, 45.0, 135.0):
        length = lattice.shortest_along(angle)
        if length is None:
            continue
        radians = math.radians(angle)
        point = (length * math.cos(radians), length * math.sin(radians))
        counts = (point[0] / lattice.first[0], point[1] / lattice.second[1])
        for value in counts:
            assert value == pytest.approx(round(value), abs=1e-9), (angle, counts)


def test_shift_grid_wraps_to_the_nearest_representative() -> None:
    grid = ShiftGrid(quantum_mm=40.0, size=3)
    assert grid.period_mm == pytest.approx(120.0)
    assert grid.offset(4) == pytest.approx(40.0)
    assert grid.wrapped(130.0) == pytest.approx(10.0)
    assert grid.wrapped(-130.0) == pytest.approx(-10.0)


def test_affine_phases_repeat_by_the_grid_size() -> None:
    assert affine_phases(3, 7, slope=2, start=1) == (1, 0, 2, 1, 0, 2, 1)


def test_search_returns_none_when_nothing_fits() -> None:
    """Ни один набор не годится — значит решения нет, а не «вот лучший из плохих»."""
    grid = ShiftGrid(quantum_mm=10.0, size=4)
    assert search_affine_phases(grid, 5, lambda _: None) is None


def test_search_picks_the_best_scoring_pattern() -> None:
    grid = ShiftGrid(quantum_mm=10.0, size=3)
    target = affine_phases(3, 6, slope=2, start=1)

    def score(phases: tuple[int, ...]) -> float | None:
        return 1.0 if phases == target else 0.0

    assert search_affine_phases(grid, 6, score) == target
