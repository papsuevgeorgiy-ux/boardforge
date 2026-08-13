"""Структура `species.yaml`: файл правят руками, и рука дрожит.

Отдельно от `test_species.py`: тот проверяет смысл справочника через загруженную
модель, этот — сам файл, до и помимо модели. Разница не формальная. Ключ,
оставшийся без значения (`fades:` вместо `fades: true`), YAML читает как `None`,
`bool(None)` даёт `False`, и признак гаснет молча — модель загрузится, а порода
тихо потеряет свойство. Такое обязано падать здесь, а не всплывать при запуске
CLI и не оставаться незамеченным вовсе.
"""

from pathlib import Path

import pytest
import yaml

from boardforge.core.species import DEFAULT_SPECIES_PATH, load_species

COLOR_FIELDS = ("base", "earlywood", "latewood", "ray")
FRACTION_FIELDS = ("ring_contrast", "ray_contrast", "latewood_fraction")
SIZE_FIELDS = ("ring_width_mm", "ray_width_mm")
PALETTE_FIELDS = (*COLOR_FIELDS, *SIZE_FIELDS, *FRACTION_FIELDS, "verified")

REQUIRED_TOP = ("name", "density", "shrinkage", "palette")
OPTIONAL_TOP = ("open_pores", "allergen", "fades", "note")

VERIFIED_SPECIES = {"oak", "wenge"}
"""Породы, чью палитру человек сверил глазами. Список ведётся вручную."""


@pytest.fixture(scope="module")
def source() -> bytes:
    return Path(DEFAULT_SPECIES_PATH).read_bytes()


@pytest.fixture(scope="module")
def blocks(source: bytes) -> dict:
    return yaml.safe_load(source.decode("utf-8"))


def test_file_is_utf8_without_bom(source: bytes) -> None:
    """Файл остаётся в UTF-8 без BOM.

    Notepad и подобные охотно пересохраняют в cp1251 или дописывают BOM —
    русские названия пород после этого превращаются в мусор, а `yaml` падает
    на первом же символе.
    """
    assert not source.startswith(b"\xef\xbb\xbf")
    source.decode("utf-8")


def test_species_names_survived(blocks: dict) -> None:
    """Названия читаются по-русски, а не кракозябрами."""
    assert blocks["maple_hard"]["name"] == "Клён сахарный"
    assert blocks["wenge"]["name"] == "Венге"
    for key, block in blocks.items():
        assert block["name"].strip(), key


def test_every_block_is_a_mapping(blocks: dict) -> None:
    """Двенадцать пород, каждая — словарь полей."""
    assert len(blocks) == 12
    for key, block in blocks.items():
        assert isinstance(block, dict), key


def test_no_key_left_without_a_value(blocks: dict) -> None:
    """Ни один ключ не остался пустым — это и есть след оборванной правки."""
    for key, block in blocks.items():
        for field, value in block.items():
            assert value is not None, f"{key}: {field} без значения"
        for field, value in block["palette"].items():
            assert value is not None, f"{key}: палитра {field} без значения"


def test_required_fields_present(blocks: dict) -> None:
    """Обязательные поля верхнего уровня на месте, лишних нет."""
    for key, block in blocks.items():
        missing = set(REQUIRED_TOP) - set(block)
        assert not missing, f"{key}: нет полей {sorted(missing)}"
        unknown = set(block) - set(REQUIRED_TOP) - set(OPTIONAL_TOP)
        assert not unknown, f"{key}: лишние поля {sorted(unknown)}"
        assert set(block["shrinkage"]) == {"tangential", "radial"}, key


def test_palette_fields_present_and_exact(blocks: dict) -> None:
    """В палитре ровно ожидаемый набор полей: ни пропусков, ни опечаток.

    Опечатка в имени поля страшнее пропуска: пропуск подставит значение из
    `base`, а опечатка тихо уйдёт в лишний ключ и никогда ни на что не повлияет.
    """
    for key, block in blocks.items():
        palette = block["palette"]
        assert isinstance(palette, dict), f"{key}: палитра не словарь"
        assert set(palette) == set(PALETTE_FIELDS), (
            f"{key}: набор полей палитры {sorted(palette)}"
        )


def test_verified_is_the_last_line_of_the_palette(blocks: dict) -> None:
    """`verified` стоит последним — так его видно, и так его труднее потерять."""
    for key, block in blocks.items():
        assert list(block["palette"])[-1] == "verified", key


def test_palette_types_are_right(blocks: dict) -> None:
    """Цвета — строки, размеры и доли — числа, `verified` — булев.

    `bool` в Python наследник `int`, поэтому проверка на число его пропустила бы:
    `ring_contrast: true` прошло бы как 1. Отсюда явное исключение.
    """
    for key, block in blocks.items():
        palette = block["palette"]
        for field in COLOR_FIELDS:
            value = palette[field]
            assert isinstance(value, str), f"{key}: {field} не строка"
            assert len(value) == 7 and value.startswith("#"), f"{key}: {field}={value}"
            int(value[1:], 16)
        for field in (*SIZE_FIELDS, *FRACTION_FIELDS):
            value = palette[field]
            assert isinstance(value, int | float) and not isinstance(value, bool), (
                f"{key}: {field} не число"
            )
        assert isinstance(palette["verified"], bool), f"{key}: verified не булев"


def test_palette_values_are_in_range(blocks: dict) -> None:
    """Диапазоны те же, что стережёт `Palette`, — но названные по файлу."""
    for key, block in blocks.items():
        palette = block["palette"]
        for field in ("ring_contrast", "ray_contrast"):
            assert 0.0 <= palette[field] <= 1.0, f"{key}: {field}"
        assert 0.0 < palette["latewood_fraction"] < 1.0, key
        for field in SIZE_FIELDS:
            assert palette[field] > 0, f"{key}: {field}"


def test_optional_flags_are_boolean(blocks: dict) -> None:
    """Признаки породы либо отсутствуют, либо булевы.

    Именно здесь пропал `fades: true` у падука: значение стёрли, ключ оставили.
    """
    for key, block in blocks.items():
        for field in ("open_pores", "allergen", "fades"):
            if field in block:
                assert isinstance(block[field], bool), f"{key}: {field} не булев"


def test_verified_species_match_the_list(blocks: dict) -> None:
    """Сверены ровно те породы, что в списке.

    Проверка двусторонняя: ловит и потерянную вручную галочку, и случайно
    проставленную. Меняется вместе со списком, когда сверена очередная порода.
    """
    verified = {key for key, block in blocks.items() if block["palette"]["verified"]}
    assert verified == VERIFIED_SPECIES


def test_file_matches_the_loaded_catalogue() -> None:
    """Файл и модель сходятся: структурная проверка говорит о том же объекте."""
    catalogue = load_species()
    assert len(catalogue) == 12
    unverified = [key for key, item in catalogue.items() if not item.palette.verified]
    assert len(unverified) == 12 - len(VERIFIED_SPECIES)
    assert catalogue["padauk"].fades
