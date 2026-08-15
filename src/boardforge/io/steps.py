"""Пошаговая инструкция: программа, прочитанная как порядок действий.

Никакого отдельного «сценария сборки» здесь нет и быть не может. Доска — это
программа, значит шаги — это её операции, а картинка шага — состояние верстака
после него. И то и другое **выводится**: шаг ничего не знает такого, чего не
знает `Program`.

Состояния берутся у `Program.trace()`, а не исполнением префиксов
`operations[:k]` — большинство префиксов валидатор законно не пропускает
(«заготовка A осталась россыпью»), и рисовать по ним было бы нечего.

Здесь же живёт `describe` — операция человеческим языком. Она пришла из
`web/presenters.py`, и переехала вниз, а не скопировалась: панель операций
в браузере и распечатка обязаны называть одно и то же одними словами.
Направление зависимостей соблюдено — веб стоит над `io/`, не наоборот.
"""

from dataclasses import dataclass, replace

from ..core.ops import Assemble, Crop, Crosscut, Cut, Glue, Operation, StandOnEnd
from ..core.piece import Part
from ..core.program import Frame, Program
from ..core.species import Species, load_species
from ..core.units import EPS, MILLIMETRES, Units
from ..render.blueprint import FOOTER_PX, Sheet, render_blueprint, sheet_margin_mm
from ..render.style import RenderOptions

DRAWING_BOX_PX = (620.0, 300.0)
"""Окно, в которое вписывается чертёж шага: ширина и высота в пикселях листа.

Масштаб у каждого шага свой, и это не украшение: щит длиной в метр и полоса
шириной в сорок миллиметров при общем масштабе дали бы одну картинку во весь
лист и одну в ноготь. Читают их подряд, поэтому приводятся они к общему окну.

Высота в окне обязательна, а не только ширина. Без неё щит, который вдвое
длиннее своей ширины, растягивается на страницу целиком, и на инструкцию из
семи шагов уходит одиннадцать листов вместо трёх.
"""


@dataclass(frozen=True, slots=True)
class Step:
    """Один шаг инструкции: что сделать и что должно получиться."""

    number: int
    kind: str
    title: str
    detail: str
    outcome: str
    """Что лежит на верстаке после шага — измерено по кадру, а не по операции."""

    drawing: str
    """Чертёж шага, готовый для вставки в HTML: без заголовка XML.

    Без заголовка намеренно: SVG идёт в страницу элементом, а не отдельным
    документом, — ровно как чертёж готовой доски в `report.py`.
    """


def describe(
    op: Operation, catalogue: dict[str, Species], units: Units
) -> tuple[str, str, str]:
    """Название операции, её суть и подробности — тремя строками."""
    match op:
        case Glue():
            rails = ", ".join(
                f"{species_name(strip.species, catalogue)} {units.format(strip.width_mm)}"
                for strip in op.strips
            )
            return (
                "Склейка",
                f"Щит {op.id} из {len(op.strips)} реек",
                f"{rails}. Длина {units.format(op.length_mm)}, "
                f"толщина {units.format(op.thickness_mm)}",
            )
        case Crosscut():
            return (
                "Торцовка",
                f"Щит {op.source} режется поперёк с шагом {units.format(op.step_mm)}",
                "Шаг торцовки становится высотой доски",
            )
        case StandOnEnd():
            return (
                "На торец",
                f"Полосы щита {op.source} ставятся на торец",
                "Волокна становятся вертикальными: это и делает доску торцевой",
            )
        case Cut():
            return (
                "Рез в плане",
                f"Щит {op.source} под {op.angle_deg:g}° "
                f"с шагом {units.format(op.step_mm)}",
                "Волокна уже вертикальны, поэтому угол задаёт узор, а не текстуру",
            )
        case Assemble():
            turned = sum(1 for value in op.reversed if value)
            shifted = sum(1 for value in op.offsets_mm if abs(value) > 1e-9)
            notes = [f"{len(op.pieces)} деталей из {', '.join(op.sources)}"]
            if turned:
                notes.append(f"развёрнуто {turned}")
            if shifted:
                notes.append(f"со сдвигом {shifted}")
            if op.flipped and any(op.flipped):
                notes.append(f"перевёрнуто {sum(1 for v in op.flipped if v)}")
            return ("Склейка деталей", f"Щит {op.id}", ", ".join(notes))
        case Crop():
            sides = [
                (name, value)
                for name, value in (
                    ("слева", op.left),
                    ("справа", op.right),
                    ("сверху", op.top),
                    ("снизу", op.bottom),
                )
                if value
            ]
            detail = ", ".join(f"{name} {units.format(value)}" for name, value in sides)
            return (
                "Обрезка",
                f"Щит {op.source} в размер",
                detail or "ничего не срезается",
            )
    return ("Операция", type(op).__name__, "")


def species_name(key: str, catalogue: dict[str, Species]) -> str:
    found = catalogue.get(key)
    return found.name if found else key


def _size(part: Part, units: Units) -> str:
    return f"{units.format(part.width_mm)} × {units.format(part.length_mm)}"


def outcome(frame: Frame, units: Units) -> str:
    """Что получилось после шага — измерением, а не пересказом операции.

    Число деталей и их размер операция не знает: «шаг 40 мм» превращается
    в девять полос или в одиннадцать в зависимости от длины щита, и ошибка
    здесь стоит поездки в магазин. Одинаковость проверяется по факту —
    после углового реза крайние полосы короче середины.
    """
    parts = frame.parts
    first = parts[0]
    if len(parts) == 1:
        return f"заготовка {frame.target}: {_size(first, units)}"

    same = all(
        abs(part.width_mm - first.width_mm) < EPS
        and abs(part.length_mm - first.length_mm) < EPS
        for part in parts
    )
    if same:
        return f"заготовка {frame.target}: {len(parts)} деталей {_size(first, units)}"
    return (
        f"заготовка {frame.target}: {len(parts)} деталей разного размера, "
        f"на чертеже первая — {_size(first, units)}"
    )


def _fit_scale(part: Part, fallback: float) -> float:
    """Масштаб, при котором деталь с полями и штампом влезает в окно.

    Поле вокруг чертежа спрашивается у самого чертёжника: на мелком масштабе
    оно раздвигается до пиксельного порога, и посчитанный без этого масштаб
    дал бы картинку шире окна.
    """
    box_width, box_height = DRAWING_BOX_PX
    scale = fallback
    for _ in range(4):  # поле зависит от масштаба, масштаб от поля — сходится за два
        margin = sheet_margin_mm(scale)
        width = part.width_mm + 2 * margin
        height = part.length_mm + 2 * margin
        if width <= 0 or height <= 0:
            return fallback
        scale = min(box_width / width, (box_height - FOOTER_PX) / height)
    return scale


def _drawing(
    frame: Frame,
    number: int,
    kind: str,
    note: str,
    catalogue: dict[str, Species],
    options: RenderOptions,
    units: Units,
) -> str:
    """Чертёж состояния после шага, приведённый к общей ширине листа.

    В штампе — только номер шага, название операции и что получилось. Всё
    остальное пишет страница вокруг: повторять её текст внутри картинки незачем,
    а вот назвать себя картинка обязана — её вырезают и уносят к станку.
    """
    part = frame.parts[0]
    fitted = replace(options, scale=_fit_scale(part, options.scale))
    drawn = render_blueprint(
        part, catalogue, fitted, Sheet(title=kind, step=number, note=note), units
    )
    return drawn.split("\n", 1)[1]


def instructions(
    program: Program,
    catalogue: dict[str, Species] | None = None,
    units: Units = MILLIMETRES,
    options: RenderOptions | None = None,
) -> list[Step]:
    """Разложить программу по шагам — с чертежом состояния после каждого."""
    catalogue = catalogue if catalogue is not None else load_species()
    options = options or RenderOptions()
    steps = []
    for frame in program.trace():
        kind, title, detail = describe(frame.operation, catalogue, units)
        result = outcome(frame, units)
        steps.append(
            Step(
                number=frame.index + 1,
                kind=kind,
                title=title,
                detail=detail,
                outcome=result,
                drawing=_drawing(
                    frame, frame.index + 1, kind, result, catalogue, options, units
                ),
            )
        )
    return steps


__all__ = [
    "DRAWING_BOX_PX",
    "Step",
    "describe",
    "instructions",
    "outcome",
    "species_name",
]
