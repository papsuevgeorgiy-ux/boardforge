"""Технологические припуски. Значения — параметры, а не магические числа."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Allowances:
    """Что съедает материал сверх чистовых размеров.

    `planing_mm` — суммарно с обеих сторон за одну склейку.
    `edge_trim_mm` — с каждой стороны по периметру за одну склейку.
    """

    kerf_mm: float = 3.2
    planing_mm: float = 2.0
    edge_trim_mm: float = 15.0

    def __post_init__(self) -> None:
        for name in ("kerf_mm", "planing_mm", "edge_trim_mm"):
            if getattr(self, name) < 0:
                raise ValueError(f"припуск {name} не может быть отрицательным")


CIRCULAR_SAW_KERF_MM = 3.2
THIN_KERF_MM = 2.2
BANDSAW_KERF_MM = 1.2
