"""Лист образцов пород: он нужен, чтобы сверить цвета глазами."""

import re
from dataclasses import replace

import pytest

from boardforge.core.species import Palette, Species, load_species
from boardforge.render.swatches import render_swatches

_TEXT = re.compile(r"<text[^>]*>([^<]*)</text>")


@pytest.fixture(scope="module")
def sheet() -> str:
    return render_swatches(load_species())


def test_every_species_gets_a_swatch(sheet: str) -> None:
    """На листе все породы справочника, каждая названа и по-русски, и ключом."""
    catalogue = load_species()
    labels = _TEXT.findall(sheet)
    for key, species in catalogue.items():
        assert species.name in labels
        assert any(line.startswith(f"{key} · ") for line in labels)


def test_unverified_palettes_are_marked(sheet: str) -> None:
    """Помечена каждая несверенная палитра и только она.

    Число берётся из справочника, а не из его размера: сверка шла в три захода
    (ни одной, потом дуб и венге, теперь все двенадцать), и тест переживал
    каждый, не меняя смысла. Сейчас ожидаемое число — ноль.
    """
    catalogue = load_species()
    unverified = [key for key, item in catalogue.items() if not item.palette.verified]
    assert _TEXT.findall(sheet).count("палитра не сверена") == len(unverified)


def test_unverified_palette_keeps_the_mark() -> None:
    """Пометка на месте, когда есть что помечать.

    Пока сверены все двенадцать, `test_unverified_palettes_are_marked` считает
    ноль против нуля и сам по себе прошёл бы и на сломанном рисовальщике.
    Этот тест держит вторую сторону: палитра без галочки помечается.
    """
    species = Species("x", "Тест", 700.0, 8.0, 4.0, Palette.from_base("#c08040"))
    assert "палитра не сверена" in render_swatches({"x": species})


def test_verified_palette_loses_the_mark() -> None:
    """Поставили verified — пометка ушла."""
    palette = replace(Palette.from_base("#c08040"), verified=True)
    species = Species("x", "Тест", 700.0, 8.0, 4.0, palette)
    assert "палитра не сверена" not in render_swatches({"x": species})


def test_sheet_is_deterministic() -> None:
    """Лист тоже часть рендера: побайтово тот же при том же справочнике."""
    catalogue = load_species()
    assert render_swatches(catalogue) == render_swatches(catalogue)


def test_empty_column_count_rejected() -> None:
    """Ноль столбцов — ошибка вызова, а не пустой файл."""
    with pytest.raises(ValueError, match="столбец"):
        render_swatches(load_species(), columns=0)
