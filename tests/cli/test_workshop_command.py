"""`boardforge workshop` — команда, ради которой затевался День 5.

Проверяется, что она даёт то, с чем можно уйти к пиле: файлы на диске и
короткая сводка в консоль, по которой видно, стоит ли вообще начинать.
"""

import pytest

from boardforge.cli import main


def test_workshop_writes_the_printout(tmp_path, capsys) -> None:
    """Команда кладёт страницу и чертёж и называет главные числа."""
    target = tmp_path / "shop"
    assert main(["workshop", "--template", "checkerboard", "-o", str(target)]) == 0

    page = (target / "workshop.html").read_text(encoding="utf-8")
    assert page.startswith("<!DOCTYPE html>")
    assert (target / "blueprint.svg").read_text(encoding="utf-8").startswith("<?xml")

    printed = capsys.readouterr().out
    assert "закупка" in printed
    assert "себестоимость" in printed
    assert str(target) in printed


def test_workshop_warns_before_the_saw(tmp_path, capsys) -> None:
    """Предупреждения о породах видны в консоли, а не только в файле."""
    assert main(["workshop", "--template", "border", "-o", str(tmp_path / "s")]) == 0
    printed = capsys.readouterr().out
    assert "!" in printed


def test_workshop_reads_a_saved_project(tmp_path, capsys) -> None:
    """Команда работает с сохранённым проектом, а не только с библиотекой."""
    from boardforge.core.library import build

    project = tmp_path / "board.json"
    project.write_text(
        __import__("json").dumps(build("brick").program.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )
    assert main(["workshop", "--project", str(project), "-o", str(tmp_path / "s")]) == 0
    assert "распечатка" in capsys.readouterr().out


def test_workshop_takes_inches(tmp_path) -> None:
    """Единицы доходят до распечатки через командную строку."""
    target = tmp_path / "shop"
    assert (
        main(["workshop", "--template", "stripes", "--units", "inch", "-o", str(target)])
        == 0
    )
    page = (target / "workshop.html").read_text(encoding="utf-8")
    assert "мм" not in page.split("<style>")[0]


def test_unknown_template_is_reported(tmp_path, capsys) -> None:
    """Несуществующий узор — внятная ошибка и код возврата 1."""
    assert main(["workshop", "--template", "нет-такого", "-o", str(tmp_path)]) == 1
    assert "нет такого узора" in capsys.readouterr().err


@pytest.mark.parametrize("template", ["chevron", "cubes"])
def test_angular_patterns_produce_a_printout(tmp_path, template) -> None:
    """Угловые узоры доходят до распечатки — на них расчёт и тяжелее всего."""
    target = tmp_path / template
    assert main(["workshop", "--template", template, "-o", str(target)]) == 0
    assert (target / "workshop.html").exists()
