"""Распечатка для мастерской: одна страница, с которой идут пилить.

Собирает вместе то, что посчитали `calc/`: карту раскроя, разбивку потерь,
смету, список в магазин и предупреждения о породах. Плюс чертёж — тем же
вектором, что идёт на экран.

Формат — HTML, и это не полумера. На Дне 6 тот же документ уходит в WeasyPrint
и становится PDF: один источник, один вид на экране и на бумаге. Поэтому здесь
нет ни одного экранного украшения — только то, что переживёт лазерный принтер.

Числа сюда не считаются. Всё, что видно на странице, приходит готовым из
`calc/`, а этот модуль расставляет по строчкам. Появись здесь арифметика —
распечатка начнёт расходиться с тем, что показывает интерфейс.
"""

from dataclasses import dataclass
from pathlib import Path

from ..calc.allowances import Allowances
from ..calc.cutlist import CutList, cut_list
from ..calc.estimate import Estimate, Prices, estimate
from ..calc.material import MaterialReport, material_report
from ..calc.nesting import NestingPlan, nest_stock
from ..calc.warnings import species_issues
from ..core.program import Issue, Program
from ..core.species import Species, load_species
from ..core.units import MILLIMETRES, Units
from ..render.blueprint import Sheet, render_blueprint
from ..render.style import RenderOptions

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"


@dataclass(frozen=True, slots=True)
class Workshop:
    """Всё, что нужно распечатке, посчитанное один раз."""

    program: Program
    catalogue: dict[str, Species]
    material: MaterialReport
    listing: CutList
    bill: Estimate
    nesting: NestingPlan
    issues: tuple[Issue, ...]
    units: Units

    @property
    def losses(self) -> tuple[tuple[str, float, float], ...]:
        """Разбивка потерь: статья, объём в дм³, доля закупки.

        Пропил, строгание и обрезка — раздельно, как и требует расчёт: сумма
        их в одну строку прячет ровно то, чем узоры отличаются по цене.
        """
        raw = self.material.raw_volume_mm3
        parts = (
            ("Пропил", self.material.losses.kerf_mm3),
            ("Строгание", self.material.losses.planing_mm3),
            ("Обрезка торцов", self.material.losses.end_trim_mm3),
            ("Обрезка кромок", self.material.losses.edge_trim_mm3),
            ("Обрезь и недорез", self.material.losses.offcut_mm3),
        )
        return tuple(
            (name, value / 1e6, value / raw if raw else 0.0) for name, value in parts
        )

    @property
    def board_dm3(self) -> float:
        """Объём самой доски."""
        return self.material.board_volume_mm3 / 1e6

    @property
    def raw_dm3(self) -> float:
        """Объём закупки."""
        return self.material.raw_volume_mm3 / 1e6


def collect(
    prog: Program,
    catalogue: dict[str, Species] | None = None,
    prices: Prices | None = None,
    allowances: Allowances | None = None,
    units: Units = MILLIMETRES,
) -> Workshop:
    """Посчитать всё, что попадёт в распечатку."""
    catalogue = catalogue if catalogue is not None else load_species()
    listing = cut_list(prog, allowances)
    return Workshop(
        program=prog,
        catalogue=catalogue,
        material=material_report(prog, allowances),
        listing=listing,
        bill=estimate(prog, prices, catalogue, allowances),
        nesting=nest_stock(listing),
        issues=tuple(species_issues(prog, catalogue)),
        units=units,
    )


def _environment():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["mm"] = lambda value: MILLIMETRES.format(value)
    env.filters["money"] = lambda value: f"{value:,.0f}".replace(",", " ")
    env.filters["percent"] = lambda value: f"{value * 100:.1f}%"
    return env


def render_workshop(shop: Workshop, options: RenderOptions | None = None) -> str:
    """Собрать страницу распечатки."""
    board = shop.program.run().board
    drawing = render_blueprint(
        board,
        shop.catalogue,
        options,
        Sheet(title="Готовая доска", note="Буква в ячейке — порода, см. обозначения"),
        shop.units,
    )
    # Заголовок XML внутри страницы не нужен и ломает вставку: SVG идёт
    # в HTML как элемент, а не как отдельный документ.
    inline = drawing.split("\n", 1)[1]

    # Шаги считаются здесь, а не в `collect`: у каждого свой чертёж, и стоит
    # это столько же, сколько все остальные расчёты цеха вместе. Панель «Цех»
    # в редакторе пересчитывается на каждую правку состава щита, и класть туда
    # рендер восьми чертежей нельзя. Распечатку открывают намеренно и один раз.
    from .steps import instructions

    return (
        _environment()
        .get_template("workshop.html")
        .render(
            shop=shop,
            board=board,
            drawing=inline,
            letters=_letters(board, shop.catalogue),
            steps=instructions(shop.program, shop.catalogue, shop.units, options),
        )
    )


def _letters(board: object, catalogue: dict[str, Species]) -> list[tuple[str, str]]:
    from ..render.svg import species_letters

    letters = species_letters(
        piece.species
        for piece in board.pieces  # type: ignore[attr-defined]
    )
    return [
        (letter, catalogue[key].name if key in catalogue else key)
        for key, letter in sorted(letters.items(), key=lambda item: item[1])
    ]


def write_workshop(
    shop: Workshop,
    directory: Path,
    options: RenderOptions | None = None,
    pdf: bool = False,
) -> Path:
    """Разложить распечатку по файлам и вернуть путь к странице.

    Принимает уже посчитанное, а не программу: расчёт цеха стоит сотни
    миллисекунд, и вызывающему он почти всегда нужен и сам — хотя бы чтобы
    сказать в консоль, во что доска обошлась.

    `pdf` печатает **ту же** разметку, что легла в `.html`, — не пересобирая
    её второй раз. Разойдись эти два документа, и цех получил бы не то, что
    видно на экране.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    board = shop.program.run().board
    (directory / "blueprint.svg").write_text(
        render_blueprint(board, shop.catalogue, options, Sheet(), shop.units),
        encoding="utf-8",
    )
    markup = render_workshop(shop, options)
    page = directory / "workshop.html"
    page.write_text(markup, encoding="utf-8")
    if pdf:
        from .pdf import write_pdf

        write_pdf(markup, directory / "workshop.pdf")
    return page


__all__ = ["Workshop", "collect", "render_workshop", "write_workshop"]
