"""Породы древесины: модель, палитра торца и загрузка справочника."""

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SPECIES_PATH = Path(__file__).with_name("species.yaml")

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

_EARLYWOOD_LIFT = 0.10
_LATEWOOD_DROP = 0.22
_RAY_LIFT = 0.22


def _channels(color: str) -> tuple[int, int, int]:
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def _mix(color: str, target: int, amount: float) -> str:
    """Подмешать к цвету белый или чёрный. Нужен только заготовкам палитры."""
    return "#" + "".join(
        f"{round(value + (target - value) * amount):02x}" for value in _channels(color)
    )


@dataclass(frozen=True, slots=True)
class Palette:
    """Цвета торцевого среза породы и выраженность его рисунка.

    Кольцо — пара слоёв: рыхлая ранняя древесина и плотная поздняя, которая
    всегда темнее. `base` — усреднённый тон, им заливается ячейка там, где
    текстуру не рисуют. Контрасты — непрозрачность штрихов в рендере, 0 гасит
    рисунок совсем.

    Ширина и доля — разные вещи, и обе нужны. `ring_width_mm` — период кольца,
    `latewood_fraction` — какую его часть занимает тёмная зона: у венге узкая
    и очень тёмная прослойка, у клёна широкая и почти неразличимая граница.
    Так же и с лучами: `ray_contrast` говорит, насколько они видны,
    `ray_width_mm` — насколько они толстые; у дуба лучи широкие, у бука узкие.
    """

    base: str
    earlywood: str
    latewood: str
    ray: str
    ring_contrast: float
    ray_contrast: float
    ring_width_mm: float
    latewood_fraction: float = 0.33
    ray_width_mm: float = 0.2
    verified: bool = False
    """Сверялись ли цвета с фотографиями торца. Пока нигде не сверялись."""

    def __post_init__(self) -> None:
        for field_name in ("base", "earlywood", "latewood", "ray"):
            value = getattr(self, field_name)
            if not _COLOR_RE.match(value):
                raise ValueError(f"цвет {field_name} должен быть в формате #rrggbb")
        for field_name in ("ring_contrast", "ray_contrast"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"выраженность {field_name} должна быть в 0–1")
        if not 0.0 < self.latewood_fraction < 1.0:
            raise ValueError("доля поздней древесины должна быть в (0, 1)")
        if self.ring_width_mm <= 0:
            raise ValueError("ширина годичного кольца должна быть положительной")
        if self.ray_width_mm <= 0:
            raise ValueError("ширина сердцевинного луча должна быть положительной")

    @property
    def colors(self) -> tuple[str, ...]:
        """Все цвета палитры — рендер не имеет права взять никакой другой."""
        return (self.base, self.earlywood, self.latewood, self.ray)

    @classmethod
    def from_base(cls, color: str, ring_width_mm: float = 2.5) -> "Palette":
        """Заготовка палитры из одного тона — для чужих справочников.

        Ранняя древесина светлее основного тона, поздняя темнее, лучи светлее
        всего. Числа взяты наугад: своя порода без палитры выглядит блёкло,
        и это честно.
        """
        if not _COLOR_RE.match(color):
            raise ValueError(f"цвет base должен быть в формате #rrggbb, получен {color}")
        return cls(
            base=color,
            earlywood=_mix(color, 0xFF, _EARLYWOOD_LIFT),
            latewood=_mix(color, 0x00, _LATEWOOD_DROP),
            ray=_mix(color, 0xFF, _RAY_LIFT),
            ring_contrast=0.30,
            ray_contrast=0.15,
            ring_width_mm=ring_width_mm,
        )

    @property
    def latewood_width_mm(self) -> float:
        """Ширина тёмной зоны кольца."""
        return self.ring_width_mm * self.latewood_fraction


@dataclass(frozen=True, slots=True)
class Species:
    """Порода древесины. Справочные значения при влажности ~12%."""

    key: str
    name: str
    density_kg_m3: float
    shrinkage_tangential: float
    shrinkage_radial: float
    palette: Palette
    open_pores: bool = False
    allergen: bool = False
    fades: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if self.density_kg_m3 <= 0:
            raise ValueError(f"{self.key}: плотность должна быть положительной")
        for field_name in ("shrinkage_tangential", "shrinkage_radial"):
            value = getattr(self, field_name)
            if not 0 <= value <= 30:
                raise ValueError(f"{self.key}: усушка {value} вне диапазона 0–30%")

    @property
    def color(self) -> str:
        """Основной тон породы. Источник истины — палитра."""
        return self.palette.base


def _palette(key: str, raw: dict[str, Any]) -> Palette:
    if "palette" in raw:
        data = dict(raw["palette"])
        base = data.pop("base", None)
        if base is None:
            raise ValueError(f"{key}: в палитре нет основного тона")
        defaults = Palette.from_base(base)
        try:
            return replace(defaults, **data)
        except TypeError as exc:
            raise ValueError(f"{key}: в палитре лишнее поле — {exc}") from exc
    if "color" in raw:
        return Palette.from_base(raw["color"])
    raise ValueError(f"{key}: у породы нет ни палитры, ни цвета")


def _build(key: str, raw: dict[str, Any]) -> Species:
    shrinkage = raw.get("shrinkage") or {}
    try:
        palette = _palette(key, raw)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return Species(
            key=key,
            name=raw["name"],
            density_kg_m3=float(raw["density"]),
            shrinkage_tangential=float(shrinkage["tangential"]),
            shrinkage_radial=float(shrinkage["radial"]),
            palette=palette,
            open_pores=bool(raw.get("open_pores", False)),
            allergen=bool(raw.get("allergen", False)),
            fades=bool(raw.get("fades", False)),
            note=raw.get("note", ""),
        )
    except KeyError as exc:
        raise ValueError(f"{key}: в описании породы нет поля {exc}") from exc


def load_species(path: Path | None = None) -> dict[str, Species]:
    """Загрузить справочник пород из YAML."""
    source = path or DEFAULT_SPECIES_PATH
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: ожидался словарь пород")
    return {key: _build(key, value) for key, value in raw.items()}
