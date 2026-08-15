"""Откат и возврат: правку доски можно отменить, не открывая файл заново.

История хранит программы целиком, и главное требование к ней — чтобы **все**
правки шли через одну дверь. Правка, прошедшая мимо `set_program`, откатилась
бы не туда, и заметно это стало бы не сразу. Поэтому здесь перечислены все
способы поменять доску, какие есть в интерфейсе, и каждый обязан откатываться.
"""

import pytest
from fastapi.testclient import TestClient

from boardforge.web import create_app
from boardforge.web.state import HISTORY_DEPTH, EditError, Editor
from tests.helpers import build_checkerboard


@pytest.fixture
def app():
    return create_app(build_checkerboard())


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def editor(app):
    return app.state.editor


def test_nothing_to_undo_at_the_start(editor: Editor) -> None:
    """Только что открытый проект откатывать некуда."""
    assert not editor.can_undo
    assert not editor.can_redo
    with pytest.raises(EditError, match="откатывать нечего"):
        editor.undo()


def test_edit_undo_redo_returns_the_same_program(client: TestClient, editor) -> None:
    """Правка — откат — возврат приводит ровно к той же программе."""
    before = editor.program
    client.post("/strips", data={"action": "add"})
    edited = editor.program
    assert edited != before

    client.post("/history", data={"action": "undo"})
    assert editor.program == before
    client.post("/history", data={"action": "redo"})
    assert editor.program == edited


def test_a_new_edit_cuts_the_redo_tail(client: TestClient, editor) -> None:
    """Правка после отката обрубает откаченное: другой ветки не бывает."""
    client.post("/strips", data={"action": "add"})
    client.post("/history", data={"action": "undo"})
    assert editor.can_redo

    client.post("/strips", data={"action": "add"})
    assert not editor.can_redo


@pytest.mark.parametrize(
    ("url", "payload"),
    [
        ("/strips", {"action": "add"}),
        ("/generate", {"seed": "4242", "template": "chevron"}),
        ("/size", {"width": "300", "length": "200", "height": "40"}),
    ],
)
def test_every_way_of_changing_the_board_is_undoable(
    client: TestClient, editor, url, payload
) -> None:
    """Каждая ручка интерфейса, меняющая доску, откатывается.

    Список не для полноты ради полноты: подбор габарита переписывает сразу
    несколько операций, а «удиви меня» — всю программу, и мимо истории они
    прошли бы легче всего.
    """
    before = editor.program
    client.post(url, data=payload)
    assert editor.program != before, "правка не изменила программу — тест бесполезен"

    client.post("/history", data={"action": "undo"})
    assert editor.program == before


def test_opening_a_project_is_undoable(client: TestClient, editor, tmp_path) -> None:
    """Открытие чужого файла — тоже правка: случайно открытое возвращается."""
    from boardforge.core.library import build
    from boardforge.io.project import save

    path = save(build("chevron").program, tmp_path / "board.json")
    before = editor.program
    client.post("/project/open", data={"path": str(path)})
    assert editor.program != before

    client.post("/history", data={"action": "undo"})
    assert editor.program == before


def test_scores_come_back_with_the_generated_board(client: TestClient) -> None:
    """Откат к сгенерированному узору возвращает и его оценки.

    Само по себе: оценки привязаны к программе, а не к флагу, поэтому история
    их не хранит и хранить не должна.
    """
    client.post("/generate", data={"seed": "4242", "template": "chevron"})
    client.post("/strips", data={"action": "add"})
    assert "экономичность" not in client.get("/").text

    assert "экономичность" in client.post("/history", data={"action": "undo"}).text


def test_saving_does_not_touch_history(client: TestClient, editor, tmp_path) -> None:
    """Сохранение — не правка доски: история от него не растёт."""
    client.post("/strips", data={"action": "add"})
    depth = len(editor.past)
    client.post("/project/save", data={"path": str(tmp_path / "b.json")})
    client.post("/units", data={"units": "inch"})
    assert len(editor.past) == depth


def test_history_is_bounded(editor: Editor) -> None:
    """История не растёт бесконечно: помним фиксированное число шагов."""
    for _ in range(HISTORY_DEPTH + 20):
        editor.add_strip()
    assert len(editor.past) == HISTORY_DEPTH


def test_buttons_are_dead_when_there_is_nothing_to_do(client: TestClient) -> None:
    """Кнопки выключены, пока откатывать нечего — вместе с горячей клавишей."""
    page = client.get("/").text
    assert page.count("disabled") >= 2

    after = client.post("/strips", data={"action": "add"}).text
    assert "Ctrl+Z" in after


def test_extra_undo_is_not_an_error(client: TestClient) -> None:
    """Лишнее нажатие Ctrl+Z — не пятисотка, а строчка в примечании.

    Горячая клавиша срабатывает и на пустой истории; ронять на этом ответ
    было бы дичью.
    """
    response = client.post("/history", data={"action": "undo"})
    assert response.status_code == 200
    assert "откатывать нечего" in response.text
