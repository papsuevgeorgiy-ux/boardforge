"""Кубы: мозаика «падающих блоков» с волосяной линией на каждой грани (Р22).

Долг Дня 3. Р22 закрыл бесшовный вариант и оставил открытым этот; здесь он
строится — но не так, как Р22 предполагал, и это главное, что стоит прочитать
до правок.

## Что подтвердилось

Три сквозных семейства под 60°: породные линии (30°), швы первого реза (150°)
и швы второго (90°). Каждое из них режет пополам грани **одного** из трёх
направлений и совпадает с рёбрами двух других — отсюда «волосяная линия по
телу каждой грани, обе половины одного цвета». Шаг всех трёх одинаков и равен
`A·√3/2`, где `A` — сторона ромба.

## Что оказалось не так

Р22 считал, что доска строится из одного щита. **Из одного не строится
никогда, ни при каких сдвигах** — это арифметика, а не неудачный перебор.

Пусть `b` — номер полосы последнего реза, `c` — номер полосы первого,
`s(b,c)` — номер породной полосы в ячейке. Мозаика требует, чтобы `s` зависела
только от класса `(2c − b) mod 3`. Сдвиг полосы последнего реза двигает
и породные линии, и швы первого реза **на одну и ту же величину**, поэтому
фаза первого реза входит в `s` не сама по себе, а вместе с фазой второго.
Выписав это, получаем условие на период набора реек `P`:

    f(t + e) = f(t) + 3   (mod P),   e ∈ ℤ/3

Применив три раза: `f(t) = f(t) + 9`, то есть `P` делит 9. Период 3 не даёт
трёх пород (в классе `(2c−b) ≡ 0` соседние полосы обязаны быть одной породы,
и на три породы полос не остаётся), период 9 не проходит уравнение для `b = 1`.
Значит подходящего набора реек нет вовсе.

## Что строится

Два щита-близнеца, набранные **одним и тем же** циклом, но со сдвигом набора
на одну рейку. Полосы последнего реза берутся из них через одну. Разница
в одну рейку и есть та степень свободы, которой не хватало: сдвигом её
не получить — глобальный сдвиг всех полос склейка гасит при нормализации,
а разный набор щита живёт в самом щите.

Ровно та ситуация, ради которой заведён мульти-щит (Р9): «ряд N не выводится
из щита А, нужен щит Б» — впервые не гипотетически.

Цена: из каждого щита в доску идёт половина полос. Вторая половина — не отход,
а комплект на вторую такую же доску с переставленными местами породами;
в смете Дня 5 это должно быть видно именно так.
"""

import math
from dataclasses import dataclass

from .color import hex_to_lab, lightness_spread
from .lattice import LineFamily, ShiftGrid, common_quantum
from .ops import Assemble, Crop, Crosscut, Cut, Glue, PieceRef, StandOnEnd, Strip
from .patterns import squared
from .program import Issue, Program
from .species import Species

CUT_FIRST_DEG = 30.0
CUT_SECOND_DEG = 120.0
"""Два реза под 30° и 120°. Вместе с вертикалью последней склейки дают
три направления под 60° — равностороннюю разбивку, других вариантов нет."""

STRIP_CYCLE = (0, 0, 2, 1, 1, 2)
"""Набор реек периода шесть: породы 0 и 1 идут парами, порода 2 — поодиночке.

Пара — это и есть грань, разрезанная волосяной линией пополам: обе половины
одной породы. Одиночные рейки достаются граням, которые режут другие два
семейства. Набор выведен из условия на мозаику, а не подобран.
"""

SECOND_PANEL_ROTATION = 1
"""На сколько реек сдвинут набор второго щита. Нечётное — существенно:
именно нечётность даёт недостающую степень свободы (см. заголовок модуля)."""

MIN_LIGHTNESS_SPREAD = 12.0
"""Наименьшая разница светлоты пород, при которой объём ещё читается, ΔL*.

Кубы — единственный узор проекта, который держится не на рисунке, а на
светотени: три грани одного «кубика» отличаются только тоном. Породы
одинаковой светлоты дают не кубы, а шестиугольную плитку.
"""

_FIRST = "A"
_SECOND = "B"
_BOARD = "BOARD"


def _plan(billet: str) -> str:
    return f"P{billet}"


def _glued(billet: str) -> str:
    return f"G{billet}"


@dataclass(frozen=True, slots=True)
class CubePanel:
    """Заготовка под кубы. Толщина щита не задаётся — она следствие стороны.

    `species` — три породы по граням: верхняя, левая, правая. Порядок влияет
    на то, какая грань окажется светлой, то есть куда «падает свет».
    """

    species: tuple[str, str, str]
    side_mm: float = 40.0
    board_height_mm: float = 40.0
    columns: int = 30
    repeats: int = 4
    """Пропорции щита — не вкус, а условие на то, чтобы полосы вышли полной
    длины и цельными. Оба реза идут наискось, и каждый съедает у щита
    `длина · tg 30°` ширины; чтобы после двух резов осталась доска, а не лента,
    ширина щита должна быть примерно в полтора раза больше его длины в плане.
    По умолчанию так и есть: 30 столбцов против 24 реек, обе меры в шагах
    `A√3/2`. Отсюда и расход: доска 381 × 321 требует двух щитов 1039 × 831,
    и это честная цена двух угловых резов."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "species", tuple(self.species))
        if len(self.species) != 3:
            raise ValueError("кубам нужны ровно три породы — по одной на грань")
        if len(set(self.species)) != 3:
            raise ValueError(
                "три грани куба обязаны быть разными породами: с повтором "
                "две грани сливаются, и объёма не видно"
            )
        if self.side_mm <= 0:
            raise ValueError("сторона ромба должна быть положительной")
        if self.board_height_mm <= 0:
            raise ValueError("высота доски должна быть положительной")
        if self.columns < 1:
            raise ValueError("в щите должен быть хотя бы один столбец")
        if self.repeats < 2:
            raise ValueError(
                "породный цикл должен повториться хотя бы дважды: сдвиг полосы "
                "переносится на период узора, и переносить его должно быть на что"
            )

    @property
    def thickness_mm(self) -> float:
        """Толщина щита. Условие Р22: `A·√3/2`, и оно не настройка, а вывод.

        Шаг всех трёх семейств линий равен `A·√3/2`; толщина щита задаёт шаг
        волосяных швов между столбцами первой склейки — четвёртого семейства,
        невидимого, но существующего. Равенство шагов делает его неотличимым
        от остальных по частоте, то есть наименее заметным.
        """
        return self.side_mm * math.sqrt(3) / 2

    @property
    def strip_width_mm(self) -> float:
        """Ширина рейки — тот же шаг: породные линии обязаны лечь на решётку."""
        return self.thickness_mm

    @property
    def cut_step_mm(self) -> float:
        """Шаг обоих резов. Он же шаг семейств линий."""
        return self.thickness_mm

    @property
    def strips(self) -> tuple[str, ...]:
        """Набор реек одного цикла: шесть штук по `STRIP_CYCLE`."""
        return tuple(self.species[index] for index in STRIP_CYCLE)

    def shift_grid(self) -> ShiftGrid:
        """Сетка сдвигов: шаг из решётки, размер — период набора реек.

        Здесь и живут «два условия вместо одного». Сдвиг полосы второго реза
        обязан оставить сквозными **и** породные линии, **и** швы первого
        реза; общий шаг ищется как согласование двух шагов, и если бы они
        оказались несоизмеримы, `common_quantum` сказал бы это словами.
        """
        pitch = self.strip_width_mm
        # Углы в системе координат щита перед вторым резом: породные линии
        # развернулись на угол первого реза, швы первого реза вертикальны.
        species_lines = LineFamily(direction_deg=-CUT_FIRST_DEG, pitch_mm=pitch)
        first_seams = LineFamily(direction_deg=90.0, pitch_mm=self.cut_step_mm)
        axis = 90.0 + CUT_SECOND_DEG
        quantum = common_quantum(
            (
                species_lines.shift_quantum(axis),
                first_seams.shift_quantum(axis),
            ),
            "кубы",
        )
        return ShiftGrid(quantum_mm=quantum, size=len(STRIP_CYCLE))


def _panel_operations(panel: CubePanel, billet: str, rotation: int) -> list[object]:
    """Щит, торцовка, постановка на торец и первая склейка в столбцы."""
    order = panel.strips[rotation:] + panel.strips[:rotation]
    strips = tuple(
        Strip(name, panel.strip_width_mm) for _ in range(panel.repeats) for name in order
    )
    return [
        Glue(
            id=billet,
            strips=strips,
            length_mm=panel.board_height_mm * panel.columns,
            thickness_mm=panel.thickness_mm,
        ),
        Crosscut(source=billet, step_mm=panel.board_height_mm),
        StandOnEnd(source=billet),
        Assemble(
            id=_plan(billet),
            pieces=tuple(PieceRef(billet, index) for index in range(panel.columns)),
            reversed=(False,) * panel.columns,
            offsets_mm=(0.0,) * panel.columns,
        ),
    ]


FULL_LENGTH_RATIO = 0.9
"""Какой долей от самой длинной полосы должна быть полоса, чтобы пойти в дело.

Отбраковка по счёту («три с каждого края», как у шеврона) на кубах не годится.
Рез под 30° к кромке идёт через прямоугольник наискось, и длина полосы падает
к краям не на трёх последних, а на трети щита. Сколько именно — зависит от
пропорций щита, поэтому число не назначается, а меряется.
"""


def _placements(
    program: Program, angle_deg: float, step_mm: float
) -> tuple[list[float], list[tuple[float, bool]]]:
    """Сдвиги «полоса на своё место» и мера годности каждой полосы.

    Меряется исполнением, как и у шеврона (Р18): формула не знает про клинья
    на краях щита, из-за которых нормализация у полос разная.

    Годность — пара «длина, цельность». Одной длины мало: полоса, прошедшая
    вдоль рваного края щита, выходит длинной, но разваливается на куски
    с дырами между ними. Взять её в щит значит собрать доску с дырой.
    """
    from . import geometry

    sliced = geometry.slice_part(program.run().board, angle_deg, step_mm)
    base = sliced.placements_mm[0][1]
    return (
        [y - base for _, y in sliced.placements_mm],
        [(part.length_mm, _is_solid(part)) for part in sliced.parts],
    )


def _is_solid(part) -> bool:  # type: ignore[no-untyped-def]
    """Один ли кусок эта полоса и нет ли в ней дыр.

    Проверяется по контуру, а не по числу ячеек: ячеек в полосе десятки,
    и они обязаны быть склеены между собой. Разъехались — это уже не деталь.
    """
    # Считаем куски, а не сравниваем тип: округление контура нередко отдаёт
    # `MultiPolygon` из одного полигона, и это цельная деталь, а не россыпь.
    shapes = list(getattr(part.outline, "geoms", [part.outline]))
    return len(shapes) == 1 and not shapes[0].interiors


def _full_length_bands(fitness: list[tuple[float, bool]], margin: int) -> range:
    """Самый длинный подряд идущий кусок полос, годных в дело.

    Подряд идущий — не придирка: полосы кладутся встык, и выбросить полосу
    из середины значит порвать доску. Либо кусок целиком, либо ничего.
    """
    if not fitness:
        return range(0)
    threshold = max(length for length, _ in fitness) * FULL_LENGTH_RATIO

    def usable(item: tuple[float, bool]) -> bool:
        length, solid = item
        return solid and length >= threshold

    best = (0, 0)
    start: int | None = None
    for index, item in enumerate([*fitness, (0.0, False)]):
        if usable(item) and start is None:
            start = index
        elif not usable(item) and start is not None:
            if index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    return range(best[0] + margin, best[1] - margin)


def _first_glue_up(
    panel: CubePanel, billet: str, rotation: int, trim: int
) -> tuple[list[object], range]:
    """Первый угловой рез и склейка: фаза растёт на три полосы за шаг."""
    operations = _panel_operations(panel, billet, rotation)
    places, fitness = _placements(
        Program(operations=tuple(operations)), CUT_FIRST_DEG, panel.cut_step_mm
    )
    grid = panel.shift_grid()
    usable = _full_length_bands(fitness, trim)
    if len(usable) < 3:
        raise ValueError(
            f"полос, годных в дело, осталось {len(usable)} из {len(fitness)} — "
            f"щиту не хватает ширины на рез под {CUT_FIRST_DEG:.0f}°. "
            f"Возьми больше столбцов или меньше повторов породного цикла"
        )
    offsets = tuple(
        grid.wrapped(places[index] + grid.offset(3 * slot))
        for slot, index in enumerate(usable)
    )
    operations += [
        Cut(source=_plan(billet), angle_deg=CUT_FIRST_DEG, step_mm=panel.cut_step_mm),
        Assemble(
            id=_glued(billet),
            pieces=tuple(PieceRef(_plan(billet), index) for index in usable),
            reversed=(False,) * len(offsets),
            offsets_mm=offsets,
        ),
    ]
    # Обрезка **до** второго реза, а не после. Сдвиги оставляют щит с пилой
    # по краю; полоса, отпиленная от такого щита под углом, выходит с выкусом,
    # а в готовой доске на его месте дыра. В цехе щит между склейками тоже
    # равняют — иначе к нему не приложить упор.
    #
    # Срезается ровно зуб пилы, а не всё до прямоугольника: рез под 30°
    # оставляет щит параллелограммом, и обрезка до прямоугольника здесь съела
    # бы почти всё. Скошенные кромки второму резу не мешают — мешают выкусы.
    operations.append(
        Crop(
            source=_glued(billet),
            top=grid.period_mm / 2,
            bottom=grid.period_mm / 2,
        )
    )
    return operations, usable


def cubes(panel: CubePanel, trim: int = 1, square: bool = False) -> Program:
    """Программа доски «падающие блоки».

    `trim` — запас сверх отбраковки по длине: сколько полос выбросить ещё
    с каждого края уже отобранного куска. `square` — дописать обрезку до
    прямоугольника; по умолчанию нет, обрезка дизайнерская (Р5).
    """
    first, _ = _first_glue_up(panel, _FIRST, 0, trim)
    second, _ = _first_glue_up(panel, _SECOND, SECOND_PANEL_ROTATION, trim)
    shared = first + second

    places, fitness = _placements(
        Program(operations=tuple(first)), CUT_SECOND_DEG, panel.cut_step_mm
    )
    grid = panel.shift_grid()
    usable = _full_length_bands(fitness, trim)
    if len(usable) < 4:
        raise ValueError(
            f"полос, годных в дело, осталось {len(usable)} из {len(fitness)} — "
            f"щиту не хватает высоты на второй рез. Возьми больше повторов "
            f"породного цикла или меньше столбцов"
        )

    pieces: list[PieceRef] = []
    offsets: list[float] = []
    for slot, index in enumerate(usable):
        # Полосы берутся из щитов через одну: соседним столбцам нужна фаза,
        # отличающаяся на нечётное число реек, а сдвигом её не получить.
        source = _glued(_SECOND if slot % 2 == 0 else _FIRST)
        pieces.append(PieceRef(source, index))
        # Фаза меняется раз в две полосы — пара «щит А + щит Б» закрывает период
        # мозаики по горизонтали — и пробегает три значения, а не шесть: шаг
        # сдвига двигает породные линии и швы первого реза вместе, и полный
        # период набора реек так не набирается.
        phase = (2 * (slot // 2)) % 3
        offsets.append(grid.wrapped(places[index] + grid.quantum_mm * phase))

    program = Program(
        operations=(
            *shared,
            Cut(
                source=_glued(_FIRST),
                angle_deg=CUT_SECOND_DEG,
                step_mm=panel.cut_step_mm,
            ),
            Cut(
                source=_glued(_SECOND),
                angle_deg=CUT_SECOND_DEG,
                step_mm=panel.cut_step_mm,
            ),
            Assemble(
                id=_BOARD,
                pieces=tuple(pieces),
                reversed=(False,) * len(pieces),
                offsets_mm=tuple(offsets),
            ),
        )
    )
    return squared(program) if square else program


def tone_issues(panel: CubePanel, catalogue: dict[str, Species]) -> list[Issue]:
    """Хватает ли породам разницы в тоне, чтобы объём читался.

    Проверка не геометрическая и потому живёт не в валидаторе программы:
    из одной и той же программы с другим справочником пород выйдет и куб,
    и плоская шестиугольная плитка.
    """
    missing = [key for key in panel.species if key not in catalogue]
    if missing:
        return [Issue("error", f"породы нет в справочнике: {', '.join(sorted(missing))}")]

    colors = [catalogue[key].color for key in panel.species]
    spread = lightness_spread(colors)
    if spread >= MIN_LIGHTNESS_SPREAD:
        return []

    order = sorted(
        panel.species, key=lambda key: hex_to_lab(catalogue[key].color).lightness
    )
    names = [catalogue[key].name for key in order]
    return [
        Issue(
            "warning",
            f"светлота пород различается всего на {spread:.0f} единиц ΔL* при "
            f"пороге {MIN_LIGHTNESS_SPREAD:.0f} — ближе всех {names[0]} "
            f"и {names[1]}. Кубы держатся не на рисунке, а на светотени: "
            f"три грани одного блока отличаются только тоном. С такими "
            f"породами выйдет не объём, а шестиугольная плитка — возьми "
            f"светлую, среднюю и тёмную",
        )
    ]


__all__ = [
    "CUT_FIRST_DEG",
    "CUT_SECOND_DEG",
    "MIN_LIGHTNESS_SPREAD",
    "STRIP_CYCLE",
    "CubePanel",
    "cubes",
    "tone_issues",
]
