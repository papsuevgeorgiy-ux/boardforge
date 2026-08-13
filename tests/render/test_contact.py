"""Контактный лист: все доски и породы на одной странице."""

import re

import pytest

from boardforge.core.species import load_species
from boardforge.render.contact import render_contact_sheet, sheet_of
from boardforge.render.style import RenderOptions
from boardforge.render.svg import render_board
from tests.helpers import build_checkerboard, build_two_panels

_ID = re.compile(r'\bid="([^"]+)"')
_VIEWBOX = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


@pytest.fixture(scope="module")
def boards(catalogue) -> dict[str, str]:
    options = RenderOptions(scale=2.0)
    return {
        "шахматка": render_board(build_checkerboard().apply(), catalogue, options),
        "два щита": render_board(build_two_panels().apply(), catalogue, options),
    }


@pytest.fixture(scope="module")
def sheet(boards, catalogue) -> str:
    return render_contact_sheet(boards, catalogue)


def test_sheet_is_one_document(sheet: str) -> None:
    """На выходе один разбираемый документ, а не склейка кусков."""
    from xml.etree import ElementTree

    assert sheet.startswith("<?xml")
    root = ElementTree.fromstring(sheet)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"


def test_sheet_holds_every_board_and_the_species(sheet: str, boards) -> None:
    """Доски и лист пород — все на одной странице, каждая своим документом."""
    from xml.etree import ElementTree

    root = ElementTree.fromstring(sheet)
    nested = root.findall(".//{http://www.w3.org/2000/svg}svg")
    assert len(nested) == len(boards) + 1

    for title in boards:
        assert title in sheet
    assert "Клён сахарный" in sheet
    assert "Венге" in sheet


def test_identifiers_never_collide(sheet: str) -> None:
    """Идентификаторы разведены по документам.

    У каждой доски своя обрезка ячеек, и называется она одинаково — `cell0`.
    Столкнись имена в общем листе, `clipPath` первой доски начал бы обрезать
    текстуру остальных: доски вышли бы наполовину без колец и со штрихами
    за краями. Молча и только на этом листе.
    """
    identifiers = _ID.findall(sheet)
    assert identifiers
    assert len(identifiers) == len(set(identifiers))


def test_references_follow_the_renamed_identifiers(sheet: str) -> None:
    """Ссылки переименованы вместе с идентификаторами, а не осиротели."""
    declared = set(_ID.findall(sheet))
    for referenced in re.findall(r"url\(#([^)]+)\)", sheet):
        assert referenced in declared


def test_sheet_grows_with_its_content(boards, catalogue) -> None:
    """Лист ровно такой высоты, чтобы вместить содержимое."""
    one = render_contact_sheet({"одна": next(iter(boards.values()))}, catalogue)
    two = render_contact_sheet(boards, catalogue)
    assert float(_VIEWBOX.search(two).group(2)) > float(_VIEWBOX.search(one).group(2))


def test_sheet_is_deterministic(boards, catalogue) -> None:
    """Контрольный отпечаток обязан быть воспроизводимым."""
    assert render_contact_sheet(boards, catalogue) == render_contact_sheet(
        boards, catalogue
    )


def test_broken_input_is_reported(catalogue) -> None:
    """Не документ SVG — внятная ошибка, а не пустой лист."""
    with pytest.raises(ValueError, match="viewBox"):
        sheet_of("мусор", "<p>это не svg</p>")
