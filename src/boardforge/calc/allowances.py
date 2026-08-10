"""Технологические припуски. Значения — параметры, а не магические числа."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Allowances:
    """Что съедает материал сверх чистовых размеров.

    `planing_mm` — суммарно с обеих сторон за одну склейку.
    `end_trim_mm` — с каждого торца щита, поперёк волокон: там сколы и «нырок»
    строгального станка, меньше 10 мм не берут.
    `edge_trim_mm` — с каждой кромки, вдоль волокон: кромку только равняют,
    поэтому припуск на порядок меньше торцевого.
    """

    kerf_mm: float = 3.2
    planing_mm: float = 2.0
    end_trim_mm: float = 15.0
    edge_trim_mm: float = 2.0

    def __post_init__(self) -> None:
        for name in ("kerf_mm", "planing_mm", "end_trim_mm", "edge_trim_mm"):
            if getattr(self, name) < 0:
                raise ValueError(f"припуск {name} не может быть отрицательным")


CIRCULAR_SAW_KERF_MM = 3.2
THIN_KERF_MM = 2.2
BANDSAW_KERF_MM = 1.2
