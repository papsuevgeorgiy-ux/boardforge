"""Файл проекта: программа туда и обратно, без потерь и без сюрпризов.

Переехало из `web/state.py` вместе с поведением, поэтому проверяется здесь
то же, что раньше проверялось через веб: круг «сохранить — открыть» и внятный
отказ на каждом виде испорченного файла.
"""

import json

import pytest

from boardforge.core.library import build
from boardforge.io.project import ProjectError, dumps, load, loads, save
from tests.helpers import build_checkerboard


@pytest.fixture(scope="module")
def program():
    return build_checkerboard()


def test_round_trip_keeps_the_program(program) -> None:
    """Сохранённое и открытое — та же программа, операция в операцию."""
    assert loads(dumps(program)) == program


@pytest.mark.parametrize("template", ["chevron", "cubes", "windmill"])
def test_round_trip_survives_the_hard_patterns(template) -> None:
    """Круг держится и на угловых узорах, и на двух щитах кубов."""
    program = build(template).program
    assert loads(dumps(program)) == program


def test_file_is_readable_by_a_human(program) -> None:
    """Проект читается глазами: отступы на месте, кириллица не в экранировании.

    Читаемость — не украшение, а причина хранить доску программой: файл
    кладут в git и смотрят в него дифом.
    """
    text = dumps(program)
    assert "\\u" not in text
    assert text.endswith("\n")
    assert "\n  " in text, "без отступов файл не диффабелен"


def test_saved_file_lands_where_asked(program, tmp_path) -> None:
    """Каталог создаётся, файл пишется в UTF-8, путь возвращается."""
    target = save(program, tmp_path / "deep" / "board.json")
    assert target.exists()
    assert load(target) == program


def test_nameless_path_is_refused(program) -> None:
    """Путь без имени файла — отказ словами."""
    from pathlib import Path

    with pytest.raises(ProjectError, match="имя файла"):
        save(program, Path("."))


def test_directory_instead_of_a_file_is_explained(program, tmp_path) -> None:
    """В поле пути указали каталог — самая частая опечатка.

    Ответ обязан быть строкой, а не `PermissionError` из недр `pathlib`:
    путь вводят руками в браузере, и промахнуться тут проще всего.
    """
    with pytest.raises(ProjectError, match="не записывается"):
        save(program, tmp_path)


def test_missing_file_is_explained(tmp_path) -> None:
    """Несуществующий файл объясняется, а не роняет трейсбек."""
    missing = tmp_path / "нет-такого.json"
    with pytest.raises(ProjectError, match="не открывается") as failure:
        load(missing)

    # Путь назван — опечатку в нём человек ищет глазами; английского Errno
    # из недр pathlib в отказе быть не должно.
    assert str(missing) in str(failure.value)
    assert "Errno" not in str(failure.value)


def test_broken_json_is_explained() -> None:
    """Битый JSON и не-JSON различаются в тексте отказа."""
    with pytest.raises(ProjectError, match="это не JSON"):
        loads("{ не json")


def test_valid_json_with_wrong_shape_is_explained() -> None:
    """JSON правильный, а проект — нет: об этом надо сказать иначе."""
    with pytest.raises(ProjectError, match="не читается"):
        loads(json.dumps({"schema_version": 2, "operations": [{"op": "Выдумка"}]}))


def test_core_still_owns_the_shape(program) -> None:
    """Слой файлов не изобретает формат: словарь приходит от ядра как есть."""
    assert json.loads(dumps(program)) == program.to_dict()
