"""Ч/б-чертёж: его печатают на офисном лазернике и несут к пиле."""

import re

import pytest
from shapely.geometry import Point

from boardforge.core.library import build
from boardforge.core.species import load_species
from boardforge.core.units import INCHES
from boardforge.render.blueprint import Sheet, render_blueprint
from boardforge.render.style import BLUEPRINT, STYLES, RenderOptions, style_by_name
from boardforge.render.svg import (
    board_cells,
    label_anchor,
    render_board,
    species_letters,
)

_TEXT = re.compile(r"<text[^>]*>([^<]*)</text>")
_COLOR = re.compile(r'(?:fill|stroke)="(#[0-9a-fA-F]{6})"')


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


@pytest.fixture(scope="module")
def board():
    return build("checkerboard").program.run().board


@pytest.fixture(scope="module")
def sheet(board, catalogue):
    return render_blueprint(board, catalogue, sheet=Sheet(step=5, title="Склейка"))


def test_blueprint_is_a_style_not_a_branch() -> None:
    """Режим чертежа — запись в `STYLES`, как превью и плоский."""
    assert style_by_name("blueprint") is BLUEPRINT
    assert BLUEPRINT.name in STYLES


def test_no_colour_survives(board, catalogue) -> None:
    """На чертеже только чёрное и белое: цветного лазерника в цеху нет.

    Проверяется весь документ, а не палитра: серую заливку легко занести
    обратно через фон или обводку, и заметить это на экране трудно — а на
    печати она растрируется в точки и съедает буквы поверх себя.
    """
    drawing = render_board(board, catalogue, RenderOptions(style=BLUEPRINT))
    assert set(_COLOR.findall(drawing)) <= {"#000000", "#ffffff"}


def test_texture_is_off(board, catalogue) -> None:
    """Кольца на чертеже не нужны и мешают: их нет."""
    assert not BLUEPRINT.texture
    drawing = render_board(board, catalogue, RenderOptions(style=BLUEPRINT))
    assert "clipPath" not in drawing


def test_every_species_gets_a_letter(sheet, board, catalogue) -> None:
    """Порода названа буквой, и все буквы разъяснены в обозначениях."""
    letters = species_letters(piece.species for piece in board.pieces)
    assert len(set(letters.values())) == len(letters)
    legend = next(line for line in _TEXT.findall(sheet) if "—" in line)
    for key, letter in letters.items():
        assert f"{letter} — {catalogue[key].name}" in legend


def test_letters_are_stable_across_renders() -> None:
    """Буква породы не пляшет от доски к доске: вчерашняя распечатка не врёт."""
    first = species_letters(["walnut_black", "maple_hard"])
    second = species_letters(["maple_hard", "walnut_black", "maple_hard"])
    assert first == second == {"maple_hard": "A", "walnut_black": "B"}


def test_no_letter_lands_on_a_seam(catalogue) -> None:
    """Ни одна буква не садится на шов. Дефект найден глазами на дне 5.

    Подпись ставилась в центр габаритной рамки ячейки. У ромбов кубов рамка
    широкая, а по короткой диагонали места нет: половина из 291 подписи
    выезжала на шов, и чертёж читался кашей. Меряется зазор до кромки от той
    точки, куда буква реально встанет, — по всем ячейкам всех трёх узоров.
    """
    for name in ("checkerboard", "chevron", "cubes"):
        board = build(name).program.run().board
        for cell in board_cells(board, catalogue, BLUEPRINT):
            anchor = label_anchor(cell.piece.polygon, BLUEPRINT.label.clearance_mm)
            if anchor is None:
                continue
            point = Point(*anchor)
            assert cell.piece.polygon.contains(point), f"{name}: буква вне ячейки"
            clearance = cell.piece.polygon.exterior.distance(point)
            assert clearance >= BLUEPRINT.label.clearance_mm - 1e-9, (
                f"{name}: буква в {clearance:.2f} мм от шва при высоте "
                f"{BLUEPRINT.label.height_mm} мм"
            )


def test_cells_without_room_stay_unlabelled(catalogue) -> None:
    """Ячейка, в которую буква не влезает, остаётся без подписи.

    Обозначение, которое врёт про свою ячейку, хуже отсутствующего. У кубов
    таких ячеек почти половина — узкие клинья по краям и тонкие ромбы.
    """
    board = build("cubes").program.run().board
    cells = board_cells(board, catalogue, BLUEPRINT)
    skipped = [
        cell
        for cell in cells
        if label_anchor(cell.piece.polygon, BLUEPRINT.label.clearance_mm) is None
    ]
    assert skipped, "в этом узоре все ячейки просторные — тест проверял бы пустоту"

    labels = [
        line
        for line in _TEXT.findall(render_blueprint(board, catalogue))
        if len(line) == 1
    ]
    assert len(labels) == len(cells) - len(skipped)


def test_clearance_follows_the_glyph(catalogue) -> None:
    """Порог выведен из буквы, а не задан отдельно.

    Отдельный порог однажды уже разошёлся с высотой буквы — с этого и начался
    дефект. Тест держит связь: буква крупнее требует больше места, и подписей
    становится меньше, а не столько же.
    """
    from dataclasses import replace

    from boardforge.render.style import Label

    assert BLUEPRINT.label.clearance_mm == BLUEPRINT.label.height_mm / 2

    board = build("cubes").program.run().board
    big = replace(BLUEPRINT, label=Label(color="#000000", height_mm=18.0))
    cells = board_cells(board, catalogue, BLUEPRINT)
    fits_small = sum(
        1
        for c in cells
        if label_anchor(c.piece.polygon, BLUEPRINT.label.clearance_mm) is not None
    )
    fits_big = sum(
        1 for c in cells if label_anchor(c.piece.polygon, big.label.clearance_mm)
    )
    assert fits_big < fits_small


def test_dimensions_are_on_the_sheet(sheet, board) -> None:
    """Габарит подписан у самих кромок, а не только в штампе."""
    lines = _TEXT.findall(sheet)
    assert f"{board.width_mm:g} мм" in lines
    assert f"{board.length_mm:g} мм" in lines


def test_step_number_is_in_the_stamp(sheet) -> None:
    """Номер шага виден: чертёж — часть инструкции, а не картинка."""
    assert any(line.startswith("Шаг 5.") for line in _TEXT.findall(sheet))


def test_sheet_without_a_step_says_only_the_title(board, catalogue) -> None:
    """Чертёж доски целиком номера шага не выдумывает."""
    drawing = render_blueprint(board, catalogue, sheet=Sheet(title="Готовая доска"))
    lines = _TEXT.findall(drawing)
    assert "Готовая доска" in lines
    assert not any(line.startswith("Шаг") for line in lines)


def test_inches_reach_the_drawing(board, catalogue) -> None:
    """Единицы — способ прочитать размер, и чертёж их слушает.

    Дюймовая кавычка в разметке экранирована: подписи проходят через `escape`,
    как и всё, что попадает в документ. Искать надо `&quot;`, а не `"`.
    """
    lines = _TEXT.findall(render_blueprint(board, catalogue, units=INCHES))
    assert any("&quot;" in line for line in lines)
    assert not any("мм" in line for line in lines)


def test_footer_does_not_overlap_the_board(sheet, board, catalogue) -> None:
    """Штамп лежит под рисунком, а не поверх него: лист выше на его высоту."""
    from boardforge.render.blueprint import FOOTER_PX, MARGIN_MM
    from boardforge.render.svg import board_canvas

    canvas = board_canvas(board, RenderOptions(style=BLUEPRINT, margin_mm=MARGIN_MM))
    height = float(re.search(r'height="([\d.]+)"', sheet).group(1))
    assert height == pytest.approx(canvas.height_px + FOOTER_PX)


def test_blueprint_is_deterministic(board, catalogue) -> None:
    """Чертёж — часть рендера: побайтово тот же при том же входе."""
    assert render_blueprint(board, catalogue) == render_blueprint(board, catalogue)
