"""Операции DSL. Все размеры чистовые: припуски живут в calc/.

Итоговый набор описан в docs/decisions.md. Порядок осей во всей модели один:
детали укладываются поперёк по X, длина детали идёт по Y, третье измерение
(толщина щита или высота доски) в плоскость не попадает.

Состояние программы — именованный набор заготовок (Р9). Рез не заводит новое
имя, а переводит заготовку из состояния «щит» в состояние «пачка деталей»
под тем же именем; деталь адресуется парой (заготовка, номер).
"""

from dataclasses import dataclass
from typing import Any


def _check_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} должно быть положительным, получено {value}")


def _check_name(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} должно быть непустым именем заготовки")


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
class PieceRef:
    """Ссылка на деталь: имя заготовки и её номер в пачке после реза."""

    billet: str
    index: int

    def __post_init__(self) -> None:
        _check_name("имя заготовки", self.billet)
        if self.index < 0:
            raise ValueError("номер детали не может быть отрицательным")

    def __str__(self) -> str:
        return f"{self.billet}#{self.index}"


@dataclass(frozen=True, slots=True)
class Glue:
    """Склейка реек кромка-к-кромке. Заводит новую заготовку — щит.

    Толщина одна на весь щит: после склейки щит строгается в единый размер,
    разнотолщинность физически не выживает.
    """

    id: str
    strips: tuple[Strip, ...]
    length_mm: float
    thickness_mm: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "strips", tuple(self.strips))
        _check_name("имя щита", self.id)
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

    source: str
    step_mm: float

    def __post_init__(self) -> None:
        _check_name("источник торцовки", self.source)
        _check_positive("шаг торцовки", self.step_mm)

    @property
    def angle_deg(self) -> float:
        """Торцовка — частный случай реза под 90° к кромке."""
        return 90.0


@dataclass(frozen=True, slots=True)
class StandOnEnd:
    """Полосы заготовки ставятся на торец. Не более раза на заготовку.

    Меняет плоскость проекции: шаг торцовки уходит в высоту доски,
    толщина щита становится размером детали в плане.
    """

    source: str

    def __post_init__(self) -> None:
        _check_name("источник постановки на торец", self.source)


@dataclass(frozen=True, slots=True)
class Cut:
    """Рез в плане под углом к кромке щита. Только после StandOnEnd.

    Угол отсчитывается от кромки (оси Y): 90° — рез поперёк.
    """

    source: str
    angle_deg: float
    step_mm: float

    def __post_init__(self) -> None:
        _check_name("источник реза", self.source)
        if not 0 < self.angle_deg < 180:
            raise ValueError(
                f"угол реза должен быть в (0, 180), получен {self.angle_deg}"
            )
        _check_positive("шаг реза", self.step_mm)


@dataclass(frozen=True, slots=True)
class Assemble:
    """Склейка деталей в новую заготовку.

    Операция клеит: расходует клей, требует струбцин, за ней следуют строгание
    и обрезка. Перестановки без склейки не существует.

    `pieces` — какие детали и в каком порядке ставим поперёк по X; детали могут
    приходить из разных заготовок, ради этого и заведён мульти-щит.
    `reversed` — разворот детали на 180° в плане, меняет порядок ячеек в ряду.
    `offsets_mm` — продольный сдвиг детали вдоль Y.
    `flipped` — переворот на другую сторону: узор не меняет, меняет текстуру.
    """

    id: str
    pieces: tuple[PieceRef, ...]
    reversed: tuple[bool, ...]
    offsets_mm: tuple[float, ...]
    flipped: tuple[bool, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pieces", tuple(self.pieces))
        object.__setattr__(self, "reversed", tuple(bool(v) for v in self.reversed))
        object.__setattr__(self, "offsets_mm", tuple(float(v) for v in self.offsets_mm))
        if self.flipped is not None:
            object.__setattr__(self, "flipped", tuple(bool(v) for v in self.flipped))

        _check_name("имя щита", self.id)
        if not self.pieces:
            raise ValueError("нечего склеивать: не выбрано ни одной детали")
        if len(set(self.pieces)) != len(self.pieces):
            raise ValueError("одна деталь не может попасть в щит дважды")

        count = len(self.pieces)
        for name in ("reversed", "offsets_mm", "flipped"):
            value = getattr(self, name)
            if value is not None and len(value) != count:
                raise ValueError(
                    f"длина {name} ({len(value)}) не совпадает с числом деталей ({count})"
                )

    @property
    def sources(self) -> tuple[str, ...]:
        """Заготовки, из которых берутся детали, без повторов."""
        return tuple(dict.fromkeys(ref.billet for ref in self.pieces))


@dataclass(frozen=True, slots=True)
class Crop:
    """Дизайнерская обрезка в размер, возможно разрезающая ячейки.

    Технологическая обрезка кромок после каждой склейки — не операция,
    а параметр припусков в calc/.
    """

    source: str
    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0

    def __post_init__(self) -> None:
        _check_name("источник обрезки", self.source)
        for name in ("left", "right", "top", "bottom"):
            if getattr(self, name) < 0:
                raise ValueError(f"обрезка {name} не может быть отрицательной")


type Operation = Glue | Crosscut | StandOnEnd | Cut | Assemble | Crop

_OPERATIONS = {
    cls.__name__: cls for cls in (Glue, Crosscut, StandOnEnd, Cut, Assemble, Crop)
}


def target_of(op: Operation) -> str:
    """Имя заготовки, которой касается операция."""
    return op.id if isinstance(op, Glue | Assemble) else op.source


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
        elif slot == "pieces":
            value = [{"billet": p.billet, "index": p.index} for p in value]
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
    elif name == "Assemble":
        payload["pieces"] = tuple(
            PieceRef(billet=p["billet"], index=p["index"]) for p in payload["pieces"]
        )
    return _OPERATIONS[name](**payload)
