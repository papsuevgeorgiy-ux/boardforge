"""Валидатор изготовимости: вопросы цеха, а не эстетики.

Тонкий клин уходит под диск при торцовке — это травма. Проверяем, что он
ловится, что мера ширины честная (габаритная рамка на наклонном клине врёт),
и что на здоровых досках валидатор молчит: замечание, которое горит всегда,
никто не читает.
"""

import math

import pytest
from shapely.geometry import Polygon

from boardforge.core import safety
from boardforge.core.ops import Assemble, Crosscut, Cut, Glue, PieceRef, StandOnEnd, Strip
from boardforge.core.patterns import StripedPanel, chevron
from boardforge.core.piece import Origin, Piece
from boardforge.core.program import Program

MAPLE, WALNUT, CHERRY = "maple_hard", "walnut_black", "cherry"


def _issues(program: Program, limits: safety.Limits | None = None):
    return safety.inspect(program, program.run(), limits)


def test_diagonal_wedge_is_not_measured_by_its_bounding_box() -> None:
    """Клин под 45° тонкий, а рамка у него большая. Меряем по-настоящему."""
    wedge = Piece(
        Polygon([(0.0, 0.0), (100.0, 100.0), (98.0, 102.0)]),
        Origin("A", 0, 0.0, MAPLE),
    )
    xmin, ymin, xmax, ymax = wedge.polygon.bounds
    assert min(xmax - xmin, ymax - ymin) > 90.0, "рамка считает клин широким"
    assert wedge.min_width_mm < 3.0


def test_min_angle_finds_the_sharp_corner() -> None:
    """Самый острый угол ячейки считается, а не берётся на глаз."""
    sliver = Piece(
        Polygon([(0.0, 0.0), (100.0, 0.0), (100.0, 10.0)]),
        Origin("A", 0, 0.0, MAPLE),
    )
    expected = math.degrees(math.atan2(10.0, 100.0))
    assert sliver.min_angle_deg == pytest.approx(expected, abs=0.01)


def _wedge_program(first_index: int = 0) -> Program:
    """Рез под 80°: крайняя полоса выходит клином с носом 10°, и её берут в щит."""
    picks = (PieceRef("P", first_index), PieceRef("P", 4), PieceRef("P", 5))
    return Program(
        operations=(
            Glue("A", (Strip(MAPLE, 60.0), Strip(WALNUT, 60.0)), 800.0, 40.0),
            Crosscut("A", 40.0),
            StandOnEnd("A"),
            Assemble(
                "P",
                tuple(PieceRef("A", index) for index in range(20)),
                (False,) * 20,
                (0.0,) * 20,
            ),
            Cut("P", 80.0, 40.0),
            Assemble("BOARD", picks, (False,) * 3, (0.0,) * 3),
        )
    )


def test_wedge_nose_is_an_error_with_the_cut_operation_number() -> None:
    """Клин — ошибка, и она указывает на рез, который его сделал."""
    program = _wedge_program()
    complaints = [issue for issue in _issues(program) if "клином" in issue.message]

    assert complaints, [str(i) for i in _issues(program)]
    assert all(issue.level == "error" for issue in complaints)
    assert all(isinstance(program.operations[i.index], Cut) for i in complaints)
    assert any("P#0" in issue.message for issue in complaints)
    assert "под диск" in complaints[0].message


def test_wedge_nose_angle_follows_the_cut_angle() -> None:
    """Нос клина равен `min(θ, 90°−θ)` — мера выведена, а не подобрана."""
    program = _wedge_program()
    wedge = program.run().billets["P"][0]
    assert wedge.outline_min_angle_deg == pytest.approx(10.0, abs=0.01)
    assert wedge.outline_min_width_mm > 20.0, "по ширине такой клин не поймать"


def test_only_used_parts_are_reported() -> None:
    """Жалуемся ровно на те детали, что идут в щит, а не на все нарезанные.

    Полоса, оставшаяся в отходе, руками не ведётся. Иначе список замечаний
    горит на каждом угловом узоре, и его перестают читать вместе с настоящими
    ошибками. При 80° клин выходит у каждой полосы, так что считать легко.
    """
    program = _wedge_program()
    produced = len(program.run().billets["P"])
    used = len(program.operations[-1].pieces)
    assert produced > used, "фикстура обязана резать больше, чем берёт"

    complaints = [issue for issue in _issues(program) if "клином" in issue.message]
    assert len(complaints) == used


def test_step_thinner_than_the_limit_is_an_error() -> None:
    """Слишком мелкий шаг реза — тонкая полоса по всей длине, это тоже ошибка."""
    program = Program(
        operations=(
            Glue("A", (Strip(MAPLE, 60.0), Strip(WALNUT, 60.0)), 400.0, 40.0),
            Crosscut("A", 40.0),
            StandOnEnd("A"),
            Assemble(
                "P",
                tuple(PieceRef("A", index) for index in range(10)),
                (False,) * 10,
                (0.0,) * 10,
            ),
            Cut("P", 90.0, 6.0),
            Assemble("BOARD", (PieceRef("P", 5),), (False,), (0.0,)),
        )
    )
    thin = [issue for issue in _issues(program) if "шириной" in issue.message]
    assert len(thin) == 1
    assert thin[0].level == "error"
    assert "6.0 мм" in thin[0].message


def test_tipping_ratio_is_reported_for_tall_narrow_sticks() -> None:
    """Высокий узкий брусок валится на столе — предупреждение с номером реза."""
    program = Program(
        operations=(
            Glue("A", (Strip(MAPLE, 60.0), Strip(CHERRY, 60.0)), 400.0, 40.0),
            Crosscut("A", 60.0),
            StandOnEnd("A"),
            Assemble(
                "P",
                tuple(PieceRef("A", index) for index in range(6)),
                (False,) * 6,
                (0.0,) * 6,
            ),
            Cut("P", 90.0, 15.0),
            Assemble(
                "BOARD",
                (PieceRef("P", 1), PieceRef("P", 2)),
                (False, False),
                (0.0, 0.0),
            ),
        )
    )
    tipping = [issue for issue in _issues(program) if "валится" in issue.message]

    assert len(tipping) == 1
    assert tipping[0].level == "warning"
    assert isinstance(program.operations[tipping[0].index], Cut)
    assert "4.0 к одному" in tipping[0].message


def test_healthy_chevron_has_no_safety_errors() -> None:
    """На нормальном шевроне опасного нет: `trim` в генераторе снимает клинья.

    Косметические замечания остаться могут — у самой кромки породная линия даёт
    волосок чужого цвета, — но ошибок быть не должно, иначе список перестают
    читать вместе с настоящими.
    """
    panel = StripedPanel(species=(MAPLE, WALNUT, CHERRY), columns=14, repeats=3)
    program = chevron(panel, angle_deg=45.0, step_mm=40.0)

    found = _issues(program)
    errors = [issue for issue in found if issue.level == "error"]
    assert not errors, [str(issue) for issue in errors]
    assert all("царапина" in issue.message for issue in found), [
        str(issue) for issue in found
    ]


def test_nose_sharpness_is_not_about_forty_five_degrees() -> None:
    """При 45° нос тупой, при 80° острый — порог ловит угол, а не «угловой рез»."""
    panel = StripedPanel(species=(MAPLE, WALNUT, CHERRY), columns=14, repeats=3)
    gentle = chevron(panel, angle_deg=45.0, step_mm=40.0, trim=0).run()
    steep = chevron(panel, angle_deg=80.0, step_mm=40.0, trim=0).run()

    assert gentle.billets["P"][0].outline_min_angle_deg == pytest.approx(45.0, abs=0.5)
    assert steep.billets["P"][0].outline_min_angle_deg == pytest.approx(10.0, abs=0.5)


def test_shallow_chevron_without_trim_is_caught() -> None:
    """Пологий рез с `trim=0` берёт остриё в щит — это обязано быть ошибкой.

    При 45° нос клина тоже 45°, и опасности нет: `min(θ, 90°−θ)` острым
    становится ближе к продольному резу. Поэтому проверяем на 80°.
    """
    panel = StripedPanel(species=(MAPLE, WALNUT, CHERRY), columns=14, repeats=3)
    program = chevron(panel, angle_deg=80.0, step_mm=40.0, trim=0)

    errors = [issue for issue in _issues(program) if issue.level == "error"]
    assert errors, "клинья на кромке прошли незамеченными"
    assert all(isinstance(program.operations[e.index], Cut) for e in errors)


def test_checkerboard_is_quiet(checkerboard: Program) -> None:
    """И на шахматке тоже: ортогональный узор клиньев не даёт."""
    assert not _issues(checkerboard), [str(i) for i in _issues(checkerboard)]


def test_limits_are_parameters_not_magic_numbers() -> None:
    """Порог можно поднять под свою мастерскую, и замечание появится."""
    panel = StripedPanel(species=(MAPLE, WALNUT, CHERRY), columns=14, repeats=3)
    program = chevron(panel, angle_deg=45.0, step_mm=40.0)

    strict = safety.Limits(min_part_width_mm=60.0)
    assert [issue for issue in _issues(program, strict) if "клином" in issue.message]

    with pytest.raises(ValueError, match="порог"):
        safety.Limits(min_angle_deg=0.0)
