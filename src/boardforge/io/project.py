"""Файл проекта: программа операций в JSON, туда и обратно.

Переезд из `web/state.py`. Веб знал про диск, кодировку и разбор JSON — то
есть про файлы, — а `io/` про них не знал вовсе. Логика от переезда не менялась
ни на строчку, поменялось только место: чтение и запись проекта нужны и
командной строке, а тянуть их из веба она не имеет права.

Ядро по-прежнему отвечает только за `Program.to_dict()` / `from_dict()`:
что такое операция, знает оно, что такое файл — этот модуль.
"""

import json
from pathlib import Path

from ..core.program import Program


class ProjectError(ValueError):
    """Проект не читается или не пишется. Текст показывают человеку."""


def dumps(program: Program) -> str:
    """Программа в JSON проекта — читаемый, диффабельный, с переводом строки.

    `ensure_ascii=False` не косметика: без него породы и имена щитов уезжают
    в `\\uXXXX`, и файл перестаёт читаться глазами — а читаемость и есть
    причина, по которой проект хранится программой, а не снимком.
    """
    return json.dumps(program.to_dict(), ensure_ascii=False, indent=2) + "\n"


def loads(text: str) -> Program:
    """Программа из JSON проекта, с разбором того, что именно не так."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProjectError(f"это не JSON: {error}") from error
    try:
        return Program.from_dict(data)
    except (ValueError, KeyError, TypeError) as error:
        raise ProjectError(f"проект не читается: {error}") from error


def save(program: Program, path: Path) -> Path:
    """Сохранить проект по пути на диске, создав каталог при необходимости."""
    path = Path(path)
    if not path.name:
        raise ProjectError("не указано имя файла")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(program), encoding="utf-8")
    except OSError as error:
        # Самый частый случай — в поле пути указали каталог, а не файл.
        # Пользователю нужна строка, а не `PermissionError` из недр pathlib.
        raise ProjectError(f"файл не записывается: {error}") from error
    return path


def load(path: Path) -> Program:
    """Открыть проект с диска."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ProjectError(f"файл не открывается: {error}") from error
    return loads(text)


__all__ = ["ProjectError", "dumps", "load", "loads", "save"]
