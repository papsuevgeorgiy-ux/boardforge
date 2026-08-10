"""Породы древесины: модель и загрузка справочника."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_SPECIES_PATH = Path(__file__).with_name("species.yaml")

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class Species:
    """Порода древесины. Справочные значения при влажности ~12%."""

    key: str
    name: str
    density_kg_m3: float
    shrinkage_tangential: float
    shrinkage_radial: float
    color: str
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
        if not _COLOR_RE.match(self.color):
            raise ValueError(f"{self.key}: цвет должен быть в формате #rrggbb")


def _build(key: str, raw: dict[str, Any]) -> Species:
    shrinkage = raw.get("shrinkage") or {}
    try:
        return Species(
            key=key,
            name=raw["name"],
            density_kg_m3=float(raw["density"]),
            shrinkage_tangential=float(shrinkage["tangential"]),
            shrinkage_radial=float(shrinkage["radial"]),
            color=raw["color"],
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
