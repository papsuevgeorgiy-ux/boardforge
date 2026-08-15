"""SVG-рендер доски: структура, детерминизм, уровни детализации."""

import hashlib
import re
import subprocess
import sys

import pytest

from boardforge.core.program import Program
from boardforge.core.species import Species, load_species
from boardforge.render.style import FLAT, PREVIEW, RenderOptions, style_by_name
from boardforge.render.svg import RenderError, render_board

REFERENCE = RenderOptions(scale=2.0, style=PREVIEW, margin_mm=6.0)

REFERENCE_SHA256 = "071e458e192f61d85831cd7b038dc217c5f50552b94342de9ee6e506c9fd6400"
"""Эталон обновлён на Дне 6, и вот почему.

Кромка доски стала округляться перед объединением (`set_precision` в
`board_body`) — иначе `unary_union` оставлял между ячейками щели нулевой
ширины, и у кубов контур выходил из 61 кольца. На шахматке щелей нет, но
округление **перенумеровывает** кольцо: путь начинается с другой вершины.

Проверено, что рисунок при этом тот же, а не «похожий»: у контура было
36 вершин и осталось 36, множества точек совпадают, полигоны геометрически
равны, площадь 288000.0 мм² до и после, длина документа 92 566 байт до и
после. Изменилась одна вершина старта: (252, 252) → (172, 252), и та же
(252, 252) встала в конец.
"""

_FILLED_POLYGON = re.compile(r'<polygon points="([^"]+)" fill="(#[0-9a-f]{6})"/>')
_VIEWBOX = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')


@pytest.fixture(scope="module")
def catalogue() -> dict[str, Species]:
    return load_species()


def render(program: Program, options: RenderOptions | None = None) -> str:
    return render_board(program.apply(), load_species(), options or REFERENCE)


def _filled(svg: str) -> list[tuple[str, str]]:
    """Залитые полигоны — это ячейки. У полигонов внутри clipPath заливки нет."""
    return _FILLED_POLYGON.findall(svg)


def _shapes(svg: str) -> set[tuple[frozenset[str], str]]:
    """Ячейки как фигуры: без учёта порядка обхода вершин.

    Поворот детали на 180° переставляет вершины контура, но квадрат остаётся
    тем же квадратом — сравнивать надо форму, а не запись.
    """
    return {(frozenset(points.split(" ")), fill) for points, fill in _filled(svg)}


def test_document_is_well_formed(checkerboard: Program) -> None:
    """На выходе разбираемый XML со своим заголовком и размерами."""
    from xml.etree import ElementTree

    svg = render(checkerboard)
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ElementTree.fromstring(svg)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.get("width") and root.get("height")


def test_one_polygon_per_cell(checkerboard: Program) -> None:
    """Число залитых полигонов совпадает с числом ячеек доски."""
    board = checkerboard.apply()
    svg = render(checkerboard)
    assert len(_filled(svg)) == len(board.pieces)


def test_fills_come_from_the_palette(
    checkerboard: Program, catalogue: dict[str, Species]
) -> None:
    """Рендер не изобретает цветов: любая заливка есть в палитре какой-то породы."""
    allowed = {color for item in catalogue.values() for color in item.palette.colors}
    used = {fill for _, fill in _filled(render(checkerboard))}
    assert used <= allowed
    assert used


def test_nothing_leaves_the_board(checkerboard: Program) -> None:
    """Ни одна деталь не выходит за границы документа."""
    svg = render(checkerboard)
    width, height = (float(value) for value in _VIEWBOX.search(svg).groups())
    for points, _ in _filled(svg):
        for point in points.split(" "):
            x, y = (float(value) for value in point.split(","))
            assert -1e-6 <= x <= width + 1e-6
            assert -1e-6 <= y <= height + 1e-6


def test_margin_keeps_the_board_inside(checkerboard: Program) -> None:
    """Поле вокруг доски пустое: обводка кромки не срезается краем документа."""
    svg = render(checkerboard)
    margin_px = REFERENCE.margin_mm * REFERENCE.scale
    width, height = (float(value) for value in _VIEWBOX.search(svg).groups())
    for points, _ in _filled(svg):
        for point in points.split(" "):
            x, y = (float(value) for value in point.split(","))
            assert margin_px - 1e-6 <= x <= width - margin_px + 1e-6
            assert margin_px - 1e-6 <= y <= height - margin_px + 1e-6


def test_seams_are_drawn(checkerboard: Program) -> None:
    """Клеевые швы обязательны: без них доска выглядит нарисованной."""
    svg = render(checkerboard)
    assert PREVIEW.seam.color in svg
    assert PREVIEW.edge.color in svg


def test_render_is_byte_identical(checkerboard: Program) -> None:
    """Один и тот же проект — побайтово тот же файл."""
    assert render(checkerboard) == render(checkerboard)


def test_render_is_identical_across_processes(tmp_path) -> None:
    """Детерминизм переживает перезапуск: сид не берётся из `hash()`.

    Встроенный `hash` для строк солится при каждом старте интерпретатора.
    Проверять это в одном процессе бессмысленно, поэтому здесь второй.
    """
    script = (
        "import hashlib;"
        "from boardforge.core.species import load_species;"
        "from boardforge.render.svg import render_board;"
        "from boardforge.render.style import RenderOptions;"
        "from tests.helpers import build_checkerboard;"
        "svg = render_board(build_checkerboard().apply(), load_species(),"
        " RenderOptions(scale=2.0, margin_mm=6.0));"
        "print(hashlib.sha256(svg.encode('utf-8')).hexdigest())"
    )
    digests = set()
    for seed in ("0", "1", "random"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "", "SYSTEMROOT": ""},
        )
        digests.add(result.stdout.strip())
    assert len(digests) == 1


def test_reference_snapshot(checkerboard: Program) -> None:
    """Снапшот эталонной доски. Хеш меняется — значит изменился рисунок.

    Тест не про правильность, а про осознанность: увидел падение — посмотри
    глазами на `out/checkerboard.svg` и обнови хеш, если так и задумано.
    """
    digest = hashlib.sha256(render(checkerboard).encode("utf-8")).hexdigest()
    assert digest == REFERENCE_SHA256


def test_small_cells_lose_the_texture(checkerboard: Program) -> None:
    """Мелкий масштаб — заливка со швами: кольца в такую ячейку не влезут."""
    board = checkerboard.apply()
    coarse = render(checkerboard, RenderOptions(scale=0.1))
    fine = render(checkerboard, RenderOptions(scale=4.0))

    assert "clipPath" not in coarse
    assert "clipPath" in fine
    assert len(_filled(coarse)) == len(board.pieces)
    assert len(coarse) < len(fine) / 4


def test_lod_uses_the_base_tone(
    checkerboard: Program, catalogue: dict[str, Species]
) -> None:
    """Без текстуры ячейка красится основным тоном, а не ранней древесиной."""
    coarse = render(checkerboard, RenderOptions(scale=0.1))
    bases = {item.palette.base for item in catalogue.values()}
    assert {fill for _, fill in _filled(coarse)} <= bases


def test_flat_style_has_no_texture(checkerboard: Program) -> None:
    """Плоский режим — тот же узор без единого кольца."""
    board = checkerboard.apply()
    flat = render(checkerboard, RenderOptions(style=FLAT))
    assert "clipPath" not in flat
    assert len(_filled(flat)) == len(board.pieces)


def test_style_is_a_parameter() -> None:
    """Режим выбирается по имени, а не пересборкой рендера."""
    assert style_by_name("preview") is PREVIEW
    assert style_by_name("flat") is FLAT
    with pytest.raises(ValueError, match="неизвестный режим"):
        style_by_name("сепия")


def _reversible(reversed_flag: bool) -> Program:
    """Доска из одной детали, которую можно поставить прямо или развёрнуто."""
    from boardforge.core.ops import Assemble, Crosscut, Glue, PieceRef, StandOnEnd, Strip

    return Program(
        operations=(
            Glue(
                id="A",
                strips=(Strip("oak", 40.0), Strip("oak", 40.0)),
                length_mm=80.0,
                thickness_mm=40.0,
            ),
            Crosscut(source="A", step_mm=40.0),
            StandOnEnd(source="A"),
            Assemble(
                id="B",
                pieces=(PieceRef("A", 0), PieceRef("A", 1)),
                reversed=(False, reversed_flag),
                offsets_mm=(0.0, 0.0),
            ),
        )
    )


def test_reversed_part_turns_its_texture() -> None:
    """Развёрнутая деталь показывает развёрнутый рисунок волокон.

    Узор от разворота здесь не меняется — обе ячейки одной породы, — значит
    отличаться могут только кольца. Если бы текстура рисовалась в координатах
    доски, файлы совпали бы, и половина узоров Дня 4 стала бы неотличима.
    """
    options = RenderOptions(scale=4.0)
    straight = render(_reversible(False), options)
    turned = render(_reversible(True), options)

    assert _shapes(straight) == _shapes(turned)
    assert straight != turned


def test_flipped_part_mirrors_its_texture() -> None:
    """`flipped` на узор не влияет (Р7), но рисунок волокон отражает."""
    from dataclasses import replace

    from boardforge.core.ops import Assemble

    base = _reversible(False)
    operations = list(base.operations)
    assemble = operations[-1]
    assert isinstance(assemble, Assemble)
    operations[-1] = replace(assemble, flipped=(False, True))
    mirrored = Program(operations=tuple(operations))

    options = RenderOptions(scale=4.0)
    assert _shapes(render(base, options)) == _shapes(render(mirrored, options))
    assert render(base, options) != render(mirrored, options)


def test_narrow_latewood_reads_darker() -> None:
    """Узкая поздняя зона темнее широкой при том же контрасте."""
    from dataclasses import replace

    from boardforge.core.species import Palette
    from boardforge.render.svg import _latewood_opacity

    wide = Palette.from_base("#c08040", ring_width_mm=3.0)
    narrow = replace(wide, latewood_fraction=wide.latewood_fraction / 3.0)
    assert _latewood_opacity(narrow) > _latewood_opacity(wide)
    assert _latewood_opacity(narrow) <= 1.0


def test_ray_widths_reach_the_document(catalogue: dict[str, Species]) -> None:
    """Толщина луча из палитры доходит до файла и разбивается по путям."""
    board = _reversible(False).apply()
    svg = render_board(board, catalogue, RenderOptions(scale=4.0))
    strokes = set(re.findall(r'stroke="#ddc9a6" stroke-width="([\d.]+)"', svg))
    assert len(strokes) > 1


def test_two_panels_render(two_panels: Program) -> None:
    """Доска из нескольких щитов рисуется целиком."""
    board = two_panels.apply()
    assert len(_filled(render(two_panels))) == len(board.pieces)


def test_unknown_species_is_reported(checkerboard: Program) -> None:
    """Порода не из справочника — внятная ошибка, а не чёрная ячейка."""
    board = checkerboard.apply()
    with pytest.raises(RenderError, match="справочнике"):
        render_board(board, {}, REFERENCE)
