"""Библиотека узоров: четырнадцать шаблонов, все параметрические.

Шаблон — не константа и не картинка, а функция от размеров и набора пород,
возвращающая программу. Поменял ячейку с 40 на 32 — получил тот же узор
на другой доске, а не сломанный.

Почти все ортогональные узоры сводятся к одному построению: несколько щитов
из реек, торцовка, постановка на торец и склейка столбцов со сдвигами. Разница
между шахматкой, кирпичом и плетёнкой — только в том, какой столбец из какого
щита взят и на сколько ячеек сдвинут. Поэтому построение здесь одно
(`_assembled`), а шаблоны — таблицы сдвигов к нему.

Угловые узоры (шеврон, ёлочка, кубы) приходят из `patterns.py` и `cubes.py`:
у них своё построение и свои тесты на схождение.

## Чем закрывается каждый шаблон

Ортогональные объявляют **периоды** — векторы, вдоль которых узор обязан
переходить сам в себя. Это и есть их тест на схождение: ошибись в сдвиге хоть
одного столбца, и период сломается. Часть шаблонов вместо периода (или вместе
с ним) объявляет симметрию поворота на 180°.

Угловые периодов не объявляют: их сходимость проверяется по швам, каждый своим
тестом (`test_patterns.py`, `test_cubes.py`), и повторять это здесь незачем.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .cubes import CubePanel, cubes
from .ops import Assemble, Crop, Crosscut, Glue, PieceRef, StandOnEnd, Strip
from .patterns import StripedPanel, chevron, herringbone
from .program import Program

_BOARD = "BOARD"


@dataclass(frozen=True, slots=True)
class Pattern:
    """Узор: программа плюс то, чем он обязан оказаться.

    `periods_mm` — векторы трансляции, вдоль которых узор переходит в себя.
    `half_turn` — переходит ли узор в себя при повороте доски на 180°.
    Пустые оба — значит схождение проверяется отдельным тестом по швам
    (так у угловых узоров).
    """

    program: Program
    periods_mm: tuple[tuple[float, float], ...] = ()
    half_turn: bool = False


@dataclass(frozen=True, slots=True)
class Template:
    """Шаблон библиотеки: имя, описание и построение с параметрами."""

    key: str
    title: str
    summary: str
    build: Callable[..., Pattern]
    defaults: Mapping[str, Any] = field(default_factory=dict)

    def __call__(self, **overrides: Any) -> Pattern:
        """Собрать узор, подменив часть параметров."""
        unknown = set(overrides) - set(self.defaults)
        if unknown:
            raise ValueError(
                f"{self.key}: неизвестные параметры {sorted(unknown)}; "
                f"есть {sorted(self.defaults)}"
            )
        return self.build(**{**self.defaults, **overrides})


def _cycle(species: Sequence[str], count: int, start: int = 0) -> tuple[str, ...]:
    """Набор реек: породы по кругу, начиная с `start`."""
    return tuple(species[(start + index) % len(species)] for index in range(count))


def assemble_columns(
    billets: Sequence[Sequence[str]],
    cell_mm: float,
    columns: Sequence[tuple[int, float]],
    reversed_flags: Sequence[bool] | None = None,
) -> Program:
    """Общее построение ортогональных узоров.

    `billets` — набор реек каждого щита снизу вверх, в породах; все рейки
    шириной в ячейку. `columns` — из какого щита взят столбец и на сколько
    ячеек он сдвинут вверх. Сдвиг дробный законен: полкирпича — обычная кладка.

    Обрезка дописывается всегда, когда сдвиги не нулевые: столбцы разъезжаются,
    и сверху с снизу остаются ступеньки. Это не брак, а нормальное состояние
    щита до обрезки в размер (Р5), но узором ступеньки не являются.
    """
    if not billets:
        raise ValueError("узору нужен хотя бы один щит")
    if not columns:
        raise ValueError("узору нужен хотя бы один столбец")

    used = sorted({index for index, _ in columns})
    if used and (used[0] < 0 or used[-1] >= len(billets)):
        raise ValueError(f"столбец ссылается на щит вне набора: {used}")

    names = [chr(ord("A") + index) for index in range(len(billets))]
    counts = {name: 0 for name in names}
    for index, _ in columns:
        counts[names[index]] += 1

    operations: list[Any] = []
    for name, strips in zip(names, billets, strict=True):
        if counts[name] == 0:
            continue
        operations += [
            Glue(
                id=name,
                strips=tuple(Strip(species, cell_mm) for species in strips),
                # Столбец в плане — одна полоса торцовки: длины щита нужно
                # ровно столько шагов, сколько столбцов из него берут.
                length_mm=cell_mm * counts[name],
                thickness_mm=cell_mm,
            ),
            Crosscut(source=name, step_mm=cell_mm),
            StandOnEnd(source=name),
        ]

    taken = {name: 0 for name in names}
    pieces: list[PieceRef] = []
    offsets: list[float] = []
    for index, shift in columns:
        name = names[index]
        pieces.append(PieceRef(name, taken[name]))
        taken[name] += 1
        offsets.append(shift * cell_mm)

    flags = tuple(reversed_flags) if reversed_flags else (False,) * len(pieces)
    operations.append(
        Assemble(
            id=_BOARD,
            pieces=tuple(pieces),
            reversed=flags,
            offsets_mm=tuple(offsets),
        )
    )

    spread = max(offsets) - min(offsets)
    if spread > 0:
        operations.append(Crop(source=_BOARD, top=spread, bottom=spread))
    return Program(operations=tuple(operations))


def _single(
    species: Sequence[str],
    cell_mm: float,
    rows: int,
    shifts: Sequence[float],
    reversed_flags: Sequence[bool] | None = None,
    start: int = 0,
) -> Program:
    """Один щит, столбцы по таблице сдвигов — частый случай `_assembled`."""
    strips = _cycle(species, rows, start)
    return assemble_columns(
        [strips], cell_mm, [(0, shift) for shift in shifts], reversed_flags
    )


def _periods(
    cell_mm: float, along: float, across: float
) -> tuple[tuple[float, float], ...]:
    return ((along * cell_mm, 0.0), (0.0, across * cell_mm))


def stripes(species: Sequence[str], cell_mm: float, columns: int, rows: int) -> Pattern:
    """Полосы: сдвигов нет, все столбцы одинаковы."""
    program = _single(species, cell_mm, rows, [0.0] * columns)
    # Столбцы одинаковы, поэтому узор переносится на одну ячейку по X
    # и на породный цикл по Y.
    return Pattern(program, _periods(cell_mm, 1, len(species)), half_turn=False)


def checkerboard(
    species: Sequence[str], cell_mm: float, columns: int, rows: int
) -> Pattern:
    """Шахматка: две породы, каждый второй столбец сдвинут на ячейку."""
    shifts = [float(index % 2) for index in range(columns)]
    program = _single(species, cell_mm, rows, shifts)
    return Pattern(program, _periods(cell_mm, 2, len(species)))


def brick(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, width: int
) -> Pattern:
    """Кирпич: столбцы сдвигаются не по одному, а группами по `width`.

    Соседние столбцы с одинаковым сдвигом сливаются в один кирпич шириной
    `width` ячеек — именно так кладка и отличается от шахматки.
    """
    if width < 1:
        raise ValueError("кирпич не может быть уже одной ячейки")
    shifts = [float((index // width) % 2) for index in range(columns)]
    program = _single(species, cell_mm, rows, shifts)
    return Pattern(program, _periods(cell_mm, 2 * width, len(species)))


def diagonal(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, step: int
) -> Pattern:
    """Диагональ: сдвиг растёт на `step` ячеек от столбца к столбцу.

    Породы уезжают вверх ровной лесенкой; при `step`, взаимно простом с числом
    пород, диагональ получается непрерывной.
    """
    shifts = [float((index * step) % len(species)) for index in range(columns)]
    program = _single(species, cell_mm, rows, shifts)
    return Pattern(program, _periods(cell_mm, len(species), len(species)))


def zigzag(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, arm: int
) -> Pattern:
    """Зигзаг: сдвиг ходит вверх-вниз треугольной волной длиной `arm`.

    Ортогональный родственник шеврона: линии не наклоняются, а ступенчато
    поднимаются и опускаются. Отличие принципиальное — здесь нет ни одного
    углового реза, доска собирается из прямоугольников.
    """
    if arm < 1:
        raise ValueError("плечо зигзага должно быть хотя бы в одну ячейку")
    period = 2 * arm
    shifts = [
        float(min(index % period, period - index % period)) for index in range(columns)
    ]
    program = _single(species, cell_mm, rows, shifts)
    return Pattern(program, _periods(cell_mm, period, len(species)), half_turn=False)


def diamonds(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, arm: int
) -> Pattern:
    """Ромбы: тот же зигзаг, но по редкой породе-акценту в широком поле.

    Поле набирается одной породой, акцент — одной рейкой на цикл. Зигзаг
    акцента, повторённый через период, замыкается в сетку ромбов.
    """
    if len(species) < 2:
        raise ValueError("ромбам нужны поле и акцент — минимум две породы")
    field_species, accent = species[0], species[1]
    strips = tuple(
        accent if index % rows == 0 else field_species for index in range(rows * 2)
    )
    period = 2 * arm
    shifts = [
        float(min(index % period, period - index % period)) for index in range(columns)
    ]
    program = assemble_columns([strips], cell_mm, [(0, shift) for shift in shifts])
    return Pattern(program, _periods(cell_mm, period, rows))


def basket(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, width: int
) -> Pattern:
    """Плетёнка: два щита с разной фазой набора, блоками по `width` столбцов.

    Один сдвиг здесь не помогает: чтобы блоки читались как переплетение,
    соседние обязаны идти из наборов, сдвинутых друг относительно друга —
    это уже другой щит, а не другой сдвиг (Р9).
    """
    if width < 1:
        raise ValueError("блок плетёнки не может быть уже одной ячейки")
    half = max(1, len(species) // 2)
    billets = [_cycle(species, rows), _cycle(species, rows, start=half)]
    plan = [((index // width) % 2, 0.0) for index in range(columns)]
    program = assemble_columns(billets, cell_mm, plan)
    return Pattern(program, _periods(cell_mm, 2 * width, len(species)))


def pinstripe(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, gap: int
) -> Pattern:
    """Карандашная линия: широкое поле, редкая тонкая полоса чужой породы.

    Проверка на то, что узор — это не обязательно много цвета. Ячейка тонкой
    полосы вдвое уже поля, и валидатор Дня 3 обязан на этом не ругаться:
    порог косметический, а не защитный.
    """
    if len(species) < 2:
        raise ValueError("полосе нужны поле и акцент — минимум две породы")
    if gap < 2:
        raise ValueError("между линиями должно быть хотя бы две ячейки поля")
    strips = tuple(
        species[1] if index % gap == 0 else species[0] for index in range(rows)
    )
    program = assemble_columns([strips], cell_mm, [(0, 0.0) for _ in range(columns)])
    return Pattern(program, _periods(cell_mm, 1, gap))


def ladder(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, run: int
) -> Pattern:
    """Лесенка: сдвиг растёт `run` столбцов подряд и сбрасывается.

    От диагонали отличается разрывом: ступень доходит до верха и начинается
    заново, а не идёт через всю доску.
    """
    if run < 2:
        raise ValueError("ступень лесенки должна быть хотя бы в два столбца")
    shifts = [float(index % run) for index in range(columns)]
    program = _single(species, cell_mm, rows, shifts)
    return Pattern(
        program,
        _periods(cell_mm, run * len(species) // _gcd(run, len(species)), len(species)),
    )


def _gcd(first: int, second: int) -> int:
    while second:
        first, second = second, first % second
    return first


def windmill(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, arm: int
) -> Pattern:
    """Мельница: блоки по `arm` столбцов, развёрнутые через один.

    Единственный шаблон, где работает `reversed`: разворот столбца на 180°
    переставляет его ячейки по вертикали, и на стыке блоков породы идут
    навстречу друг другу.
    """
    if arm < 2:
        raise ValueError("крыло мельницы должно быть хотя бы в два столбца")
    shifts = [float((index // arm) % 2) for index in range(columns)]
    flags = [(index // arm) % 2 == 1 for index in range(columns)]
    program = _single(species, cell_mm, rows, shifts, flags)
    return Pattern(program, _periods(cell_mm, 2 * arm, len(species)))


def border(
    species: Sequence[str], cell_mm: float, columns: int, rows: int, thickness: int
) -> Pattern:
    """Рамка: поле в кайме из другой породы.

    Кайма по бокам — это крайние столбцы из щита каймы; кайма сверху и снизу —
    крайние рейки в наборе поля. Сдвигов нет вовсе, поэтому и обрезки нет:
    рамка обязана быть ровной по определению.
    """
    if thickness < 1:
        raise ValueError("кайма не может быть уже одной ячейки")
    if rows <= 2 * thickness or columns <= 2 * thickness:
        raise ValueError("кайма съедает доску целиком — возьми её тоньше")

    frame, inner = species[0], species[1 % len(species)]
    field_strips = tuple(
        frame if index < thickness or index >= rows - thickness else inner
        for index in range(rows)
    )
    program = assemble_columns(
        [field_strips, (frame,) * rows],
        cell_mm,
        [
            (1 if index < thickness or index >= columns - thickness else 0, 0.0)
            for index in range(columns)
        ],
    )
    return Pattern(program, half_turn=True)


def _striped_panel(species: Sequence[str], cell_mm: float, repeats: int) -> StripedPanel:
    return StripedPanel(
        species=tuple(species),
        strip_width_mm=cell_mm,
        board_height_mm=cell_mm,
        column_width_mm=cell_mm / 2,
        columns=12,
        repeats=repeats,
    )


def chevron_pattern(
    species: Sequence[str], cell_mm: float, angle_deg: float, repeats: int
) -> Pattern:
    """Шеврон: породные линии сходятся на швах в непрерывный зигзаг."""
    panel = _striped_panel(species, cell_mm, repeats)
    return Pattern(
        chevron(panel, angle_deg=angle_deg, step_mm=cell_mm, trim=3, square=True)
    )


def herringbone_pattern(
    species: Sequence[str], cell_mm: float, angle_deg: float, repeats: int
) -> Pattern:
    """Ёлочка: тот же рез и то же зеркало, зигзаг разорван на полшага."""
    panel = _striped_panel(species, cell_mm, repeats)
    return Pattern(
        herringbone(panel, angle_deg=angle_deg, step_mm=cell_mm, trim=3, square=True)
    )


def cube_pattern(species: Sequence[str], side_mm: float, columns: int) -> Pattern:
    """Кубы: мозаика «падающих блоков», два щита-близнеца (см. `cubes.py`)."""
    panel = CubePanel(
        species=(species[0], species[1], species[2]),
        side_mm=side_mm,
        columns=columns,
    )
    return Pattern(cubes(panel, square=True))


LIBRARY: dict[str, Template] = {
    template.key: template
    for template in (
        Template(
            "stripes",
            "Полосы",
            "Самый простой узор: сдвигов нет, порода меняется по высоте",
            stripes,
            {
                "species": ("maple_hard", "walnut_black", "cherry"),
                "cell_mm": 40.0,
                "columns": 12,
                "rows": 9,
            },
        ),
        Template(
            "checkerboard",
            "Шахматка",
            "Две породы, каждый второй столбец сдвинут на ячейку",
            checkerboard,
            {
                "species": ("maple_hard", "walnut_black"),
                "cell_mm": 40.0,
                "columns": 14,
                "rows": 10,
            },
        ),
        Template(
            "brick",
            "Кирпичная кладка",
            "Сдвиг группами: соседние столбцы сливаются в кирпич",
            brick,
            {
                "species": ("cherry", "hornbeam"),
                "cell_mm": 34.0,
                "columns": 15,
                "rows": 12,
                "width": 3,
            },
        ),
        Template(
            "diagonal",
            "Диагональ",
            "Сдвиг растёт от столбца к столбцу — породы уезжают лесенкой",
            diagonal,
            {
                "species": ("maple_hard", "cherry", "walnut_black"),
                "cell_mm": 36.0,
                "columns": 15,
                "rows": 12,
                "step": 1,
            },
        ),
        Template(
            "zigzag",
            "Зигзаг",
            "Треугольная волна сдвигов: шеврон без единого углового реза",
            zigzag,
            {
                "species": ("ash", "walnut_black", "cherry", "maple_hard"),
                "cell_mm": 32.0,
                "columns": 17,
                "rows": 14,
                "arm": 4,
            },
        ),
        Template(
            "diamonds",
            "Ромбы",
            "Зигзаг редкого акцента в широком поле замыкается в сетку",
            diamonds,
            {
                "species": ("maple_hard", "wenge"),
                "cell_mm": 30.0,
                "columns": 17,
                "rows": 5,
                "arm": 4,
            },
        ),
        Template(
            "basket",
            "Плетёнка",
            "Два щита с разной фазой набора, блоками через один",
            basket,
            {
                "species": ("oak", "walnut_black", "maple_hard", "cherry"),
                "cell_mm": 34.0,
                "columns": 16,
                "rows": 12,
                "width": 2,
            },
        ),
        Template(
            "pinstripe",
            "Карандашная линия",
            "Широкое поле и редкая тонкая полоса чужой породы",
            pinstripe,
            {
                "species": ("maple_hard", "wenge"),
                "cell_mm": 28.0,
                "columns": 14,
                "rows": 15,
                "gap": 5,
            },
        ),
        Template(
            "ladder",
            "Лесенка",
            "Ступень идёт вверх несколько столбцов и начинается заново",
            ladder,
            {
                "species": ("beech", "jatoba", "maple_hard"),
                "cell_mm": 34.0,
                "columns": 16,
                "rows": 12,
                "run": 4,
            },
        ),
        Template(
            "windmill",
            "Мельница",
            "Блоки, развёрнутые через один: породы идут навстречу",
            windmill,
            {
                "species": ("sapele", "maple_hard", "wenge"),
                "cell_mm": 34.0,
                "columns": 16,
                "rows": 12,
                "arm": 2,
            },
        ),
        Template(
            "border",
            "Рамка",
            "Поле в кайме из другой породы, без единого сдвига",
            border,
            {
                "species": ("wenge", "maple_hard"),
                "cell_mm": 34.0,
                "columns": 14,
                "rows": 12,
                "thickness": 1,
            },
        ),
        Template(
            "chevron",
            "Шеврон",
            "Угловой рез и зеркало: породные линии сходятся в непрерывный зигзаг",
            chevron_pattern,
            {
                "species": ("maple_hard", "walnut_black", "cherry"),
                "cell_mm": 36.0,
                "angle_deg": 45.0,
                "repeats": 6,
            },
        ),
        Template(
            "herringbone",
            "Ёлочка",
            "Тот же рез и то же зеркало, зигзаг разорван на полшага",
            herringbone_pattern,
            {
                "species": ("maple_hard", "walnut_black", "cherry"),
                "cell_mm": 36.0,
                "angle_deg": 45.0,
                "repeats": 6,
            },
        ),
        Template(
            "cubes",
            "Кубы",
            "Мозаика падающих блоков: два реза, два щита, объём из светотени",
            cube_pattern,
            {
                "species": ("maple_hard", "cherry", "walnut_black"),
                "side_mm": 40.0,
                "columns": 30,
            },
        ),
    )
}


def build(key: str, **overrides: Any) -> Pattern:
    """Собрать узор библиотеки по имени."""
    if key not in LIBRARY:
        raise ValueError(f"нет такого узора: {key!r}; есть {sorted(LIBRARY)}")
    return LIBRARY[key](**overrides)


__all__ = ["LIBRARY", "Pattern", "Template", "assemble_columns", "build"]
