"""Верхние границы рендера: доска 30×20 ячеек с текстурой.

Границы заведомо выше замеров на рабочей машине — тест ловит не медленный
компьютер, а обвал производительности или разбухание файла: кольцо, нарисованное
окружностью в метр радиусом, или текстура, не выключившаяся на мелком масштабе.
"""

import time

import pytest

from boardforge.core.piece import Part
from boardforge.core.species import Species, load_species
from boardforge.render.style import FLAT, RenderOptions
from boardforge.render.svg import render_board
from tests.helpers import build_grid

COLUMNS = 30
ROWS = 20

TIME_LIMIT_S = 3.0
SIZE_LIMIT_KB = 1024.0
COARSE_SIZE_LIMIT_KB = 128.0


@pytest.fixture(scope="module")
def catalogue() -> dict[str, Species]:
    return load_species()


@pytest.fixture(scope="module")
def grid() -> Part:
    return build_grid(COLUMNS, ROWS).apply()


def _render(board: Part, catalogue: dict[str, Species], options: RenderOptions):
    started = time.perf_counter()
    svg = render_board(board, catalogue, options)
    return time.perf_counter() - started, len(svg.encode("utf-8")) / 1024.0


def test_grid_has_the_expected_cells(grid: Part) -> None:
    """Сначала убедимся, что меряем ту доску, которую собирались."""
    assert len(grid.pieces) == COLUMNS * ROWS


def test_textured_board_stays_within_limits(
    grid: Part, catalogue: dict[str, Species]
) -> None:
    """600 ячеек с кольцами — секунды и мегабайта хватать не должно."""
    elapsed, kilobytes = _render(grid, catalogue, RenderOptions(scale=2.0))
    assert elapsed < TIME_LIMIT_S, f"рендер занял {elapsed:.2f} с"
    assert kilobytes < SIZE_LIMIT_KB, f"файл вышел {kilobytes:.0f} КБ"


def test_detail_level_cuts_the_file(grid: Part, catalogue: dict[str, Species]) -> None:
    """На мелком масштабе текстура выключается, и файл падает в разы."""
    _, textured = _render(grid, catalogue, RenderOptions(scale=2.0))
    elapsed, coarse = _render(grid, catalogue, RenderOptions(scale=0.5))
    assert coarse < COARSE_SIZE_LIMIT_KB, f"файл вышел {coarse:.0f} КБ"
    assert coarse < textured / 4.0
    assert elapsed < TIME_LIMIT_S


def test_flat_style_is_cheap(grid: Part, catalogue: dict[str, Species]) -> None:
    """Плоская заливка не платит за текстуру ни временем, ни весом."""
    _, textured = _render(grid, catalogue, RenderOptions(scale=2.0))
    elapsed, flat = _render(grid, catalogue, RenderOptions(scale=2.0, style=FLAT))
    assert flat < COARSE_SIZE_LIMIT_KB
    assert flat < textured / 4.0
    assert elapsed < TIME_LIMIT_S
