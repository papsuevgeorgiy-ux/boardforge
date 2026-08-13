"""Состояние редактора: текущая программа и как её показывать.

Инструмент локальный и однопользовательский, поэтому проект живёт в памяти
процесса, а не в базе и не в сессии. Хранится **только программа** — узор,
габарит и раскрой из неё выводятся. Единицы и масштаб к проекту не относятся:
это способ смотреть, а не свойство доски, и в JSON они не попадают.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..core.ops import Glue, Strip
from ..core.program import Program
from ..core.species import Species, load_species
from ..core.units import Units, units_by_key


class EditError(ValueError):
    """Правку нельзя применить."""


@dataclass(slots=True)
class Editor:
    """Открытый проект и вид на него."""

    program: Program
    catalogue: dict[str, Species] = field(default_factory=load_species)
    units: Units = field(default_factory=lambda: units_by_key("mm"))
    scale: float = 1.6
    note: str = ""
    path: Path | None = None

    @property
    def glue(self) -> Glue:
        """Первая склейка — щит, состав которого правится в панели."""
        for op in self.program.operations:
            if isinstance(op, Glue):
                return op
        raise EditError("в программе нет ни одной склейки")

    def build_board(self) -> tuple[object | None, str]:
        """Доска и причина, если её нет.

        Валидатор проверяет последовательность операций, но не считает
        геометрию: обрезка, которая съедает щит целиком, проходит его насквозь
        и падает уже при исполнении. Такое нельзя ронять пятисоткой — это
        обычное состояние доски, которую сейчас крутят, и о нём надо сказать
        словами рядом с остальным разбором.
        """
        errors = self.program.errors
        if errors:
            return None, "; ".join(str(issue) for issue in errors)
        try:
            return self.program.apply(), ""
        except ValueError as error:
            return None, str(error)

    def set_units(self, key: str) -> None:
        """Переключить единицы показа."""
        self.units = units_by_key(key)

    def set_strips(self, species: list[str], widths: list[float]) -> None:
        """Переписать состав щита: породы и чистовые ширины реек."""
        if len(species) != len(widths):
            raise EditError("у рейки должна быть и порода, и ширина")
        if not species:
            raise EditError("щит не может остаться без реек")

        strips = []
        for index, (key, width) in enumerate(zip(species, widths, strict=True), start=1):
            if key not in self.catalogue:
                raise EditError(f"рейка {index}: породы {key} нет в справочнике")
            if width <= 0:
                raise EditError(f"рейка {index}: ширина должна быть положительной")
            strips.append(Strip(key, width))

        self._replace_glue(strips=tuple(strips))

    def add_strip(self) -> None:
        """Добавить рейку, повторив последнюю."""
        strips = self.glue.strips
        self._replace_glue(strips=(*strips, strips[-1]))

    def remove_strip(self, index: int) -> None:
        """Убрать рейку по номеру."""
        strips = self.glue.strips
        if len(strips) <= 1:
            raise EditError("в щите должна остаться хотя бы одна рейка")
        if not 0 <= index < len(strips):
            raise EditError(f"рейки {index + 1} в щите нет")
        self._replace_glue(strips=tuple(s for i, s in enumerate(strips) if i != index))

    def _replace_glue(self, **changes) -> None:
        from dataclasses import replace

        glue = self.glue
        updated = replace(glue, **changes)
        self.program = Program(
            operations=tuple(
                updated if op is glue else op for op in self.program.operations
            ),
            schema_version=self.program.schema_version,
        )

    def load_json(self, text: str) -> None:
        """Загрузить программу из JSON проекта."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise EditError(f"это не JSON: {error}") from error
        try:
            self.program = Program.from_dict(data)
        except (ValueError, KeyError, TypeError) as error:
            raise EditError(f"проект не читается: {error}") from error

    def dump_json(self) -> str:
        """Программа в JSON проекта — читаемый и диффабельный."""
        return json.dumps(self.program.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def save_to(self, path: Path) -> Path:
        """Сохранить проект по пути на диске."""
        path = Path(path)
        if not path.name:
            raise EditError("не указано имя файла")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dump_json(), encoding="utf-8")
        self.path = path
        return path

    def open_from(self, path: Path) -> Path:
        """Открыть проект с диска."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise EditError(f"файл не открывается: {error}") from error
        self.load_json(text)
        self.path = path
        return path
