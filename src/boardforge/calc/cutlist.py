"""Карта раскроя: что пилить, из чего и куда потом ставить.

Ничего нового про доску здесь не считается — всё выводится из программы и её
исполнения, как и узор. Смысл модуля в другом: разложить то же самое по
строчкам, которые можно унести в мастерскую на бумаге.

Два уровня, и путать их нельзя. **Рейка** — то, что покупают: доска породы,
из которой склеят щит; у неё сырые размеры, с припусками. **Полоса** — то, что
получилось после реза и что берут в руки при сборке; у неё чистовые размеры
в системе координат плана, то есть ровно те, что видно на превью.

Отсюда и нумерация: рейка щита A — `A1`, полоса того же щита — `A-01`. Разные
формы записи у разных вещей: на распечатке они лежат в двух таблицах, и спутать
их значит отпилить не то.

Полос перечисляются **все стадии**, а не только первая. У углового узора щит
режут, склеивают и режут снова; на каждой стадии в руках оказывается своя пачка
деталей, и без номеров вторую от первой не отличить.

Полоса, не попавшая ни в одну склейку, — не обязательно отход. У кубов (Р23)
половина полос каждого щита это комплект на вторую доску, и `spare_boards`
считает, сколько таких досок ещё выйдет из остатка.
"""

from dataclasses import dataclass, replace

from ..core.ops import Assemble, Glue
from ..core.program import Program
from .allowances import Allowances
from .material import material_report


@dataclass(frozen=True, slots=True)
class StockItem:
    """Позиция закупки: рейка щита в сыром размере, до строгания и обрезки."""

    number: str
    billet: str
    strip: int
    species: str
    width_mm: float
    thickness_mm: float
    length_mm: float

    @property
    def size(self) -> str:
        """Размер одной строкой: длина × ширина × толщина."""
        return f"{self.length_mm:.0f} × {self.width_mm:.1f} × {self.thickness_mm:.1f}"


@dataclass(frozen=True, slots=True)
class Placement:
    """Куда полоса встаёт в склейке."""

    assembly: str
    position: int
    offset_mm: float
    turned: bool
    flipped: bool

    @property
    def note(self) -> str:
        """Что сделать с полосой перед склейкой, словами."""
        notes = []
        if self.turned:
            notes.append("развернуть на 180°")
        if self.flipped:
            notes.append("перевернуть на другую сторону")
        if abs(self.offset_mm) > 1e-9:
            notes.append(f"сдвинуть на {self.offset_mm:+.1f} мм")
        return ", ".join(notes)


@dataclass(frozen=True, slots=True)
class CutPart:
    """Полоса: чистовая деталь, которую берут в руки при сборке."""

    number: str
    billet: str
    index: int
    species: tuple[str, ...]
    width_mm: float
    length_mm: float
    height_mm: float
    angle_deg: float
    step_mm: float
    op_index: int
    """Номер операции реза в программе — им стадии отличаются друг от друга."""
    area_mm2: float
    placement: Placement | None
    reusable: bool = False
    """Годится ли полоса в следующую такую же доску.

    Только про остаток: полоса, уже стоящая в доске, в остатке не лежит, и
    у неё это всегда `False`. Годной считается цельная полоса площадью не
    меньше худшей из пошедших в дело — порог берётся из самой доски, а не
    назначается. Цельность проверяется отдельно от площади, потому что рез
    под углом идёт через щит наискось: с краёв выходят не полосы, а россыпь
    кусков с дырами между ними, и площадь у такой бывает приличная.
    """

    @property
    def spare(self) -> bool:
        """Осталась ли полоса невостребованной."""
        return self.placement is None

    @property
    def size(self) -> str:
        """Габарит в плане плюс высота доски."""
        return f"{self.length_mm:.1f} × {self.width_mm:.1f} × {self.height_mm:.1f}"

    @property
    def square(self) -> bool:
        """Прямой ли рез: у прямого угол в карте не пишут, он и так 90°."""
        return abs(self.angle_deg - 90.0) < 1e-9


@dataclass(frozen=True, slots=True)
class CutStage:
    """Один рез: чем режут, с каким шагом и что из этого вышло."""

    op_index: int
    billet: str
    angle_deg: float
    step_mm: float
    parts: tuple[CutPart, ...]

    @property
    def used(self) -> tuple[CutPart, ...]:
        """Полосы, ушедшие в дело."""
        return tuple(part for part in self.parts if not part.spare)

    @property
    def keepers(self) -> tuple[CutPart, ...]:
        """Годный остаток — полосы, которые не жалко отложить до следующей доски."""
        return tuple(part for part in self.parts if part.reusable)

    @property
    def spare_boards(self) -> int:
        """Сколько ещё раз хватит годного остатка на такой же комплект."""
        used = len(self.used)
        return len(self.keepers) // used if used else 0


@dataclass(frozen=True, slots=True)
class CutList:
    """Карта раскроя целиком: закупка, стадии реза и что из них вышло."""

    stock: tuple[StockItem, ...]
    stages: tuple[CutStage, ...]
    panels: tuple[str, ...]
    """Щиты, склеенные из купленных реек: по ним идёт закупка."""
    final: tuple[str, ...]
    """Заготовки, из деталей которых собрана сама доска."""

    @property
    def parts(self) -> tuple[CutPart, ...]:
        """Все полосы всех стадий по порядку реза."""
        return tuple(part for stage in self.stages for part in stage.parts)

    @property
    def used(self) -> tuple[CutPart, ...]:
        """Полосы, попавшие в склейку."""
        return tuple(part for part in self.parts if not part.spare)

    @property
    def spare(self) -> tuple[CutPart, ...]:
        """Полосы, оставшиеся после сборки."""
        return tuple(part for part in self.parts if part.spare)

    def of_billet(self, billet: str) -> tuple[CutPart, ...]:
        """Полосы одной заготовки по порядку реза."""
        return tuple(part for part in self.parts if part.billet == billet)

    @property
    def final_stages(self) -> tuple[CutStage, ...]:
        """Резы, чьи полосы идут прямо в доску."""
        return tuple(stage for stage in self.stages if stage.billet in self.final)

    @property
    def spare_boards(self) -> int:
        """Сколько ещё таких же досок выйдет из уже купленного и распиленного.

        Считается по последним резам, а не по всем: полосы ранних стадий
        в остатке лежать не могут — их склеили в щиты следующей стадии, и
        засчитать их второй раз значит посчитать одно дерево дважды.

        Ноль — честный ответ, а не отсутствие ответа: он значит, что остаток
        комплекта не образует и в смете идёт в отход, а не в актив.
        """
        sets = [stage.spare_boards for stage in self.final_stages if stage.used]
        return min(sets) if sets else 0


def _placements(prog: Program) -> dict[tuple[str, int], Placement]:
    """Куда каждая деталь попала при склейке, по ссылке (заготовка, номер)."""
    found: dict[tuple[str, int], Placement] = {}
    for op in prog.operations:
        if not isinstance(op, Assemble):
            continue
        flipped = op.flipped or (False,) * len(op.pieces)
        for slot, ref in enumerate(op.pieces):
            found[(ref.billet, ref.index)] = Placement(
                assembly=op.id,
                position=slot + 1,
                offset_mm=op.offsets_mm[slot],
                turned=op.reversed[slot],
                flipped=flipped[slot],
            )
    return found


def cut_list(prog: Program, allowances: Allowances | None = None) -> CutList:
    """Собрать карту раскроя по программе."""
    execution = prog.run()
    material = material_report(prog, allowances)
    placed = _placements(prog)

    stock: list[StockItem] = []
    for panel in material.panels:
        for index, item in enumerate(panel.stock, start=1):
            stock.append(
                StockItem(
                    number=f"{panel.billet}{index}",
                    billet=panel.billet,
                    strip=index,
                    species=item.species,
                    width_mm=item.width_mm,
                    thickness_mm=item.thickness_mm,
                    length_mm=item.length_mm,
                )
            )

    stages: list[CutStage] = []
    for cut in execution.cuts:
        pieces = execution.billets.get(cut.billet, ())
        parts = [
            CutPart(
                number=f"{cut.billet}-{index + 1:02d}",
                billet=cut.billet,
                index=index + 1,
                species=tuple(dict.fromkeys(piece.species for piece in part.pieces)),
                width_mm=part.width_mm,
                length_mm=part.length_mm,
                height_mm=part.thickness_mm,
                angle_deg=cut.angle_deg,
                step_mm=cut.step_mm,
                op_index=cut.op_index,
                area_mm2=part.area_mm2,
                placement=placed.get((cut.billet, index)),
            )
            for index, part in enumerate(pieces)
        ]
        stages.append(
            CutStage(
                op_index=cut.op_index,
                billet=cut.billet,
                angle_deg=cut.angle_deg,
                step_mm=cut.step_mm,
                parts=tuple(_mark_reusable(parts, pieces)),
            )
        )

    return CutList(
        stock=tuple(stock),
        stages=tuple(stages),
        panels=tuple(op.id for op in prog.operations if isinstance(op, Glue)),
        final=_final_sources(prog),
    )


def _mark_reusable(parts: list[CutPart], pieces: tuple) -> list[CutPart]:
    """Отметить в остатке то, что годится в следующую доску.

    Цельность считается только у полос, прошедших порог по площади. Проверка
    идёт через объединение всех ячеек полосы и на кубах стоит миллисекунды;
    полос там две сотни, а до порога доходит десяток.
    """
    used = [part for part in parts if not part.spare]
    if not used:
        return parts
    floor = min(part.area_mm2 for part in used) - 1e-6
    return [
        replace(part, reusable=True)
        if part.spare and part.area_mm2 >= floor and _is_solid(pieces[index])
        else part
        for index, part in enumerate(parts)
    ]


def _is_solid(part: object) -> bool:
    """Один ли кусок эта полоса и нет ли в ней дыр.

    По контуру, а не по числу ячеек: ячеек в полосе десятки, и они обязаны
    быть склеены между собой. Разъехались — это уже не деталь, а россыпь.
    """
    outline = part.outline  # type: ignore[attr-defined]
    shapes = list(getattr(outline, "geoms", [outline]))
    return len(shapes) == 1 and not shapes[0].interiors


def _final_sources(prog: Program) -> tuple[str, ...]:
    """Из чьих деталей склеена сама доска — по последней склейке в программе."""
    for op in reversed(prog.operations):
        if isinstance(op, Assemble):
            return op.sources
    return ()


__all__ = ["CutList", "CutPart", "CutStage", "Placement", "StockItem", "cut_list"]
