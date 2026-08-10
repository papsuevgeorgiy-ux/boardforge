"""Операции DSL. Все размеры чистовые: припуски живут в calc/.

Итоговый набор описан в docs/decisions.md. Порядок осей во всей модели один:
детали укладываются поперёк по X, длина детали идёт по Y, третье измерение
(толщина щита или высота доски) в плоскость не попадает.
"""

from dataclasses import dataclass
from typing import Any


def _check_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} должно быть положительным, получено {value}")


@dataclass(frozen=True, slots=True)
class Strip:
    """Рейка в щите: порода и чистовая ширина."""

    species: str
    width_mm: float

    def __post_init__(self) -> None:
        if not self.species:
            raise ValueError("у рейки не указана порода")
        _check_positive("ширина рейки", self.width_mm)


@dataclass(frozen=True, slots=True)
class Glue:
    """Склейка реек кромка-к-кромке. Результат — щит.

    Толщина одна на весь щит: после склейки щит строгается в единый размер,
    разнотолщинность физически не выживает.
    """

    strips: tuple[Strip, ...]
    length_mm: float
    thickness_mm: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "strips", tuple(self.strips))
        if not self.strips:
            raise ValueError("щит не может быть пустым")
        _check_positive("длина щита", self.length_mm)
        _check_positive("толщина щита", self.thickness_mm)

    @property
    def width_mm(self) -> float:
        """Чистовая ширина щита."""
        return sum(strip.width_mm for strip in self.strips)


@dataclass(frozen=True, slots=True)
class Crosscut:
    """Торцовка: резы поперёк волокон, всегда 90°. Задаёт высоту доски."""

    step_mm: float

    def __post_init__(self) -> None:
        _check_positive("шаг торцовки", self.step_mm)

    @property
    def angle_deg(self) -> float:
        """Торцовка — частный случай реза под 90° к кромке."""
        return 90.0


@dataclass(frozen=True, slots=True)
class StandOnEnd:
    """Полосы ставятся на торец. Ровно один раз, сразу после торцовки.

    Меняет плоскость проекции: шаг торцовки уходит в высоту доски,
    толщина щита становится размером детали в плане.
    """


@dataclass(frozen=True, slots=True)
class Cut:
    """Рез в плане под углом к кромке щита. Только после StandOnEnd.

    Угол отсчитывается от кромки (оси Y): 90° — рез поперёк.
    """

    angle_deg: float
    step_mm: float

    def __post_init__(self) -> None:
        if not 0 < self.angle_deg < 180:
            raise ValueError(
                f"угол реза должен быть в (0, 180), получен {self.angle_deg}"
            )
        _check_positive("шаг реза", self.step_mm)


@dataclass(frozen=True, slots=True)
class Assemble:
    """Склейка деталей в новый щит.

    Операция клеит: расходует клей, требует струбцин, за ней следуют строгание
    и обрезка. Перестановки без склейки не существует.

    `order` — какие детали и в каком порядке ставим поперёк по X.
    `reversed` — разворот детали на 180° в плане, меняет порядок ячеек в ряду.
    `offsets_mm` — продольный сдвиг детали вдоль Y.
    `flipped` — переворот на другую сторону: узор не меняет, меняет текстуру.
    """

    order: tuple[int, ...]
    reversed: tuple[bool, ...]
    offsets_mm: tuple[float, ...]
    flipped: tuple[bool, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "order", tuple(int(v) for v in self.order))
        object.__setattr__(self, "reversed", tuple(bool(v) for v in self.reversed))
        object.__setattr__(self, "offsets_mm", tuple(float(v) for v in self.offsets_mm))
        if self.flipped is not None:
            object.__setattr__(self, "flipped", tuple(bool(v) for v in self.flipped))

        if not self.order:
            raise ValueError("нечего склеивать: пустой порядок деталей")
        if len(set(self.order)) != len(self.order):
            raise ValueError("одна деталь не может попасть в щит дважды")
        if any(index < 0 for index in self.order):
            raise ValueError("индексы деталей не могут быть отрицательными")

        count = len(self.order)
        for name in ("reversed", "offsets_mm", "flipped"):
            value = getattr(self, name)
            if value is not None and len(value) != count:
                raise ValueError(
                    f"длина {name} ({len(value)}) не совпадает с числом деталей ({count})"
                )


@dataclass(frozen=True, slots=True)
class Crop:
    """Дизайнерская обрезка в размер, возможно разрезающая ячейки.

    Технологическая обрезка кромок после каждой склейки — не операция,
    а параметр припусков в calc/.
    """

    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0

    def __post_init__(self) -> None:
        for name in ("left", "right", "top", "bottom"):
            if getattr(self, name) < 0:
                raise ValueError(f"обрезка {name} не может быть отрицательной")


type Operation = Glue | Crosscut | StandOnEnd | Cut | Assemble | Crop

_OPERATIONS = {
    cls.__name__: cls for cls in (Glue, Crosscut, StandOnEnd, Cut, Assemble, Crop)
}


def op_to_dict(op: Operation) -> dict[str, Any]:
    """Операция в словарь для JSON. Ключ `op` — имя класса."""
    name = type(op).__name__
    if name not in _OPERATIONS:
        raise TypeError(f"неизвестная операция: {name}")
    data: dict[str, Any] = {"op": name}
    for slot in type(op).__slots__:
        value = getattr(op, slot)
        if slot == "strips":
            value = [{"species": s.species, "width_mm": s.width_mm} for s in value]
        elif isinstance(value, tuple):
            value = list(value)
        data[slot] = value
    return data


def op_from_dict(data: dict[str, Any]) -> Operation:
    """Операция из словаря."""
    payload = dict(data)
    name = payload.pop("op", None)
    if name not in _OPERATIONS:
        raise ValueError(f"неизвестная операция: {name!r}")
    if name == "Glue":
        payload["strips"] = tuple(
            Strip(species=s["species"], width_mm=s["width_mm"]) for s in payload["strips"]
        )
    return _OPERATIONS[name](**payload)
