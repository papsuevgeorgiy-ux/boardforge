"""Два слоя рендера: быстрая структура и догоняющая текстура.

Живое редактирование не может ждать текстуру: она стоит втрое дороже всего
остального. Поэтому рендер разнесён на слой, который рисуется всегда и сразу
(полигоны, швы, кромка), и слой, который догоняет отдельным запросом.

Контракт между ними один и жёсткий: структура плюс текстура — это ровно полный
документ. Разойдись они, и превью в браузере перестало бы совпадать с тем, что
уходит в файл и в печать.
"""

import re
import time

import pytest

from boardforge.core.piece import Part
from boardforge.core.species import Species, load_species
from boardforge.render.style import FLAT, RenderOptions
from boardforge.render.svg import (
    TEXTURE_GROUP_ID,
    render_board,
    render_structure,
    render_texture,
)
from tests.helpers import build_grid

EMPTY_GROUP = f'<g id="{TEXTURE_GROUP_ID}"></g>'

STRUCTURE_TIME_LIMIT_S = 0.6
STRUCTURE_SIZE_LIMIT_KB = 128.0
"""Границы быстрого слоя на доске 30×20. Замер на рабочей машине — 78 мс и
60 КБ; предел поднят с запасом, он ловит обвал, а не медленный компьютер."""

_FILLED_POLYGON = re.compile(r'<polygon points="[^"]+" fill="#[0-9a-f]{6}"/>')


@pytest.fixture(scope="module")
def catalogue() -> dict[str, Species]:
    return load_species()


@pytest.fixture(scope="module")
def grid() -> Part:
    return build_grid(30, 20).apply()


def test_layers_compose_into_the_whole(grid: Part, catalogue) -> None:
    """Структура со вставленной текстурой — побайтово полный документ.

    Это и есть контракт двух слоёв. Всё остальное в этом файле — следствия.
    """
    options = RenderOptions(scale=2.0)
    structure = render_structure(grid, catalogue, options)
    texture = render_texture(grid, catalogue, options)
    filled = structure.replace(EMPTY_GROUP, f'<g id="{TEXTURE_GROUP_ID}">{texture}</g>')
    assert filled == render_board(grid, catalogue, options)


def test_structure_has_a_place_for_the_texture(grid: Part, catalogue) -> None:
    """В быстром слое остаётся пустая группа — место, куда встанет текстура."""
    structure = render_structure(grid, catalogue, RenderOptions(scale=2.0))
    assert EMPTY_GROUP in structure


def test_structure_carries_no_texture(grid: Part, catalogue) -> None:
    """Структура — это заливка, швы и кромка, и ничего сверх того."""
    structure = render_structure(grid, catalogue, RenderOptions(scale=2.0))
    assert "clipPath" not in structure
    assert structure.count("<path") == 2


def test_structure_draws_every_cell_and_the_seams(grid: Part, catalogue) -> None:
    """Узор виден уже на быстром слое: ячейка на месте, швы на месте."""
    options = RenderOptions(scale=2.0)
    structure = render_structure(grid, catalogue, options)
    assert len(_FILLED_POLYGON.findall(structure)) == len(grid.pieces)
    assert options.style.seam.color in structure
    assert options.style.edge.color in structure


def test_texture_is_a_fragment_not_a_document(grid: Part, catalogue) -> None:
    """Текстура возвращается куском разметки: её вставляют в готовый документ."""
    texture = render_texture(grid, catalogue, RenderOptions(scale=2.0))
    assert not texture.startswith("<?xml")
    assert "<svg" not in texture
    assert "clipPath" in texture


def test_one_polygon_per_cell_in_both_layers(grid: Part, catalogue) -> None:
    """Текстура не перекрашивает ячейку заново.

    Иначе в документе оказалось бы по два полигона на деталь: лишний вес и
    потерянный инвариант «полигонов столько же, сколько деталей».
    """
    options = RenderOptions(scale=2.0)
    cells = len(grid.pieces)
    assert (
        len(_FILLED_POLYGON.findall(render_structure(grid, catalogue, options))) == cells
    )
    assert len(_FILLED_POLYGON.findall(render_board(grid, catalogue, options))) == cells
    assert not _FILLED_POLYGON.findall(render_texture(grid, catalogue, options))


def test_structure_is_fast_and_small(grid: Part, catalogue) -> None:
    """Быстрый слой держит живое редактирование: доска 30×20 за доли секунды."""
    options = RenderOptions(scale=2.0)
    render_structure(grid, catalogue, options)

    started = time.perf_counter()
    structure = render_structure(grid, catalogue, options)
    elapsed = time.perf_counter() - started
    kilobytes = len(structure.encode("utf-8")) / 1024.0

    assert elapsed < STRUCTURE_TIME_LIMIT_S, f"структура заняла {elapsed:.2f} с"
    assert kilobytes < STRUCTURE_SIZE_LIMIT_KB, f"структура вышла {kilobytes:.0f} КБ"


def test_structure_is_cheaper_than_texture(grid: Part, catalogue) -> None:
    """Ради этого всё и затевалось: текстура заметно дороже структуры."""
    options = RenderOptions(scale=2.0)
    structure = render_structure(grid, catalogue, options)
    texture = render_texture(grid, catalogue, options)
    assert len(texture) > 4 * len(structure)


def test_flat_style_needs_no_second_layer(grid: Part, catalogue) -> None:
    """Где текстуры нет по стилю, второй слой пуст, а не отсутствует."""
    options = RenderOptions(scale=2.0, style=FLAT)
    assert render_texture(grid, catalogue, options) == ""
    assert render_structure(grid, catalogue, options) == render_board(
        grid, catalogue, options
    )


def test_small_scale_needs_no_second_layer(grid: Part, catalogue) -> None:
    """И там, где ячейка мельче порога детализации, тоже."""
    options = RenderOptions(scale=0.2)
    assert render_texture(grid, catalogue, options) == ""
    assert render_structure(grid, catalogue, options) == render_board(
        grid, catalogue, options
    )


def test_layers_are_deterministic(grid: Part, catalogue) -> None:
    """Оба слоя воспроизводимы по отдельности, а не только вместе."""
    options = RenderOptions(scale=2.0)
    assert render_structure(grid, catalogue, options) == render_structure(
        grid, catalogue, options
    )
    assert render_texture(grid, catalogue, options) == render_texture(
        grid, catalogue, options
    )
