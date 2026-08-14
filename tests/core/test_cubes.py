"""Кубы: сверка с эталонной мозаикой, построенной независимо от ядра.

Проверять кубы «на глаз по превью» нельзя — почти правильная раскладка выглядит
почти правильно. Поэтому эталон строится здесь заново, из проекции кубической
решётки, и доска сверяется с ним породой в точке.
"""

import math

import pytest
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

from boardforge.core.cubes import (
    CUT_FIRST_DEG,
    CUT_SECOND_DEG,
    MIN_LIGHTNESS_SPREAD,
    CubePanel,
    cubes,
    tone_issues,
)
from boardforge.core.ops import Cut, Glue
from boardforge.core.piece import Part
from boardforge.core.species import load_species

SIDE_MM = 40.0
SPECIES = ("maple_hard", "walnut_black", "cherry")


def _panel(**overrides: object) -> CubePanel:
    values: dict[str, object] = {"species": SPECIES, "side_mm": SIDE_MM}
    values.update(overrides)
    return CubePanel(**values)  # type: ignore[arg-type]


def _colour_lattice(side_mm: float) -> tuple[tuple[float, float], ...]:
    """Трансляции, переводящие мозаику кубов в себя вместе с раскраской.

    Не всякий перенос годится: сдвиг на одну сторону ромба переставляет грани
    местами. Годятся переносы решётки кубов вдоль плоскости `x+y+z=0`.
    """
    return (
        (side_mm * math.sqrt(3), 0.0),
        (side_mm * math.sqrt(3) / 2, 1.5 * side_mm),
    )


def _samples(board: Part, margin_mm: float, steps: int = 22):
    xmin, ymin, xmax, ymax = board.bounds
    for i in range(steps):
        for j in range(steps):
            x = xmin + margin_mm + (xmax - xmin - 2 * margin_mm) * i / (steps - 1)
            y = ymin + margin_mm + (ymax - ymin - 2 * margin_mm) * j / (steps - 1)
            yield x, y


def test_program_is_legal_and_runs() -> None:
    """Сначала — что это вообще программа: валидатор молчит, доска собирается."""
    program = cubes(_panel())
    assert not program.errors, [str(issue) for issue in program.errors]

    board = program.run().board
    assert len(board.pieces) > 300
    assert board.width_mm > 300 and board.length_mm > 300
    assert not cubes(_panel(), square=True).errors


def test_two_billets_are_glued_from_the_same_cycle_shifted_by_one_strip() -> None:
    """Щита два, набор один и тот же, сдвинут на рейку — в этом весь фокус."""
    program = cubes(_panel())
    glues = [op for op in program.operations if isinstance(op, Glue)]
    assert len(glues) == 2, "из одного щита кубы не строятся, см. заголовок модуля"

    first = [strip.species for strip in glues[0].strips]
    second = [strip.species for strip in glues[1].strips]
    assert sorted(first) == sorted(second), "щиты обязаны быть из одного набора"
    assert first != second, "а сдвиг набора обязан быть — иначе щиты одинаковы"
    assert second == first[1:] + first[:1]


def test_thickness_follows_from_the_side() -> None:
    """Р22: толщина щита не настройка, а `A·√3/2`."""
    panel = _panel()
    assert panel.thickness_mm == pytest.approx(SIDE_MM * math.sqrt(3) / 2)

    glue = next(op for op in cubes(panel).operations if isinstance(op, Glue))
    assert glue.thickness_mm == pytest.approx(panel.thickness_mm)
    for strip in glue.strips:
        assert strip.width_mm == pytest.approx(panel.thickness_mm)


def test_three_through_families_at_sixty_degrees() -> None:
    """Два реза под 30° и 120°; вместе с вертикалью склейки — разбивка под 60°."""
    angles = [op.angle_deg for op in cubes(_panel()).operations if isinstance(op, Cut)]
    # По одному первому резу на каждый щит-близнец и по одному второму.
    assert angles == [CUT_FIRST_DEG, CUT_FIRST_DEG, CUT_SECOND_DEG, CUT_SECOND_DEG]

    # Направления семейств в готовой доске: породные линии, швы первого реза,
    # швы последней склейки. Попарные углы — по 60°.
    families = sorted(
        {
            (-CUT_FIRST_DEG - CUT_SECOND_DEG) % 180,
            (90 - CUT_SECOND_DEG) % 180,
            90.0,
        }
    )
    assert families == [30.0, 90.0, 150.0]


def test_pattern_is_invariant_under_the_tumbling_block_lattice() -> None:
    """Породы совпадают со сдвигом на вектор решётки кубов — во всех пробах.

    Это и есть проверка мозаики: любая «почти сошедшаяся» раскладка ломает
    инвариантность на большой доле проб, а не на единицах.
    """
    board = cubes(_panel(), square=True).run().board
    checked = matched = 0
    for x, y in _samples(board, margin_mm=1.2 * SIDE_MM):
        here = board.species_at(x, y)
        if here is None:
            continue
        for dx, dy in _colour_lattice(SIDE_MM):
            there = board.species_at(x + dx, y + dy)
            if there is None:
                continue
            checked += 1
            matched += here == there

    assert checked > 400, f"проб слишком мало ({checked}), тест ничего не ловит"
    assert matched == checked, f"разошлось {checked - matched} проб из {checked}"


def _reference_faces(side_mm: float, span: int = 10):
    """Эталонная мозаика: три видимые грани каждого куба, x+y+z=0."""
    scale = side_mm
    e1 = (math.sqrt(3) / 2 * scale, 0.5 * scale)
    e2 = (-math.sqrt(3) / 2 * scale, 0.5 * scale)
    e3 = (0.0, -scale)

    def project(x: int, y: int, z: int) -> tuple[float, float]:
        return ((x - y) * math.sqrt(3) / 2 * scale, ((x + y) / 2 - z) * scale)

    def rhombus(corner, first, second):
        return Polygon(
            [
                corner,
                (corner[0] + first[0], corner[1] + first[1]),
                (corner[0] + first[0] + second[0], corner[1] + first[1] + second[1]),
                (corner[0] + second[0], corner[1] + second[1]),
            ]
        )

    faces, kinds = [], []
    for x in range(-span, span + 1):
        for y in range(-span, span + 1):
            base = project(x, y, -x - y)
            faces.append(rhombus(project(x, y, -x - y + 1), e1, e2))
            kinds.append("top")
            faces.append(rhombus((base[0] + e1[0], base[1] + e1[1]), e2, e3))
            kinds.append("left")
            faces.append(rhombus((base[0] + e2[0], base[1] + e2[1]), e1, e3))
            kinds.append("right")
    return faces, kinds


def test_board_matches_the_reference_mosaic_face_for_face() -> None:
    """Сверка с эталоном: каждой породе доски отвечает одно направление грани.

    Соответствие не задаётся, а выводится из одной пробы и дальше обязано
    держаться везде — иначе это не мозаика кубов, а что-то на неё похожее.
    """
    board = cubes(_panel(), square=True).run().board
    faces, kinds = _reference_faces(SIDE_MM)
    tree = STRtree(faces)

    edge_mm = 2.0
    """Полоса вдоль рёбер эталона, где проба ничего не значит.

    Совмещение доски с эталоном ищется перебором и попадает в цель с точностью
    до десятой миллиметра. Проба в двух миллиметрах от ребра ромба от такого
    промаха не зависит, проба на самом ребре — целиком от него. Исключив
    рёбра, можно требовать точного совпадения, а не «почти»: так тест ловит
    съехавшую фазу, а не собственную грубость.
    """

    def kind_at(x: float, y: float) -> str | None:
        probe = Point(x, y)
        for index in tree.query(probe):
            face = faces[index]
            if face.covers(probe):
                return kinds[index] if face.exterior.distance(probe) > edge_mm else None
        return None

    # Эталон и доска стоят в разных началах координат: совмещаем по одной пробе.
    points = [
        (x, y)
        for x, y in _samples(board, margin_mm=1.2 * SIDE_MM, steps=26)
        if board.species_at(x, y) is not None
    ]
    assert len(points) > 300
    anchor = points[len(points) // 2]

    species_at = [(x, y, board.species_at(x, y)) for x, y in points]

    def score(shift: tuple[float, float]) -> tuple[float, dict[str, str]]:
        """Доля совпавших проб при данном совмещении и само соответствие.

        Доля, а не «всё или ничего»: проба, попавшая ровно на ребро ромба,
        про узор не говорит ничего. Соответствие «порода → грань» выводится
        большинством, а потом им же и проверяется.
        """
        tally: dict[tuple[str, str], int] = {}
        for x, y, species in species_at:
            kind = kind_at(x - anchor[0] + shift[0], y - anchor[1] + shift[1])
            if kind is not None and species is not None:
                tally[(species, kind)] = tally.get((species, kind), 0) + 1
        if not tally:
            return 0.0, {}
        mapping: dict[str, str] = {}
        for species, kind in sorted(tally, key=lambda key: -tally[key]):
            if species not in mapping and kind not in mapping.values():
                mapping[species] = kind
        agreed = sum(count for (s, k), count in tally.items() if mapping.get(s) == k)
        return agreed / sum(tally.values()), mapping

    # Эталон периодичен, поэтому достаточно перебрать сдвиги внутри одной ячейки
    # его решётки — а потом уточнить: на грубой сетке промах в пару миллиметров
    # даёт несколько процентов расхождения на одних только рёбрах.
    steps = (SIDE_MM * math.sqrt(3) / 12, 1.5 * SIDE_MM / 12)
    best = (0.0, {}, (0.0, 0.0))
    for i in range(12):
        for j in range(12):
            shift = (steps[0] * i, steps[1] * j)
            share, mapping = score(shift)
            if len(mapping) == 3 and share > best[0]:
                best = (share, mapping, shift)

    for _ in range(3):
        steps = (steps[0] / 4, steps[1] / 4)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                shift = (best[2][0] + steps[0] * di, best[2][1] + steps[1] * dj)
                share, mapping = score(shift)
                if len(mapping) == 3 and share > best[0]:
                    best = (share, mapping, shift)

    assert best[1], "ни при одном совмещении доска не легла на эталон"
    assert best[0] == 1.0, f"совпало {best[0]:.1%} проб — это не мозаика кубов"
    assert sorted(best[1].values()) == ["left", "right", "top"]


def test_species_share_the_board_equally() -> None:
    """Три грани — три равные доли площади. Перекос значит съехавшую фазу."""
    board = cubes(_panel()).run().board
    areas: dict[str, float] = {}
    for piece in board.pieces:
        areas[piece.species] = areas.get(piece.species, 0.0) + piece.area_mm2

    total = sum(areas.values())
    assert set(areas) == set(SPECIES)
    for key, value in areas.items():
        assert value / total == pytest.approx(1 / 3, abs=0.04), (key, areas)


def test_repeated_species_are_refused_outright() -> None:
    """Две одинаковые грани — не кубы, и это отказ, а не предупреждение."""
    with pytest.raises(ValueError, match="разными породами"):
        CubePanel(species=("oak", "oak", "wenge"))


def test_close_tones_are_reported_as_a_warning() -> None:
    """Близкие по светлоте породы — предупреждение с объяснением, не запрет."""
    catalogue = load_species()
    issues = tone_issues(_panel(species=("oak", "beech", "hornbeam")), catalogue)

    assert len(issues) == 1
    assert issues[0].level == "warning"
    assert "светотени" in issues[0].message
    assert "плитка" in issues[0].message


def test_contrasting_tones_pass_without_a_word() -> None:
    """На здоровом наборе замечание молчит — иначе оно ничего не значит."""
    assert tone_issues(_panel(), load_species()) == []


def test_the_tone_threshold_is_the_thing_being_tested() -> None:
    """Порог берётся из модуля, а не переписывается тестом под результат."""
    catalogue = load_species()
    from boardforge.core.color import lightness_spread

    good = lightness_spread([catalogue[key].color for key in SPECIES])
    assert good >= MIN_LIGHTNESS_SPREAD

    bad = lightness_spread([catalogue[key].color for key in ("oak", "beech", "hornbeam")])
    assert bad < MIN_LIGHTNESS_SPREAD


def test_missing_species_is_an_error_not_a_warning() -> None:
    issues = tone_issues(_panel(species=("maple_hard", "walnut_black", "ipe")), {})
    assert [issue.level for issue in issues] == ["error"]


def test_squared_board_is_a_rectangle() -> None:
    """Обрезка до прямоугольника доезжает и на кубах — щит после склейки рваный."""
    board = cubes(_panel(), square=True).run().board
    xmin, ymin, xmax, ymax = board.bounds
    area = sum(piece.area_mm2 for piece in board.pieces)
    assert area == pytest.approx((xmax - xmin) * (ymax - ymin), rel=1e-3)


def test_too_much_trim_says_so() -> None:
    """Отбраковать больше, чем есть полос, — внятный отказ, а не пустой щит."""
    with pytest.raises(ValueError, match="не хватает ширины"):
        cubes(_panel(columns=3), trim=40)
