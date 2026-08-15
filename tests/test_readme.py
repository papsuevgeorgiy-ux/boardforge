"""README не ссылается на то, чего нет.

README — первое и часто единственное, что читает посторонний человек. Битая
картинка или путь к файлу, которого больше нет, портят впечатление раньше,
чем он дойдёт до кода. Проверка дешёвая, а гниёт README тихо: файлы переезжают,
текст остаётся.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
TEXT = README.read_text(encoding="utf-8")

IMAGES = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", TEXT)

# Пути в обратных кавычках: только те, что похожи на файл в репозитории,
# — с косой чертой и расширением. `calc/estimate.py` сюда попадает,
# `out/workshop/` (его создаёт команда) — нет.
PATHS = sorted(
    set(re.findall(r"`((?:docs|projects|tools|tests|src)/[\w./-]+\.\w+)`", TEXT))
)


def test_readme_exists_and_is_not_a_stub() -> None:
    assert len(TEXT) > 2000, len(TEXT)


@pytest.mark.parametrize("link", IMAGES)
def test_every_picture_is_in_place(link: str) -> None:
    """Картинки лежат в репозитории: README читают и без запуска кода."""
    assert not link.startswith(("http://", "https://")), (
        f"{link}: картинка из сети — README обязан читаться без неё"
    )
    assert (ROOT / link).exists(), link


@pytest.mark.parametrize("path", PATHS)
def test_every_named_file_exists(path: str) -> None:
    """Файл, названный в README, существует."""
    assert (ROOT / path).exists(), path
