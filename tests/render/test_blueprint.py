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


def _sheet_size(svg: str) -> tuple[float, float]:
    """Ширина и высота листа из заголовка документа."""
    found = re.search(r'width="([\d.]+)" height="([\d.]+)"', svg)
    assert found, "у документа должны быть размеры"
    return float(found.group(1)), float(found.group(2))


def test_dimension_room_survives_a_small_scale(board, catalogue) -> None:
    """На мелком масштабе поле раздвигается: цифре размера нужны пиксели, не мм.

    Дефект был настоящий и виден на бумаге: чертёж шага приводится к ширине
    листа, масштаб падает ниже единицы, одиннадцать миллиметров отступа дают
    меньше десяти пикселей — и кромка доски проходит сквозь подпись «648 мм».
    """
    from boardforge.render.blueprint import (
        MIN_MARGIN_PX,
        MIN_OFFSET_PX,
        sheet_margin_mm,
        sheet_offset_mm,
    )

    for scale in (0.2, 0.5, 0.9, 1.2):
        assert sheet_margin_mm(scale) * scale >= MIN_MARGIN_PX - 1e-9
        assert sheet_offset_mm(scale) * scale >= MIN_OFFSET_PX - 1e-9


def test_generous_scale_keeps_the_original_field(board, catalogue) -> None:
    """При рабочем масштабе чертежа поле прежнее — пиксельный порог не мешает.

    Якорь к Дню 5: вид готового чертежа менять было не за чем, чинили только
    мелкий масштаб.
    """
    from boardforge.render.blueprint import (
        MARGIN_MM,
        OFFSET_MM,
        sheet_margin_mm,
        sheet_offset_mm,
    )

    assert sheet_margin_mm(2.0) == MARGIN_MM
    assert sheet_offset_mm(2.0) == OFFSET_MM


def test_narrow_part_still_fits_its_stamp(catalogue) -> None:
    """Лист не бывает уже штампа: узкая полоса не обрезает «Шаг 2. Торцовка».

    Полоса берётся настоящая — из кадра после торцовки, а не выдуманная:
    именно на ней штамп и обрывался.
    """
    from boardforge.render.blueprint import MIN_SHEET_PX

    program = build("chevron").program
    strip = program.trace()[1].parts[0]
    assert strip.width_mm < 100.0, "после торцовки полоса обязана быть узкой"

    svg = render_blueprint(
        strip, catalogue, RenderOptions(scale=0.5), Sheet(step=2, title="Торцовка")
    )
    width, _ = _sheet_size(svg)
    assert width >= MIN_SHEET_PX
    assert "Шаг 2. Торцовка" in svg


def test_board_edge_is_one_contour_on_cubes(catalogue) -> None:
    """Кромка доски обводится один раз, а не по каждой щели внутри узора.

    `unary_union` соседних ячеек оставляет между ними щели нулевой ширины:
    у кубов контур выходил из 61 кольца вместо одного, и каждая из шестидесяти
    щелей обводилась толщиной кромки. На чертеже это толстые отрезки,
    разбросанные по узору, — их читают как рёбра кубов, а это артефакт.
    Тот же дефект чинили на Дне 4 в `Part.outline`; сюда починка не доехала,
    потому что здесь своё объединение.

    Считаются **кольца**, а не полигоны: щели приходят дырками внутри одного
    полигона, и счёт полигонов их не видит — на этом легко успокоиться зря.
    """
    from shapely import set_precision
    from shapely.ops import unary_union

    from boardforge.core.piece import SNAP_MM

    board = build("cubes").program.run().board
    raw = unary_union([piece.polygon for piece in board.pieces])
    raw_rings = sum(1 + len(g.interiors) for g in getattr(raw, "geoms", (raw,)))
    assert raw_rings > 1, "на этом узоре щелей нет — тест проверял бы пустоту"

    edge = set_precision(raw, SNAP_MM)
    rings = sum(1 + len(g.interiors) for g in getattr(edge, "geoms", (edge,)))
    assert rings == 1


def test_blueprint_draws_the_rounded_edge(catalogue) -> None:
    """Чертёж кубов рисует кромку одним контуром — округление доехало до листа.

    Проверка сквозная, а не по геометрии: округлить контур и забыть отдать его
    рисовальщику — ровно та ошибка, которая уже случалась.
    """
    board = build("cubes").program.run().board
    svg = render_blueprint(board, catalogue, RenderOptions(scale=1.0))
    edge_path = re.findall(r'<path d="([^"]+)" stroke-linejoin="round"[^>]*>', svg)
    assert edge_path, "кромка рисуется отдельным путём"
    assert edge_path[-1].count("Z") == 1, "кромка обведена больше одного раза"
