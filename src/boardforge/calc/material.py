"""Обратный ход: от чистовых размеров программы к сырью и потерям.

Программа не знает о пропиле и строгании (см. docs/decisions.md, Р0.1).
Здесь мы идём назад: сколько дерева надо купить, чтобы после всех потерь
получить объявленные чистовые размеры.
"""

from dataclasses import dataclass

from ..core.ops import Assemble, Crosscut, Glue
from ..core.program import Execution, Program
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
class PanelStock:
    """Сырьё под один щит программы."""

    billet: str
    stock: tuple[StockPiece, ...]
    raw_width_mm: float
    raw_length_mm: float
    raw_thickness_mm: float
    trimmed_length_mm: float
    crosscut_step_real_mm: float
    strip_count: int

    @property
    def raw_volume_mm3(self) -> float:
        """Объём сырья на щит."""
        return self.raw_width_mm * self.raw_length_mm * self.raw_thickness_mm


@dataclass(frozen=True, slots=True)
class Losses:
    """Куда девается разница между закупкой и доской."""

    kerf_mm3: float
    planing_mm3: float
    end_trim_mm3: float
    edge_trim_mm3: float
    offcut_mm3: float

    @property
    def total_mm3(self) -> float:
        """Суммарные потери."""
        return (
            self.kerf_mm3
            + self.planing_mm3
            + self.end_trim_mm3
            + self.edge_trim_mm3
            + self.offcut_mm3
        )


@dataclass(frozen=True, slots=True)
class MaterialReport:
    """Что купить и почему этого больше, чем «сумма объёмов деталей»."""

    panels: tuple[PanelStock, ...]
    board_volume_mm3: float
    raw_volume_mm3: float
    losses: Losses

    @property
    def stock(self) -> tuple[StockPiece, ...]:
        """Единый список закупки по всем щитам."""
        return tuple(item for panel in self.panels for item in panel.stock)

    @property
    def overhead_ratio(self) -> float:
        """Во сколько раз закупка больше готовой доски: 0.3 — это +30%."""
        return self.raw_volume_mm3 / self.board_volume_mm3 - 1.0

    @property
    def economy(self) -> float:
        """Какая доля купленного дерева доехала до доски.

        Здесь и только здесь. `fitness.economy` берёт это же число: мера узора
        и строка сметы обязаны говорить одно и то же, иначе генератор оптимизирует
        не то, за что потом платят.
        """
        if self.raw_volume_mm3 <= 0:
            return 0.0
        return max(0.0, min(1.0, self.board_volume_mm3 / self.raw_volume_mm3))

    def panel(self, billet: str) -> PanelStock:
        """Сырьё под конкретный щит."""
        for item in self.panels:
            if item.billet == billet:
                return item
        raise KeyError(f"щит {billet} в расчёте не участвует")


def _panel_stock(
    glue: Glue,
    crosscut: Crosscut,
    strip_count: int,
    assemblies_after: int,
    allow: Allowances,
) -> PanelStock:
    # Каждая склейка после торцовки строгается по пласти доски и съедает высоту,
    # поэтому пилить надо выше, чем объявлено в программе.
    step_real = crosscut.step_mm + assemblies_after * allow.planing_mm
    trimmed_length = strip_count * step_real + (strip_count - 1) * allow.kerf_mm

    raw_width = glue.width_mm + 2 * allow.edge_trim_mm
    raw_length = trimmed_length + 2 * allow.end_trim_mm
    raw_thickness = glue.thickness_mm + allow.planing_mm

    stock: list[StockPiece] = []
    last = len(glue.strips) - 1
    for index, strip in enumerate(glue.strips):
        width = strip.width_mm
        if index == 0:
            width += allow.edge_trim_mm
        if index == last:
            width += allow.edge_trim_mm
        stock.append(StockPiece(strip.species, width, raw_thickness, raw_length))

    return PanelStock(
        billet=glue.id,
        stock=tuple(stock),
        raw_width_mm=raw_width,
        raw_length_mm=raw_length,
        raw_thickness_mm=raw_thickness,
        trimmed_length_mm=trimmed_length,
        crosscut_step_real_mm=step_real,
        strip_count=strip_count,
    )


def _glue_ups_downstream(prog: Program, billet: str, after: int) -> int:
    """Через сколько склеек проходит материал щита после его торцовки.

    Считать все `Assemble` программы нельзя: у кубов два щита-близнеца, их
    операции идут подряд, и щит A получал бы припуск ещё и за склейки щита B.
    Близнецы при этом одинаковы, а припуск у них выходил разный — верный признак,
    что считалось не то. Материал прослеживается по имени: склейка касается щита,
    если среди её источников есть он сам или то, во что он уже вошёл.
    """
    reached = {billet}
    count = 0
    for index, op in enumerate(prog.operations):
        if index <= after or not isinstance(op, Assemble):
            continue
        if reached.intersection(op.sources):
            reached.add(op.id)
            count += 1
    return count


def _planed_area(prog: Program, execution: Execution) -> float:
    """Площадь, проходящая под строгальным станком за все склейки.

    По площади того щита, который вышел из склейки, а не готовой доски:
    промежуточный щит углового узора вдвое-втрое больше неё, и считать его
    по её размеру — занизить строгание там, где его больше всего.
    """
    total = 0.0
    for op in prog.operations:
        if not isinstance(op, Assemble):
            continue
        parts = execution.billets.get(op.id, ())
        if parts:
            total += parts[0].area_mm2
    return total


def material_report(
    prog: Program, allowances: Allowances | None = None
) -> MaterialReport:
    """Посчитать сырьё и разбивку потерь по программе."""
    allow = allowances or Allowances()
    execution = prog.run()

    crosscuts = {
        op.source: (index, op)
        for index, op in enumerate(prog.operations)
        if isinstance(op, Crosscut)
    }
    strips_of = {cut.billet: cut.count for cut in execution.cuts if cut.angle_deg == 90.0}

    panels: list[PanelStock] = []
    for op in prog.operations:
        if not isinstance(op, Glue):
            continue
        if op.id not in crosscuts:
            raise ValueError(
                f"щит {op.id} ни разу не торцован — расчёт материала не определён"
            )
        cut_index, crosscut = crosscuts[op.id]
        panels.append(
            _panel_stock(
                op,
                crosscut,
                strips_of[op.id],
                _glue_ups_downstream(prog, op.id, cut_index),
                allow,
            )
        )

    board_area = execution.board.area_mm2
    board_volume = board_area * execution.board.thickness_mm
    raw_volume = sum(panel.raw_volume_mm3 for panel in panels)

    planing = _planed_area(prog, execution) * allow.planing_mm
    end_trim = 0.0
    edge_trim = 0.0
    kerf = 0.0
    for panel, glue in zip(panels, _glues(prog), strict=True):
        planing += panel.raw_width_mm * panel.raw_length_mm * allow.planing_mm
        end_trim += (
            (panel.raw_length_mm - panel.trimmed_length_mm)
            * panel.raw_width_mm
            * glue.thickness_mm
        )
        edge_trim += (
            (panel.raw_width_mm - glue.width_mm)
            * panel.trimmed_length_mm
            * glue.thickness_mm
        )
        kerf += (
            (panel.strip_count - 1) * allow.kerf_mm * glue.width_mm * glue.thickness_mm
        )

    offcut = raw_volume - board_volume - planing - end_trim - edge_trim - kerf

    return MaterialReport(
        panels=tuple(panels),
        board_volume_mm3=board_volume,
        raw_volume_mm3=raw_volume,
        losses=Losses(kerf, planing, end_trim, edge_trim, offcut),
    )


def _glues(prog: Program) -> list[Glue]:
    return [op for op in prog.operations if isinstance(op, Glue)]
