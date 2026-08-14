"""Веб-оболочка: FastAPI + Jinja2 + HTMX. Вся логика на Python.

Обмен идёт фрагментами разметки, а не перерисовкой страницы: правка состава
щита возвращает превью, список операций, разбор валидатора и панель размеров —
и ничего больше.

Превью приходит в два приёма. Сначала структура: полигоны, швы, кромка —
десятки миллисекунд, узор виден сразу. Через `TEXTURE_DELAY_MS` после того, как
структура встала, браузер сам просит текстуру. Пока пользователь крутит
параметры, структура успевает перерисоваться, а запрос текстуры не доживает
до отправки — его элемент к тому времени уже заменён.
"""

from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..core.fitting import FitError, fit_dimensions
from ..core.program import Program
from ..render.style import RenderOptions
from ..render.svg import render_board, render_structure
from . import presenters
from .state import EditError, Editor

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"

TEXTURE_DELAY_MS = 200
"""Пауза перед запросом текстуры. Отсчитывается от появления структуры, поэтому
частые правки её всё время сбрасывают — текстура догоняет, когда крутить
перестали."""

DEFAULT_PROJECT_PATH = "out/project.json"


def _default_program() -> Program:
    """Чем открывается пустой редактор — шахматкой из библиотеки узоров.

    Из `core/library.py`, а не из `cli/`: веб не имеет права зависеть
    от командной строки, и до Дня 4 эта зависимость была временной подпоркой.
    """
    from ..core.library import build

    return build("checkerboard").program


def create_app(program: Program | None = None) -> FastAPI:
    """Собрать приложение вокруг одного открытого проекта."""
    app = FastAPI(title="BoardForge", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES))
    editor = Editor(program=program or _default_program())
    app.state.editor = editor
    app.state.templates = templates

    def context(request: Request, full: bool = False, **extra) -> dict:
        board, failure = editor.build_board()
        issues = presenters.issue_views(editor.program, failure)
        return {
            "request": request,
            "editor": editor,
            "full": full,
            "oob": False,
            "svg": render_preview(board, editor, full),
            "failure": failure,
            "units": editor.units,
            "catalogue": editor.catalogue,
            "strips": list(editor.glue.strips),
            "operations": presenters.operation_views(
                editor.program, editor.catalogue, editor.units
            ),
            "issues": issues,
            "verdict": presenters.verdict(issues),
            "board": board,
            "size": _size_view(board, editor),
            "note": editor.note,
            "texture_delay_ms": TEXTURE_DELAY_MS,
            "default_path": str(editor.path or DEFAULT_PROJECT_PATH),
            **extra,
        }

    def refresh(request: Request) -> HTMLResponse:
        """Ответ на правку: превью в цель, остальные панели — вне очереди."""
        return templates.TemplateResponse(
            request, "_refresh.html", context(request, oob=True)
        )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Response:
        return templates.TemplateResponse(request, "page.html", context(request))

    @app.get("/fragment/board", response_class=HTMLResponse)
    def fragment_board(request: Request, full: int = 0) -> Response:
        return templates.TemplateResponse(
            request, "_board.html", context(request, full=bool(full))
        )

    @app.post("/strips", response_class=HTMLResponse)
    async def edit_strips(request: Request) -> Response:
        form = await read_form(request)
        action = form.get("action", "apply")
        editor.note = ""
        try:
            if action == "add":
                editor.add_strip()
            elif action.startswith("remove:"):
                editor.remove_strip(int(action.split(":", 1)[1]))
            else:
                editor.set_strips(
                    form.all("species"),
                    [_number(value, "ширина рейки") for value in form.all("width")],
                )
        except (EditError, ValueError) as error:
            editor.note = str(error)
        return refresh(request)

    @app.post("/size", response_class=HTMLResponse)
    async def edit_size(request: Request) -> Response:
        form = await read_form(request)
        editor.note = ""
        try:
            fit = fit_dimensions(
                editor.program,
                _number(form.get("width"), "ширина"),
                _number(form.get("length"), "длина"),
                _number(form.get("height"), "высота"),
            )
        except (FitError, ValueError) as error:
            editor.note = str(error)
        else:
            editor.program = fit.program
            editor.note = _fit_note(fit, editor)
        return refresh(request)

    @app.post("/units", response_class=HTMLResponse)
    async def switch_units(request: Request) -> Response:
        form = await read_form(request)
        editor.set_units(form.get("units", "mm"))
        return refresh(request)

    @app.post("/project/save", response_class=HTMLResponse)
    async def save_project(request: Request) -> Response:
        form = await read_form(request)
        try:
            saved = editor.save_to(Path(form.get("path") or DEFAULT_PROJECT_PATH))
        except (EditError, OSError) as error:
            editor.note = f"не сохранено: {error}"
        else:
            editor.note = f"проект сохранён: {saved}"
        return refresh(request)

    @app.post("/project/open", response_class=HTMLResponse)
    async def open_project(request: Request) -> Response:
        form = await read_form(request)
        try:
            opened = editor.open_from(Path(form.get("path") or DEFAULT_PROJECT_PATH))
        except (EditError, OSError) as error:
            editor.note = f"не открыто: {error}"
        else:
            editor.note = f"проект открыт: {opened}"
        return refresh(request)

    @app.get("/project.json")
    def download_project() -> Response:
        return PlainTextResponse(
            editor.dump_json(),
            media_type="application/json",
            headers={"content-disposition": 'attachment; filename="project.json"'},
        )

    return app


class Form(dict):
    """Разобранная форма: ключ может повторяться, поэтому значения — списки."""

    def get(self, key: str, default: str = "") -> str:
        """Первое значение поля."""
        values = super().get(key)
        return values[0] if values else default

    def all(self, key: str) -> list[str]:
        """Все значения поля — так приходят рейки."""
        return list(super().get(key, ()))


async def read_form(request: Request) -> Form:
    """Разбор urlencoded формы средствами стандартной библиотеки.

    `request.form()` из Starlette тянет `python-multipart` даже там, где
    никаких файлов нет. Файлы здесь и не нужны: проект берётся по пути на диске,
    а не заливается, — и ради одного разбора `application/x-www-form-urlencoded`
    зависимость не нужна тоже.
    """
    body = (await request.body()).decode("utf-8")
    fields: dict[str, list[str]] = {}
    for key, value in parse_qsl(body, keep_blank_values=True):
        fields.setdefault(key, []).append(value)
    return Form(fields)


def _number(value: object, name: str) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{name}: «{value}» — не число") from None


def _size_view(board, editor: Editor) -> dict | None:
    if board is None:
        return None
    return {
        "width": editor.units.format(board.width_mm),
        "length": editor.units.format(board.length_mm),
        "height": editor.units.format(board.thickness_mm),
        "cells": len(board.pieces),
    }


def _fit_note(fit, editor: Editor) -> str:
    if fit.exact:
        return "Габарит достигнут точно."
    width, length, height = (editor.units.format_signed(v) for v in fit.deviation)
    return (
        f"Ближайший достижимый габарит: ширина {width}, длина {length}, "
        f"высота {height}. Точнее не выходит без обрезки или другой ширины реек."
    )


def render_preview(board, editor: Editor, full: bool) -> str:
    """SVG превью: структура или полный документ."""
    if board is None:
        return ""
    options = RenderOptions(scale=editor.scale)
    draw = render_board if full else render_structure
    return draw(board, editor.catalogue, options)


app = create_app()
