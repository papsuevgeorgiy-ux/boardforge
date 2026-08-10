"""Миграции схемы проекта.

Проект хранится как программа операций, и её форма со временем меняется.
Каждая миграция поднимает словарь на одну версию; читатель всегда работает
с текущей формой и ничего не знает о прошлых.
"""

from string import ascii_uppercase
from typing import Any

SCHEMA_VERSION = 2


def _billet_name(index: int) -> str:
    """Имена заготовок для программ, где их не было: A, B, ... Z, AA, AB."""
    letters = ascii_uppercase
    name = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, len(letters))
        name = letters[remainder] + name
    return name


def _v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Одна линия заготовки превращается в именованный набор (Р9).

    В версии 1 состояние было единственным, поэтому имя восстанавливается
    однозначно: щит A, каждая склейка заводит следующую букву.
    """
    operations: list[dict[str, Any]] = []
    current = _billet_name(0)
    produced = 1

    for raw in data["operations"]:
        op = dict(raw)
        name = op["op"]
        if name == "Glue":
            op["id"] = current
        elif name == "Assemble":
            order = op.pop("order")
            op["pieces"] = [{"billet": current, "index": i} for i in order]
            current = _billet_name(produced)
            produced += 1
            op["id"] = current
        else:
            op["source"] = current
        operations.append(op)

    return {"schema_version": 2, "operations": operations}


_MIGRATIONS = {1: _v1_to_v2}


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Поднять проект до текущей версии схемы."""
    version = data.get("schema_version", SCHEMA_VERSION)
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"проект версии {version} новее, чем понимает эта сборка ({SCHEMA_VERSION})"
        )
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"нет миграции с версии {version}")
        data = step(data)
        version = data["schema_version"]
    return data
