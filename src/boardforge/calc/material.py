"""Обратный ход: от чистовых размеров программы к сырью и потерям.

Программа не знает о пропиле и строгании (см. docs/decisions.md, Р0.1).
Здесь мы идём назад: сколько дерева надо купить, чтобы после всех потерь
получить объявленные чистовые размеры.
"""

from dataclasses import dataclass

from ..core.ops import Assemble, Crosscut, Glue
from ..core.program import Program
from .allowances import Allowances


@dataclass(frozen=True, slots=True)
class StockPiece:
    """Позиция закупки: рейка в сыром размере, до строгания и обрезки."""

    species: str
    width_mm: float
    thickness_mm: float
    length_mm: float

    @property
    def volume_mm3(self) -> float:
        """Объём заготовки."""
        return self.width_mm * self.thickness_mm * self.length_mm


@dataclass(frozen=True, slots=True)
class Losses:
    """Куда девается разница между закупкой и доской."""

    kerf_mm3: float
    planing_mm3: float
    edge_trim_mm3: float
    offcut_mm3: float

    @property
    def total_mm3(self) -> float:
        """Суммарные потери."""
        return self.kerf_mm3 + self.planing_mm3 + self.edge_trim_mm3 + self.offcut_mm3


@dataclass(frozen=True, slots=True)
class MaterialReport:
    """Что купить и почему этого больше, чем «сумма объёмов деталей»."""

    stock: tuple[StockPiece, ...]
    panel_raw_width_mm: float
    panel_raw_length_mm: float
    panel_raw_thickness_mm: float
    crosscut_step_real_mm: float
    strip_count: int
    board_volume_mm3: float
    raw_volume_mm3: float
    losses: Losses

    @property
    def overhead_ratio(self) -> float:
        """Во сколько раз закупка больше готовой доски: 0.3 — это +30%."""
        return self.raw_volume_mm3 / self.board_volume_mm3 - 1.0


def material_report(
    prog: Program, allowances: Allowances | None = None
) -> MaterialReport:
    """Посчитать сырьё и разбивку потерь по программе."""
    allow = allowances or Allowances()
    execution = prog.run()

    glue = next((op for op in prog.operations if isinstance(op, Glue)), None)
    crosscut = next((op for op in prog.operations if isinstance(op, Crosscut)), None)
    if glue is None or crosscut is None:
        raise ValueError("для расчёта материала нужны склейка щита и торцовка")

    assemblies = sum(1 for op in prog.operations if isinstance(op, Assemble))
    strip_count = next(cut.count for cut in execution.cuts if cut.angle_deg == 90.0)

    # Каждая склейка после торцовки строгается по пласти доски и съедает высоту,
    # поэтому пилить надо выше, чем объявлено в программе.
    step_real = crosscut.step_mm + assemblies * allow.planing_mm

    panel_width = glue.width_mm
    panel_thickness = glue.thickness_mm
    raw_width = panel_width + 2 * allow.edge_trim_mm
    raw_thickness = panel_thickness + allow.planing_mm
    trimmed_length = strip_count * step_real + (strip_count - 1) * allow.kerf_mm
    raw_length = trimmed_length + 2 * allow.edge_trim_mm

    stock: list[StockPiece] = []
    last = len(glue.strips) - 1
    for index, strip in enumerate(glue.strips):
        width = strip.width_mm
        if index == 0:
            width += allow.edge_trim_mm
        if index == last:
            width += allow.edge_trim_mm
        stock.append(StockPiece(strip.species, width, raw_thickness, raw_length))

    board_area = execution.board.area_mm2
    board_volume = board_area * execution.board.thickness_mm
    raw_volume = raw_width * raw_length * raw_thickness

    planing = raw_width * raw_length * allow.planing_mm
    planing += assemblies * board_area * allow.planing_mm
    edge_trim = (raw_width * raw_length - panel_width * trimmed_length) * panel_thickness
    kerf = (strip_count - 1) * allow.kerf_mm * panel_width * panel_thickness
    offcut = raw_volume - board_volume - planing - edge_trim - kerf

    return MaterialReport(
        stock=tuple(stock),
        panel_raw_width_mm=raw_width,
        panel_raw_length_mm=raw_length,
        panel_raw_thickness_mm=raw_thickness,
        crosscut_step_real_mm=step_real,
        strip_count=strip_count,
        board_volume_mm3=board_volume,
        raw_volume_mm3=raw_volume,
        losses=Losses(kerf, planing, edge_trim, offcut),
    )
