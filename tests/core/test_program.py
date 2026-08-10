"""Валидатор последовательности и исполнение программы целиком."""

import json

import pytest

from boardforge.core.ops import (
    Assemble,
    Crosscut,
    Cut,
    Glue,
    StandOnEnd,
    Strip,
)
from boardforge.core.program import Program, ProgramError, program
from tests.helpers import CELL_MM, MAPLE, ROW_COUNT, STRIP_COUNT, WALNUT

SIMPLE_GLUE = Glue((Strip(MAPLE, 40.0), Strip(WALNUT, 40.0)), 600.0, 40.0)


def errors_of(prog: Program) -> str:
    return " | ".join(issue.message for issue in prog.errors)


def test_checkerboard_runs(checkerboard: Program) -> None:
    """Программа из пяти операций даёт доску 600×120 из 45 ячеек."""
    board = checkerboard.apply()
    assert board.width_mm == pytest.approx(STRIP_COUNT * CELL_MM)
    assert board.length_mm == pytest.approx(ROW_COUNT * CELL_MM)
    assert board.thickness_mm == pytest.approx(CELL_MM)
    assert len(board.pieces) == STRIP_COUNT * ROW_COUNT


def test_checkerboard_alternates(checkerboard: Program) -> None:
    """Соседние ячейки по обеим осям — разных пород."""
    board = checkerboard.apply()
    for column in range(STRIP_COUNT):
        for row in range(ROW_COUNT):
            x = column * CELL_MM + CELL_MM / 2
            y = row * CELL_MM + CELL_MM / 2
            expected = MAPLE if (column + row) % 2 == 0 else WALNUT
            assert board.species_at(x, y) == expected, (column, row)


def test_checkerboard_has_no_slivers(checkerboard: Program) -> None:
    """Ни одна ячейка не выродилась в щепку при резах и обрезке."""
    assert not checkerboard.apply().has_degenerate(min_size_mm=CELL_MM - 1e-6)


def test_run_reports_cut_yield(checkerboard: Program) -> None:
    """Исполнение отдаёт выход полос — это вход для расчёта материала."""
    cuts = checkerboard.run().cuts
    assert len(cuts) == 1
    assert cuts[0].count == STRIP_COUNT
    assert cuts[0].remainder_mm == pytest.approx(0.0, abs=1e-6)
    assert cuts[0].source_length_mm == pytest.approx(600.0)


def test_geometry_is_deterministic(checkerboard: Program) -> None:
    """Один и тот же список операций даёт одну и ту же геометрию."""
    first = checkerboard.apply()
    second = checkerboard.apply()
    assert [p.polygon.wkt for p in first.pieces] == [p.polygon.wkt for p in second.pieces]


def test_json_roundtrip_preserves_pattern(checkerboard: Program) -> None:
    """Проект переживает JSON: та же программа, та же доска."""
    restored = Program.from_dict(json.loads(json.dumps(checkerboard.to_dict())))
    assert restored == checkerboard

    before, after = checkerboard.apply(), restored.apply()
    assert after.area_mm2 == pytest.approx(before.area_mm2)
    for column in range(STRIP_COUNT):
        for row in range(ROW_COUNT):
            x = column * CELL_MM + CELL_MM / 2
            y = row * CELL_MM + CELL_MM / 2
            assert after.species_at(x, y) == before.species_at(x, y)


def test_future_schema_version_rejected(checkerboard: Program) -> None:
    """Проект от более новой сборки не открываем молча."""
    data = checkerboard.to_dict()
    data["schema_version"] = 99
    with pytest.raises(ValueError, match="новее"):
        Program.from_dict(data)


def test_empty_program_is_invalid() -> None:
    """Пустая программа — не доска."""
    assert "программа пуста" in errors_of(program())


def test_program_must_start_with_glue() -> None:
    """Резать нечего, пока не склеен щит."""
    prog = program(Crosscut(40.0), StandOnEnd(), Assemble((0,), (False,), (0.0,)))
    assert "должна начинаться с Glue" in errors_of(prog)


def test_second_glue_rejected() -> None:
    """Второй щит с нуля пока не поддерживается — и об этом говорится прямо."""
    prog = program(SIMPLE_GLUE, SIMPLE_GLUE)
    assert "только в начале программы" in errors_of(prog)


def test_stand_on_end_requires_crosscut() -> None:
    """На торец ставят сразу после торцовки, иначе ячейки не занимают весь шаг."""
    prog = program(SIMPLE_GLUE, StandOnEnd())
    assert "сразу после торцовки" in errors_of(prog)


def test_stand_on_end_only_once() -> None:
    """Дважды на торец не ставят — доска уже стоит."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut(40.0),
        StandOnEnd(),
        StandOnEnd(),
        Assemble((0,), (False,), (0.0,)),
    )
    assert "один раз за программу" in errors_of(prog)


def test_crosscut_after_stand_on_end_rejected() -> None:
    """Торцовка поверх вертикальных волокон бессмысленна."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut(40.0),
        StandOnEnd(),
        Assemble(tuple(range(15)), (False,) * 15, (0.0,) * 15),
        Crosscut(40.0),
        Assemble((0,), (False,), (0.0,)),
    )
    assert "волокна уже вертикальны" in errors_of(prog)


def test_angled_cut_before_stand_on_end_rejected() -> None:
    """До постановки на торец угол задаёт направление волокон, а не узор."""
    prog = program(SIMPLE_GLUE, Cut(45.0, 40.0), Assemble((0,), (False,), (0.0,)))
    assert "только после StandOnEnd" in errors_of(prog)


def test_cut_needs_single_panel() -> None:
    """Резать можно щит, а не россыпь полос."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut(40.0),
        StandOnEnd(),
        Cut(45.0, 40.0),
        Assemble((0,), (False,), (0.0,)),
    )
    assert "надо склеить в щит" in errors_of(prog)


def test_assemble_needs_a_cut() -> None:
    """Склеивать нечего, пока щит не разрезан."""
    prog = program(SIMPLE_GLUE, Assemble((0,), (False,), (0.0,)))
    assert "нужен рез" in errors_of(prog)


def test_program_must_end_assembled() -> None:
    """Программа заканчивается щитом, а не кучей полос на верстаке."""
    prog = program(SIMPLE_GLUE, Crosscut(40.0), StandOnEnd())
    assert "заканчиваться собранным щитом" in errors_of(prog)


def test_missing_stand_on_end_warns() -> None:
    """Без StandOnEnd программа исполнима, но это не торцевая доска."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut(40.0),
        Assemble(tuple(range(15)), (False,) * 15, (0.0,) * 15),
    )
    assert prog.errors == []
    warnings = [issue.message for issue in prog.validate() if issue.level == "warning"]
    assert any("не торцевая доска" in message for message in warnings)


def test_invalid_program_refuses_to_run() -> None:
    """Неисполнимая программа падает с разбором, а не с невнятной геометрией."""
    with pytest.raises(ProgramError, match="начинаться с Glue"):
        program(Crosscut(40.0)).apply()


def test_issue_mentions_operation_number() -> None:
    """Ошибка указывает на конкретную операцию, чтобы её было где искать."""
    prog = program(SIMPLE_GLUE, StandOnEnd())
    assert str(prog.errors[0]).startswith("операция 2:")


def test_crop_trims_to_size(checkerboard: Program) -> None:
    """Обрезка доводит рваный от сдвигов край до прямоугольника."""
    without_crop = Program(operations=checkerboard.operations[:-1])
    ragged = without_crop.apply().length_mm
    assert ragged == pytest.approx((ROW_COUNT + 2) * CELL_MM)
    assert checkerboard.apply().length_mm == pytest.approx(ROW_COUNT * CELL_MM)
