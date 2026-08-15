"""Сборка демо-проектов, которые лежат в комплекте.

Файлы в `projects/` — обычные проекты BoardForge: программа операций в JSON.
Их можно открыть в редакторе (`boardforge serve --project`), распечатать
в мастерскую (`boardforge workshop --project`) и править руками.

Почему скрипт, а не шесть файлов, набранных однажды: у проекта есть
`schema_version`, и при следующей миграции комплект надо будет пересобрать
одной командой, а не шестью правками вручную.

    uv run python tools/demo_projects.py

Набор подобран не по красоте, а по разнообразию столярной работы: от прямых
резов до двух угловых на двух щитах-близнецах. Порядок — по возрастанию
сложности изготовления, и это же порядок в README.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from boardforge.core.library import LIBRARY  # noqa: E402
from boardforge.io.project import dumps  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "projects"

# Ключ файла → шаблон и его параметры. Размеры — настоящие кухонные доски,
# а не отвлечённые сетки: 300–450 мм по длинной стороне.
DEMOS: dict[str, tuple[str, dict[str, object]]] = {
    "01-checkerboard-classic": (
        "checkerboard",
        {
            "species": ("maple_hard", "walnut_black"),
            "cell_mm": 32.0,
            "columns": 12,
            "rows": 10,
        },
    ),
    "02-stripes-breakfast": (
        "stripes",
        {
            "species": ("ash", "wenge", "cherry"),
            "cell_mm": 28.0,
            "columns": 14,
            "rows": 9,
        },
    ),
    "03-brick-walnut": (
        "brick",
        {
            "species": ("walnut_black", "maple_hard", "cherry"),
            "cell_mm": 30.0,
            "columns": 12,
            "rows": 10,
            "width": 2,
        },
    ),
    "04-diamonds-padauk": (
        "diamonds",
        {
            "species": ("maple_hard", "padauk", "walnut_black"),
            "cell_mm": 26.0,
            "columns": 13,
            "rows": 8,
            "arm": 3,
        },
    ),
    "05-chevron-oak": (
        "chevron",
        {
            "species": ("oak", "wenge"),
            # Крупная ячейка не прихоть: у шеврона длину доски задаёт она,
            # а число повторов растит только ширину. При 30 мм выходила
            # подставка под кружку — 150 × 156 мм.
            "cell_mm": 50.0,
            "angle_deg": 45.0,
            "repeats": 8,
        },
    ),
    "06-cubes-showpiece": (
        "cubes",
        {
            "species": ("maple_hard", "cherry", "wenge"),
            "side_mm": 34.0,
            # Кубам нужно много столбцов: узор обязан сойтись в прямоугольник,
            # и при малом их числе ряды разъезжаются — валидатор такую доску
            # честно не пропускает. 32 столбца дают 324 × 340 мм.
            "columns": 32,
        },
    ),
}


def build_all(out_dir: Path = OUT_DIR) -> list[Path]:
    """Пересобрать комплект. Возвращает записанные пути."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (template, params) in DEMOS.items():
        program = LIBRARY[template](**params).program
        path = out_dir / f"{name}.json"
        path.write_text(dumps(program), encoding="utf-8")
        # Собираем доску здесь же: узор кубов стоит десятки секунд, и строить
        # его второй раз ради строчки отчёта незачем.
        board = program.run().board
        print(
            f"{path.name}: {board.width_mm:.0f} x {board.length_mm:.0f} мм, "
            f"ячеек {len(board.pieces)}, операций {len(program.operations)}"
        )
        written.append(path)
    return written


if __name__ == "__main__":
    build_all()
