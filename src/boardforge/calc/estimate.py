"""Себестоимость: во что обходится доска и сколько её выйдет из закупки.

Считается **по объёму закупки, а не доски**. Разница не бухгалтерская: у
углового узора в отход уходит половина щита, у кубов четыре пятых, и смета,
посчитанная по готовой доске, покажет цену вчетверо ниже той, что придётся
заплатить в магазине.

Цены — не свойство доски и в программу не входят. Доска остаётся программой
операций (главный инвариант), а прайс-лист живёт рядом, правится пользователем
и в файл проекта не попадает, как не попадают туда единицы измерения.

Числа по умолчанию — порядок величины, а не справочник. Плотности и усушка
сверены по Wood Handbook и The Wood Database, а цена дерева зависит от города,
поставщика и дня недели, и сверять её бессмысленно: её задают.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..core.ops import Assemble, Glue
from ..core.program import Program
from ..core.species import Species, load_species
from .allowances import Allowances
from .cutlist import cut_list
from .material import material_report

MM3_IN_M3 = 1e9
MM2_IN_M2 = 1e6

DEFAULT_PRICE_PER_M3 = {
    "maple_hard": 145_000.0,
    "walnut_black": 320_000.0,
    "cherry": 210_000.0,
    "ash": 95_000.0,
    "oak": 120_000.0,
    "beech": 90_000.0,
    "hornbeam": 110_000.0,
    "padauk": 340_000.0,
    "purpleheart": 380_000.0,
    "wenge": 420_000.0,
    "jatoba": 260_000.0,
    "sapele": 180_000.0,
}
"""Ориентир в рублях за кубометр обрезной доски камерной сушки. Правится."""

UNKNOWN_PRICE_PER_M3 = 150_000.0
"""Чем считать породу, которой нет в прайсе. Не ноль: бесплатного дерева
не бывает, и молчаливый ноль в смете хуже заведомо грубой цифры."""


@dataclass(frozen=True, slots=True)
class Prices:
    """Прайс и расходные нормы. Всё редактируется, ничто не выводится."""

    per_m3: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_PRICE_PER_M3)
    )
    unknown_per_m3: float = UNKNOWN_PRICE_PER_M3
    glue_kg_per_m2: float = 0.25
    """Расход ПВА D3 на квадратный метр шва — по обеим склеиваемым кромкам."""
    glue_per_kg: float = 900.0
    oil_l_per_m2: float = 0.08
    """Минеральное масло в два слоя. Торцевая доска пьёт заметно больше пласти,
    поэтому норма взята по верхней границе паспортной."""
    oil_per_l: float = 2_500.0
    currency: str = "₽"

    def __post_init__(self) -> None:
        for name in (
            "unknown_per_m3",
            "glue_kg_per_m2",
            "glue_per_kg",
            "oil_l_per_m2",
            "oil_per_l",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} не может быть отрицательным")
        for key, value in self.per_m3.items():
            if value < 0:
                raise ValueError(f"цена породы {key} не может быть отрицательной")

    def of(self, species: str) -> float:
        """Цена кубометра породы; для незнакомой — общая ставка."""
        return self.per_m3.get(species, self.unknown_per_m3)


@dataclass(frozen=True, slots=True)
class SpeciesCost:
    """Строка закупки по одной породе."""

    species: str
    name: str
    volume_mm3: float
    price_per_m3: float

    @property
    def volume_m3(self) -> float:
        """Объём в кубометрах — в них и торгуют."""
        return self.volume_mm3 / MM3_IN_M3

    @property
    def cost(self) -> float:
        """Сколько стоит эта позиция."""
        return self.volume_m3 * self.price_per_m3


@dataclass(frozen=True, slots=True)
class Estimate:
    """Смета: материал, расходники и что из всего этого выйдет."""

    species: tuple[SpeciesCost, ...]
    glue_kg: float
    glue_cost: float
    oil_l: float
    oil_cost: float
    weight_kg: float
    boards: int
    """Сколько досок выйдет из этой закупки. Единица — обычный случай; больше
    бывает там, где последний рез даёт лишний комплект полос (кубы, Р23)."""
    economy: float
    """Доля закупки, доехавшая до одной доски — та же мера, что в оценке узора."""
    prices: Prices

    @property
    def wood_cost(self) -> float:
        """Дерево по всем породам."""
        return sum(item.cost for item in self.species)

    @property
    def total(self) -> float:
        """Всё вместе."""
        return self.wood_cost + self.glue_cost + self.oil_cost

    @property
    def per_board(self) -> float:
        """Себестоимость одной доски.

        Делится на число досок, а не приравнивается к итогу: у кубов из той же
        закупки выходит комплект на вторую доску, и записать всю стоимость
        на первую — значит соврать вдвое.
        """
        return self.total / self.boards if self.boards else self.total

    @property
    def volume_m3(self) -> float:
        """Объём закупки."""
        return sum(item.volume_m3 for item in self.species)


def _glued_area_mm2(prog: Program, execution: object) -> float:
    """Площадь склеиваемых поверхностей: кромки в щите и швы между деталями.

    Считается по швам, а не по пласти: клей кладут на стык, и шов у щита из
    десяти реек длиннее, чем у щита из двух, при той же площади щита.
    """
    total = 0.0
    for op in prog.operations:
        if isinstance(op, Glue):
            total += (len(op.strips) - 1) * op.length_mm * op.thickness_mm
        elif isinstance(op, Assemble):
            parts = execution.billets.get(op.id, ())  # type: ignore[attr-defined]
            if parts:
                total += (len(op.pieces) - 1) * parts[0].length_mm * parts[0].thickness_mm
    return total


def _finished_area_mm2(board: object) -> float:
    """Площадь, которую покрывают маслом: обе пласти плюс четыре кромки."""
    width = board.width_mm  # type: ignore[attr-defined]
    length = board.length_mm  # type: ignore[attr-defined]
    height = board.thickness_mm  # type: ignore[attr-defined]
    return 2 * width * length + 2 * (width + length) * height


def _weight_kg(board: object, catalogue: dict[str, Species]) -> float:
    """Вес готовой доски: по каждой ячейке своя порода и своя плотность.

    По ячейкам, а не по средней плотности: доска из клёна с венге и доска
    из клёна с орехом одинаковы по объёму и различаются на четверть по весу,
    а поднимать её будут руками.
    """
    volume_by_species: dict[str, float] = {}
    for piece in board.pieces:  # type: ignore[attr-defined]
        volume_by_species[piece.species] = (
            volume_by_species.get(piece.species, 0.0) + piece.area_mm2
        )
    height = board.thickness_mm  # type: ignore[attr-defined]

    total = 0.0
    for species, area in volume_by_species.items():
        found = catalogue.get(species)
        if found is None:
            continue
        total += area * height / MM3_IN_M3 * found.density_kg_m3
    return total


def estimate(
    prog: Program,
    prices: Prices | None = None,
    catalogue: dict[str, Species] | None = None,
    allowances: Allowances | None = None,
) -> Estimate:
    """Посчитать смету по программе."""
    prices = prices or Prices()
    catalogue = catalogue if catalogue is not None else load_species()

    material = material_report(prog, allowances)
    listing = cut_list(prog, allowances)
    execution = prog.run()

    volumes: dict[str, float] = {}
    for item in material.stock:
        volumes[item.species] = volumes.get(item.species, 0.0) + item.volume_mm3

    species = tuple(
        SpeciesCost(
            species=key,
            name=catalogue[key].name if key in catalogue else key,
            volume_mm3=volume,
            price_per_m3=prices.of(key),
        )
        for key, volume in sorted(volumes.items())
    )

    glue_kg = _glued_area_mm2(prog, execution) / MM2_IN_M2 * prices.glue_kg_per_m2
    oil_l = _finished_area_mm2(execution.board) / MM2_IN_M2 * prices.oil_l_per_m2

    return Estimate(
        species=species,
        glue_kg=glue_kg,
        glue_cost=glue_kg * prices.glue_per_kg,
        oil_l=oil_l,
        oil_cost=oil_l * prices.oil_per_l,
        weight_kg=_weight_kg(execution.board, catalogue),
        boards=1 + listing.spare_boards,
        economy=material.economy,
        prices=prices,
    )


__all__ = [
    "DEFAULT_PRICE_PER_M3",
    "UNKNOWN_PRICE_PER_M3",
    "Estimate",
    "Prices",
    "SpeciesCost",
    "estimate",
]
