"""Веб-оболочка: страница, фрагменты, правки, проект.

Обмен фрагментами — не деталь реализации, а требование: перерисовка страницы
целиком стирала бы позицию прокрутки и фокус на каждом движении ползунка.
Поэтому здесь всюду проверяется, что ответ на правку — фрагмент, а не документ.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from boardforge.core.ops import Crosscut, Glue, Strip
from boardforge.core.program import Program
from boardforge.web import TEMPLATES, TEXTURE_DELAY_MS, create_app
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


def test_page_has_every_panel(client: TestClient) -> None:
    """Страница собирается целиком: превью, параметры, программа, разбор."""
    page = client.get("/")
    assert page.status_code == 200
    for anchor in ('id="board"', 'id="strips"', 'id="size"', 'id="issues"'):
        assert anchor in page.text
    assert 'id="program"' in page.text
    assert 'id="project"' in page.text


def test_page_serves_htmx_locally(client: TestClient) -> None:
    """HTMX лежит рядом, а не на чужом CDN: инструмент работает без сети."""
    assert "/static/htmx.min.js" in client.get("/").text
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_structure_comes_first(client: TestClient) -> None:
    """Первым приходит быстрый слой, и он сам просит текстуру через паузу."""
    fragment = client.get("/fragment/board").text
    assert "clipPath" not in fragment
    assert "<svg" in fragment
    assert f"delay:{TEXTURE_DELAY_MS}ms" in fragment
    assert "/fragment/board?full=1" in fragment


def test_texture_arrives_second_and_stops(client: TestClient) -> None:
    """Полный слой приходит по второму запросу и больше ничего не просит."""
    fragment = client.get("/fragment/board?full=1").text
    assert "clipPath" in fragment
    assert "hx-get" not in fragment


def test_fragments_are_not_pages(client: TestClient) -> None:
    """Фрагмент — это кусок разметки, а не документ."""
    for response in (
        client.get("/fragment/board"),
        client.post("/strips", data={"action": "add"}),
        client.post("/units", data={"units": "inch"}),
    ):
        assert "<html" not in response.text
        assert "<!DOCTYPE" not in response.text


def test_edit_returns_only_the_touched_panels(client: TestClient) -> None:
    """Правка возвращает превью и панели вне очереди, а не всю страницу.

    Панелей столько же, сколько в `_refresh.html`, минус превью: оно идёт
    в цель, а не вне очереди. Число выводится из шаблона, а не вписано:
    вписанное пришлось бы править при каждой новой панели, и однажды его
    поправили бы не глядя — а тест сторожит не количество, а то, что ответ
    остаётся набором фрагментов.
    """
    refresh = (TEMPLATES / "_refresh.html").read_text(encoding="utf-8")
    panels = len(re.findall(r'{% include "(_\w+)\.html" %}', refresh)) - 1

    response = client.post("/strips", data={"action": "add"})
    assert response.status_code == 200
    assert response.text.count('hx-swap-oob="true"') == panels
    assert 'id="board"' in response.text


def test_strips_can_be_added_and_removed(client: TestClient, editor) -> None:
    """Состав щита правится: рейку можно добавить и убрать."""
    before = len(editor.glue.strips)
    client.post("/strips", data={"action": "add"})
    assert len(editor.glue.strips) == before + 1
    client.post("/strips", data={"action": "remove:0"})
    assert len(editor.glue.strips) == before


def test_strips_rewrite_species_and_widths(client: TestClient, editor) -> None:
    """Породы и ширины реек переписываются целиком."""
    client.post(
        "/strips",
        data={"species": ["oak", "ash"], "width": ["30", "25"], "action": "apply"},
    )
    assert [(s.species, s.width_mm) for s in editor.glue.strips] == [
        ("oak", 30.0),
        ("ash", 25.0),
    ]


def test_unknown_species_is_refused_with_a_note(client: TestClient, editor) -> None:
    """Порода не из справочника отклоняется, и об этом говорят словами."""
    response = client.post(
        "/strips", data={"species": ["ёлка"], "width": ["30"], "action": "apply"}
    )
    assert "справочнике" in editor.note
    assert editor.glue.strips[0].species != "ёлка"
    assert "справочнике" in response.text


def test_last_strip_cannot_be_removed(client: TestClient, editor) -> None:
    """Щит без реек не бывает — последнюю не отдаём."""
    while len(editor.glue.strips) > 1:
        client.post("/strips", data={"action": "remove:0"})
    client.post("/strips", data={"action": "remove:0"})
    assert len(editor.glue.strips) == 1
    assert "хотя бы одна рейка" in editor.note


def test_size_rewrites_the_program(client: TestClient, editor) -> None:
    """Габарит вводится, программа переписывается, размер нигде не хранится."""
    client.post("/size", data={"width": "400", "length": "300", "height": "40"})
    board, _ = editor.build_board()
    assert board.thickness_mm == pytest.approx(40.0)
    assert abs(board.width_mm - 400.0) <= 40.0
    assert editor.program.errors == []

    stored = json.dumps(editor.program.to_dict(), ensure_ascii=False)
    for word in ("target", "desired", "целев"):
        assert word not in stored


def test_size_reports_the_deviation(client: TestClient, editor) -> None:
    """Недостижимый размер не подгоняется молча: показывается отклонение."""
    client.post("/size", data={"width": "417", "length": "313", "height": "37"})
    assert "Ближайший достижимый габарит" in editor.note
    assert editor.build_board()[0].thickness_mm == pytest.approx(37.0)


def test_size_reports_an_exact_hit(client: TestClient, editor) -> None:
    """Точное попадание тоже называется вслух."""
    client.post("/size", data={"width": "400", "length": "240", "height": "40"})
    assert "точно" in editor.note.lower()


def test_size_refuses_nonsense(client: TestClient, editor) -> None:
    """Не-число и отрицательный размер — понятная ошибка, а не пятисотка."""
    response = client.post(
        "/size", data={"width": "много", "length": "300", "height": "40"}
    )
    assert response.status_code == 200
    assert "не число" in editor.note

    client.post("/size", data={"width": "-5", "length": "300", "height": "40"})
    assert "положительной" in editor.note


def test_units_switch_the_display_only(client: TestClient, editor) -> None:
    """Дюймы меняют показ, но не программу."""
    before = editor.program.to_dict()
    response = client.post("/units", data={"units": "inch"})
    assert editor.units.key == "inch"
    assert editor.program.to_dict() == before
    assert '"' in response.text

    client.post("/units", data={"units": "mm"})
    assert editor.units.key == "mm"


def test_validator_is_visible_with_operation_numbers() -> None:
    """Разбор валидатора показывается словами и с привязкой к операции.

    Это главная функция инструмента: неизготовимую доску пользователь должен
    видеть сразу и понимать, какая именно операция виновата.
    """
    broken = Program(
        operations=(
            Glue(
                id="A",
                strips=(Strip("maple_hard", 40.0),),
                length_mm=200.0,
                thickness_mm=40.0,
            ),
            Crosscut(source="A", step_mm=40.0),
        )
    )
    client = TestClient(create_app(broken))
    page = client.get("/").text
    assert "Операция 2" in page or "Программа целиком" in page
    assert "россыпью деталей" in page
    assert "неизготовима" in page.lower()


def test_broken_program_still_renders_the_page() -> None:
    """Неисполнимая программа не роняет страницу: превью пустое, разбор есть."""
    broken = Program(
        operations=(
            Glue(
                id="A",
                strips=(Strip("maple_hard", 40.0),),
                length_mm=200.0,
                thickness_mm=40.0,
            ),
            Crosscut(source="A", step_mm=40.0),
        )
    )
    page = TestClient(create_app(broken)).get("/")
    assert page.status_code == 200
    assert "Доска не собирается" in page.text


def test_geometry_failure_is_shown_not_thrown(client: TestClient, editor) -> None:
    """Программа, законная по операциям, но невозможная по числам, не роняет UI.

    Валидатор читает последовательность операций и не считает геометрию:
    обрезка, съедающая щит целиком, проходит его насквозь и падает уже при
    исполнении. Для пользователя, который сейчас крутит параметры, это обычное
    промежуточное состояние, а не пятисотка.
    """
    while len(editor.glue.strips) > 1:
        client.post("/strips", data={"action": "remove:0"})

    response = client.post(
        "/strips", data={"species": ["maple_hard"], "width": ["20"], "action": "apply"}
    )
    assert response.status_code == 200

    board, failure = editor.build_board()
    assert board is None
    assert failure
    assert "Программа не исполняется" in response.text
    assert "Доска не собирается" in response.text


def test_project_round_trip_through_disk(client: TestClient, editor, tmp_path) -> None:
    """Сохранение и загрузка проекта: в файле программа, а не картинка."""
    path = tmp_path / "board.json"
    client.post("/strips", data={"species": ["oak"], "width": ["55"], "action": "apply"})
    client.post("/project/save", data={"path": str(path)})
    assert "сохранён" in editor.note

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == editor.program.schema_version
    assert saved["operations"][0]["op"] == "Glue"

    client.post("/strips", data={"species": ["ash"], "width": ["20"], "action": "apply"})
    assert editor.glue.strips[0].species == "ash"

    client.post("/project/open", data={"path": str(path)})
    assert "открыт" in editor.note
    assert [(s.species, s.width_mm) for s in editor.glue.strips] == [("oak", 55.0)]


def test_opening_a_missing_file_is_reported(client: TestClient, editor, tmp_path) -> None:
    """Отсутствующий файл — сообщение, а не падение."""
    response = client.post("/project/open", data={"path": str(tmp_path / "нет.json")})
    assert response.status_code == 200
    assert "не открыто" in editor.note


def test_opening_junk_is_reported(client: TestClient, editor, tmp_path) -> None:
    """Мусор вместо проекта тоже."""
    path = tmp_path / "junk.json"
    path.write_text("это не json", encoding="utf-8")
    client.post("/project/open", data={"path": str(path)})
    assert "не открыто" in editor.note


def test_project_downloads_as_json(client: TestClient) -> None:
    """Проект можно скачать файлом."""
    response = client.get("/project.json")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert json.loads(response.text)["operations"]


def test_species_cycle_warning_reaches_the_page(tmp_path) -> None:
    """Нехватку породных циклов человек видит в списке замечаний, а не в дыре.

    Сквозная проверка требования Дня 3: замечание должно доезжать до страницы
    с номером операции, до того как кто-то станет разглядывать превью.
    """
    from boardforge.core.patterns import StripedPanel, chevron

    panel = StripedPanel(
        species=("maple_hard", "walnut_black", "cherry"),
        columns=10,
        repeats=1,
    )
    client = TestClient(create_app(chevron(panel)))

    page = client.get("/").text
    assert "породным циклом" in page
    assert "предупреждение" in page
    assert "Операция 1 — Glue" in page
