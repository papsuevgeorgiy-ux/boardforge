"""Замер рендера: слои SVG и меш 3D на доске 30×20 с текстурой.

Не тест: порогов здесь нет и падать ему не от чего. Это прибор, и лежит он
в репозитории по одной причине — замеры разных дней должны быть сделаны **тем
же кодом**. На Дне 5 сравнение с прошлым не состоялось именно потому, что
условия прежнего замера были неизвестны, а числа Дня 2 не воспроизвелись.

Меряет с прогревом и медианой из пяти: одиночный холодный вызов приписывает
первой функции весь разогрев numpy, shapely и trimesh. Разброс печатается
рядом с медианой — на этой машине он доходил до половины самой величины,
и читать разницу меньше разброса как «стало быстрее» нельзя.

Запуск из корня проекта:
    $env:PYTHONPATH = "."
    uv run python tools\\bench.py
"""

import statistics
import time

from tests.helpers import build_grid

from boardforge.core.species import load_species
from boardforge.render.mesh import board_mesh, export_glb
from boardforge.render.style import RenderOptions
from boardforge.render.svg import render_board, render_structure, render_texture

COLUMNS = 30
ROWS = 20
REPEATS = 5

TARGET_STRUCTURE_MS = 100.0
"""Ориентир интерактивного слоя из `architecture.md`. Не порог: печатается
рядом с результатом, чтобы не искать его в документе."""

grid = build_grid(COLUMNS, ROWS).apply()
catalogue = load_species()
options = RenderOptions(scale=2.0)


def measure(fn):
    fn(grid, catalogue, options)  # прогрев, в счёт не идёт
    samples = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        fn(grid, catalogue, options)
        samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(samples), min(samples), max(samples)


def _mesh(board, cat, _options):
    return board_mesh(board, cat)


def _glb(board, cat, _options):
    return export_glb(board, cat)


print(
    f"доска {COLUMNS}x{ROWS} = {len(grid.pieces)} ячеек, "
    f"{REPEATS} прогонов после прогрева"
)
for name, fn in (
    ("структура", render_structure),
    ("текстура", render_texture),
    ("полный", render_board),
    ("меш 3D", _mesh),
    ("экспорт glb", _glb),
):
    median, best, worst = measure(fn)
    spread = (worst - best) / best * 100.0
    note = ""
    if name == "структура":
        note = f"  [ориентир {TARGET_STRUCTURE_MS:.0f} мс]"
    print(
        f"{name}: медиана {median:.0f} мс, лучший {best:.0f}, "
        f"худший {worst:.0f} (разброс {spread:.0f}%){note}"
    )
