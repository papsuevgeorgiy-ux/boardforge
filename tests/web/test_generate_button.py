"""«Удиви меня» в браузере: первое, что нажмут, и то, чего до Дня 5 не было.

Генератор жил только в CLI. Проверяется здесь не «кнопка есть», а то, ради
чего она нужна: узор меняется, сид возвращается на экран и по нему всё
повторяется, а оценки на панели относятся именно к тому, что нарисовано.
"""

import re

import pytest
from fastapi.testclient import TestClient

from boardforge.core.library import LIBRARY
from boardforge.web import create_app
from tests.helpers import build_checkerboard

SEED_FIELD = re.compile(r'name="seed"[^>]*value="(\d*)"')


@pytest.fixture
def app():
    return create_app(build_checkerboard())


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def test_panel_is_on_the_page(client: TestClient) -> None:
    """Панель на месте, и в ней все узоры библиотеки."""
    page = client.get("/").text
    assert 'id="generate"' in page
    assert "Удиви меня" in page
    for template in LIBRARY.values():
        assert template.title in page


def test_empty_seed_gives_a_pattern_and_names_it(client: TestClient, app) -> None:
    """Пустое поле — случайный узор, и сид возвращается на экран."""
    before = app.state.editor.program
    answer = client.post("/generate", data={"seed": "", "template": ""})

    assert answer.status_code == 200
    assert app.state.editor.program != before
    assert app.state.editor.seed is not None
    assert str(app.state.editor.seed) in SEED_FIELD.search(answer.text).group(1)


def test_the_same_seed_gives_the_same_board(client: TestClient, app) -> None:
    """Один сид — один узор. Это и есть смысл того, что сид показан."""
    client.post("/generate", data={"seed": "4242", "template": ""})
    first = app.state.editor.program
    client.post("/generate", data={"seed": "17", "template": ""})
    client.post("/generate", data={"seed": "4242", "template": ""})
    assert app.state.editor.program == first


def test_template_can_be_asked_for(client: TestClient, app) -> None:
    """Выбранный узор — тот, что выбрали, а не любой."""
    client.post("/generate", data={"seed": "5", "template": "herringbone"})
    generated = app.state.editor.generated
    assert generated is not None
    assert generated[0].template == "herringbone"


def test_scores_are_shown_and_include_economy(client: TestClient) -> None:
    """Оценки видны, и экономичность среди них: цена углов должна быть на виду."""
    answer = client.post("/generate", data={"seed": "9", "template": "chevron"}).text
    assert "экономичность" in answer
    assert "реализуемость" in answer


def test_scores_disappear_after_a_hand_edit(client: TestClient, app) -> None:
    """Правка руками уносит оценки: они посчитаны для другой доски.

    Оставить их на экране — соврать числом, которое выглядит измеренным.
    Проверка на устаревание живёт в `Editor.generated` и держится сравнением
    с текущей программой, поэтому гасить её вручную в каждой правке не нужно.
    """
    client.post("/generate", data={"seed": "3", "template": "checkerboard"})
    assert app.state.editor.generated is not None

    answer = client.post("/strips", data={"action": "add"})
    assert app.state.editor.generated is None
    assert "экономичность" not in answer.text


def test_junk_seed_is_reported_not_raised(client: TestClient, app) -> None:
    """Сид буквами — замечание в панели, а не пятисотка."""
    before = app.state.editor.program
    answer = client.post("/generate", data={"seed": "абв", "template": ""})
    assert answer.status_code == 200
    assert "не целое число" in answer.text
    assert app.state.editor.program == before


def test_unknown_template_is_reported(client: TestClient) -> None:
    """Узор, которого нет в библиотеке, — тоже замечание словами."""
    answer = client.post("/generate", data={"seed": "1", "template": "нет-такого"})
    assert answer.status_code == 200
    assert "нет такого узора" in answer.text


def test_workshop_panel_shows_the_numbers(client: TestClient) -> None:
    """Панель «Цех» на странице, и в ней главное — расход, вес и цена."""
    page = client.get("/").text
    assert 'id="workshop"' in page
    for label in ("Закупка", "В доску идёт", "Вес доски", "Себестоимость"):
        assert label in page


def test_printout_and_blueprint_are_served(client: TestClient) -> None:
    """Распечатка и чертёж отдаются отдельными документами — их печатают."""
    printout = client.get("/workshop")
    assert printout.status_code == 200
    assert "Обозначения пород" in printout.text

    drawing = client.get("/blueprint.svg")
    assert drawing.status_code == 200
    assert drawing.headers["content-type"].startswith("image/svg+xml")
    assert drawing.text.startswith("<?xml")


def test_printout_of_a_broken_program_explains_itself(client: TestClient, app) -> None:
    """Неисполнимая программа даёт разбор словами, а не пустую страницу.

    Обрезка, съедающая щит целиком, законна по последовательности операций
    и невозможна по числам — обычное состояние доски, которую сейчас крутят.
    """
    from boardforge.core.ops import Crop, target_of
    from boardforge.core.program import Program

    editor = app.state.editor
    last = target_of(editor.program.operations[-1])
    editor.program = Program(
        operations=(*editor.program.operations, Crop(last, left=10_000.0))
    )
    assert client.get("/workshop").status_code == 409
    assert client.get("/blueprint.svg").status_code == 409


def test_workshop_is_not_recomputed_for_the_same_program(app) -> None:
    """Расчёт цеха кэшируется по программе: у кубов он стоит полсекунды.

    Панель перерисовывается на каждую правку, и без кэша редактор встал бы
    именно на тех узорах, ради которых расчёт и нужен.
    """
    editor = app.state.editor
    first = editor.workshop
    assert first is not None
    assert editor.workshop is first

    editor.add_strip()
    assert editor.workshop is not first


def test_generated_board_is_manufacturable(client: TestClient, app) -> None:
    """Сгенерированное в браузере проходит валидатор — как и в CLI.

    Генератор отбраковывает негодные геномы сам, но проверить это надо со
    стороны веба: сюда узор приходит другой дорогой, чем в командной строке.
    """
    for seed in ("11", "12", "13"):
        client.post("/generate", data={"seed": seed, "template": ""})
        program = app.state.editor.program
        assert not program.errors
        assert program.run().board.area_mm2 > 0
