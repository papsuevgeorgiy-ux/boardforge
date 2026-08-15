"""Демо-проекты из комплекта открываются, проходят валидатор и собираются.

Комплект — это обещание постороннему человеку: он клонирует репозиторий
и открывает файл, не читав ни строчки кода. Сломанный демо-проект дороже
сломанного теста, потому что ломается он у того, кто не сможет починить.
"""

from pathlib import Path

import pytest

from boardforge.core.program import ProgramError
from boardforge.io.project import load

PROJECTS_DIR = Path(__file__).resolve().parents[2] / "projects"
DEMOS = sorted(PROJECTS_DIR.glob("*.json"))

MIN_DEMOS = 5

# Кухонная доска, а не отвлечённая сетка: комплект показывает вещи,
# которые имеет смысл изготавливать.
MIN_SIDE_MM = 90.0
MAX_SIDE_MM = 600.0


def test_the_kit_is_not_empty() -> None:
    """Комплект на месте — иначе все тесты ниже молча выродятся в ноль."""
    assert len(DEMOS) >= MIN_DEMOS, [p.name for p in DEMOS]


@pytest.mark.parametrize("path", DEMOS, ids=lambda p: p.stem)
def test_demo_project_opens_and_runs(path: Path) -> None:
    """Файл читается, программа законна, доска собирается."""
    program = load(path)

    errors = [str(issue) for issue in program.validate() if issue.level == "error"]
    assert not errors, f"{path.name}: {errors}"

    try:
        board = program.run().board
    except ProgramError as error:  # pragma: no cover - защита от регрессии
        pytest.fail(f"{path.name}: {error}")

    for side in (board.width_mm, board.length_mm):
        assert MIN_SIDE_MM <= side <= MAX_SIDE_MM, (
            f"{path.name}: {board.width_mm:.0f} x {board.length_mm:.0f} мм"
        )


@pytest.mark.parametrize("path", DEMOS, ids=lambda p: p.stem)
def test_readme_lists_the_demo(path: Path) -> None:
    """README перечисляет комплект поимённо, и список обязан не разъезжаться.

    Тест дешёвый, а стережёт он ровно тот случай, ради которого комплект
    и заведён: человек читает README и открывает названный файл.
    """
    readme = (PROJECTS_DIR.parent / "README.md").read_text(encoding="utf-8")
    assert path.name in readme
