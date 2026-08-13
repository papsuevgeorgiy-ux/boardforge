"""Обратная задача по габаритам (Р8).

Проверяется не формула, а свойство: программа переписана, размер достигнут
настолько, насколько он вообще достижим, и нигде не сохранён. Последнее важнее
всего — стоит завести поле «целевой размер», и появится второй источник истины,
который начнёт расходиться с операциями.
"""

import json

import pytest

from boardforge.core.fitting import FitError, fit_dimensions
from boardforge.core.ops import Glue
from boardforge.core.program import Program
from tests.helpers import build_checkerboard, build_two_panels


def board_of(program: Program):
    return program.apply()


def test_height_is_hit_exactly() -> None:
    """Высота — это шаг торцовки, она задаётся напрямую и попадает точно."""
    for height in (30.0, 38.0, 45.0):
        fit = fit_dimensions(build_checkerboard(), 400.0, 300.0, height)
        assert fit.achieved[2] == pytest.approx(height)


def test_the_program_is_rewritten_not_annotated() -> None:
    """Меняются параметры операций, а не приписка к программе."""
    before = build_checkerboard()
    fit = fit_dimensions(before, 400.0, 300.0, 40.0)

    assert fit.program is not before
    assert len(fit.program.operations) == len(before.operations)
    assert fit.program.errors == []

    glue_before = next(op for op in before.operations if isinstance(op, Glue))
    glue_after = next(op for op in fit.program.operations if isinstance(op, Glue))
    assert glue_after.strips != glue_before.strips or (
        glue_after.length_mm != glue_before.length_mm
    )


def test_target_is_not_stored_anywhere() -> None:
    """Целевой размер не переживает подбор: в JSON его нет."""
    fit = fit_dimensions(build_checkerboard(), 437.0, 311.0, 41.0)
    stored = json.dumps(fit.program.to_dict(), ensure_ascii=False)
    for trace in ("437", "311", "target", "desired"):
        assert trace not in stored


def test_achieved_size_is_measured_not_predicted() -> None:
    """Достигнутый размер меряется по собранной доске.

    Обрезка и остаток от торцовки съедают миллиметры, которых в формуле нет.
    Считать габарит вторым способом — верный способ показать пользователю не то,
    что он получит.
    """
    fit = fit_dimensions(build_checkerboard(), 400.0, 300.0, 40.0)
    board = board_of(fit.program)
    assert fit.achieved == (board.width_mm, board.length_mm, board.thickness_mm)


def test_search_beats_the_first_guess() -> None:
    """Подбор уточняется до тех пор, пока промах не перестанет уменьшаться.

    Эталонная шахматка обрезается на 40 мм сверху и снизу. Первая прикидка про
    обрезку не знает и промахивается на все 80; уточнение обязано её догнать.
    """
    fit = fit_dimensions(build_checkerboard(), 400.0, 300.0, 40.0)
    _, length_miss, _ = fit.deviation
    assert abs(length_miss) <= 40.0


def test_reachable_size_is_hit_exactly() -> None:
    """Достижимый габарит берётся точно, и об этом говорит `exact`."""
    fit = fit_dimensions(build_checkerboard(), 1000.0, 600.0, 50.0)
    assert fit.exact
    assert fit.deviation == pytest.approx((0.0, 0.0, 0.0))


def test_unreachable_size_reports_the_miss() -> None:
    """Недостижимый габарит не подгоняется молча."""
    fit = fit_dimensions(build_checkerboard(), 417.0, 313.0, 37.0)
    assert not fit.exact
    assert any(abs(value) > 0.05 for value in fit.deviation)
    assert max(abs(value) for value in fit.deviation) < 60.0


def test_strip_widths_are_not_stretched() -> None:
    """Ширины реек не подгоняются под миллиметр: меняется их количество.

    Столяр покупает рейку в размер. Растянуть 40 мм до 37.4 ради круглого
    габарита — это придумать материал, которого в мастерской нет.
    """
    before = build_checkerboard()
    widths_before = {
        s.width_mm for op in before.operations if isinstance(op, Glue) for s in op.strips
    }
    fit = fit_dimensions(before, 433.0, 297.0, 40.0)
    widths_after = {
        s.width_mm
        for op in fit.program.operations
        if isinstance(op, Glue)
        for s in op.strips
    }
    assert widths_after <= widths_before


def test_species_pattern_survives() -> None:
    """Последовательность пород повторяется по кругу, а не теряется."""
    fit = fit_dimensions(build_checkerboard(), 400.0, 500.0, 40.0)
    glue = next(op for op in fit.program.operations if isinstance(op, Glue))
    species = [strip.species for strip in glue.strips]
    assert set(species) == {"maple_hard", "walnut_black"}
    assert species[0] != species[1]


def test_multi_billet_program_is_refused() -> None:
    """Сложная программа отклоняется словами, а не молча портится."""
    with pytest.raises(FitError, match="простую доску"):
        fit_dimensions(build_two_panels(), 400.0, 300.0, 40.0)


def test_nonsense_sizes_are_refused() -> None:
    """Ноль и отрицательный размер — ошибка вызова."""
    for size in ((0.0, 300.0, 40.0), (400.0, -1.0, 40.0), (400.0, 300.0, 0.0)):
        with pytest.raises(FitError, match="положительной"):
            fit_dimensions(build_checkerboard(), *size)


def test_fitting_is_deterministic() -> None:
    """Тот же запрос — та же программа: подбор не гадает."""
    first = fit_dimensions(build_checkerboard(), 421.0, 307.0, 39.0)
    second = fit_dimensions(build_checkerboard(), 421.0, 307.0, 39.0)
    assert first.program.to_dict() == second.program.to_dict()
    assert first.achieved == second.achieved
