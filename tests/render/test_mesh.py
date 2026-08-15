"""Меш доски: та же доска, поднятая на высоту, — и это проверяется числом.

3D легко сделать «похожим»: увидеть на глаз, что кривая грань или потерянная
ячейка — не видно. Поэтому здесь всё меряется. Объём без фаски обязан сойтись
с площадью ячеек, помноженной на высоту, точно; съеденное фаской — с длиной
кромки; меш обязан быть замкнутым, иначе это не тело, а набор поверхностей.
"""

import numpy as np
import pytest

from boardforge.core.library import build
from boardforge.core.species import load_species
from boardforge.render.mesh import (
    METRES_PER_MM,
    MeshOptions,
    board_mesh,
    export_glb,
    oiled_colour,
)

TEMPLATES = ("checkerboard", "chevron", "cubes")


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


@pytest.fixture(scope="module")
def board():
    return build("checkerboard").program.run().board


def _cubic_mm(mesh) -> float:
    return mesh.volume / METRES_PER_MM**3


@pytest.mark.parametrize("template", TEMPLATES)
def test_mesh_is_a_closed_body(template, catalogue) -> None:
    """Меш замкнут и согласован по обходу — иначе это не доска, а плёнки."""
    board = build(template).program.run().board
    mesh = board_mesh(board, catalogue)
    assert mesh.is_watertight
    assert mesh.is_winding_consistent


@pytest.mark.parametrize("template", TEMPLATES)
def test_volume_without_chamfer_matches_the_plan(template, catalogue) -> None:
    """Без фаски объём тела равен площади ячеек на высоту — точно.

    Тут и ловится потерянная ячейка, вывернутая наизнанку призма и лишний
    кусок: все три меняют объём, а на картинке не видны.
    """
    board = build(template).program.run().board
    mesh = board_mesh(board, catalogue, MeshOptions(chamfer_mm=0.0))
    plan = sum(piece.area_mm2 for piece in board.pieces) * board.thickness_mm
    assert _cubic_mm(mesh) == pytest.approx(plan, rel=1e-9)


@pytest.mark.parametrize("template", TEMPLATES)
def test_chamfer_eats_the_edge_and_only_the_edge(template, catalogue) -> None:
    """Фаска снимает дерево по периметру, а не по всей крайней ячейке.

    Расчётная величина — длина кромки на квадрат фаски: два скоса, верхний и
    нижний, каждый треугольного сечения. Углы дают недобор в доли процента,
    поэтому допуск односторонний. Первая редакция фаски промахивалась здесь
    в двести раз: скос растягивался на всю крайнюю ячейку.
    """
    board = build(template).program.run().board
    chamfer = 2.0
    plain = _cubic_mm(board_mesh(board, catalogue, MeshOptions(chamfer_mm=0.0)))
    eased = _cubic_mm(board_mesh(board, catalogue, MeshOptions(chamfer_mm=chamfer)))

    expected = board.outline.boundary.length * chamfer**2
    eaten = plain - eased
    assert 0.97 * expected <= eaten <= expected


def test_mesh_stands_on_the_table(board, catalogue) -> None:
    """Доска лежит от нуля до своей высоты и никуда не уезжает."""
    mesh = board_mesh(board, catalogue, MeshOptions(chamfer_mm=0.0))
    low, high = mesh.bounds
    assert low[2] == pytest.approx(0.0)
    assert high[2] == pytest.approx(board.thickness_mm * METRES_PER_MM)


def test_mesh_is_exported_in_metres(board, catalogue) -> None:
    """Габарит меша — метры, как договорился glTF, а не миллиметры.

    В миллиметрах доска приезжает в браузер размером с дом, и камера
    `<model-viewer>` встаёт внутрь неё.
    """
    mesh = board_mesh(board, catalogue)
    low, high = mesh.bounds
    assert (high[0] - low[0]) == pytest.approx(board.width_mm * METRES_PER_MM)
    assert (high[0] - low[0]) < 2.0, "доска шире двух метров — значит, единицы не те"


def test_species_reach_the_colours(board, catalogue) -> None:
    """Цветов у меша столько же, сколько пород в доске: 3D красит по программе."""
    mesh = board_mesh(board, catalogue, MeshOptions(oiled=False))
    used = {piece.species for piece in board.pieces}
    unique = {tuple(row) for row in np.asarray(mesh.visual.vertex_colors)}
    assert len(unique) == len(used)


def test_oil_darkens_the_wood(catalogue) -> None:
    """Масло темнит тон — как темнеет смоченное дерево.

    Проверяется на всех двенадцати породах справочника, а не на одной: правка
    коэффициента не должна где-нибудь высветлять.
    """
    for species in catalogue.values():
        dry = species.palette.base.lstrip("#")
        plain = tuple(int(dry[i : i + 2], 16) for i in (0, 2, 4))
        assert sum(oiled_colour(species.palette.base)) < sum(plain)


def test_glb_is_a_glb(board, catalogue) -> None:
    """Экспорт даёт настоящий контейнер glTF, а не пустышку."""
    data = export_glb(board, catalogue)
    assert data[:4] == b"glTF"
    assert len(data) > 5000


def test_glb_reads_back_with_the_same_volume(board, catalogue) -> None:
    """Файл переживает дорогу: прочитанный обратно, он про ту же доску."""
    import io

    import trimesh

    data = export_glb(board, catalogue, MeshOptions(chamfer_mm=0.0))
    scene = trimesh.load(io.BytesIO(data), file_type="glb")
    restored = scene.to_mesh() if hasattr(scene, "to_mesh") else scene
    plan = sum(piece.area_mm2 for piece in board.pieces) * board.thickness_mm
    assert _cubic_mm(restored) == pytest.approx(plan, rel=1e-6)


def test_negative_chamfer_is_refused() -> None:
    """Отрицательной фаски не бывает, и молча превращать её в ноль нельзя."""
    with pytest.raises(ValueError):
        MeshOptions(chamfer_mm=-1.0)


def test_exported_board_lies_flat(board, catalogue) -> None:
    """В файле доска лежит на столе, а не стоит на ребре.

    У нас вверх смотрит Z, у glTF — Y, и `trimesh` при записи оси не меняет.
    Без поворота `<model-viewer>` показывает доску поставленной на торец;
    поймать это тестом дешевле, чем каждый раз открывать браузер.
    """
    import io

    import trimesh

    data = export_glb(board, catalogue, MeshOptions(chamfer_mm=0.0))
    scene = trimesh.load(io.BytesIO(data), file_type="glb")
    low, high = scene.bounds
    extents = high - low
    assert extents[1] == pytest.approx(board.thickness_mm * METRES_PER_MM, rel=1e-6)
    assert extents[1] < extents[0] and extents[1] < extents[2]
