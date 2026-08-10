"""Валидатор последовательности и исполнение программы целиком."""

import json

import pytest

from boardforge.core.ops import (
    Assemble,
    Crop,
    Crosscut,
    Cut,
    Glue,
    PieceRef,
    StandOnEnd,
    Strip,
)
from boardforge.core.program import Program, ProgramError, program
from tests.helpers import BOARD, CELL_MM, MAPLE, PANEL, ROW_COUNT, STRIP_COUNT, WALNUT

SIMPLE_GLUE = Glue("A", (Strip(MAPLE, 40.0), Strip(WALNUT, 40.0)), 600.0, 40.0)
ALL_STRIPS = tuple(PieceRef("A", index) for index in range(15))
FULL_ASSEMBLE = Assemble("B", ALL_STRIPS, (False,) * 15, (0.0,) * 15)


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
    assert cuts[0].billet == PANEL
    assert cuts[0].count == STRIP_COUNT
    assert cuts[0].remainder_mm == pytest.approx(0.0, abs=1e-6)
    assert cuts[0].source_length_mm == pytest.approx(600.0)


def test_run_keeps_all_billets(checkerboard: Program) -> None:
    """Исполнение отдаёт все заготовки — по ним считается выводимость рядов."""
    billets = checkerboard.run().billets
    assert set(billets) == {PANEL, BOARD}
    assert len(billets[PANEL]) == STRIP_COUNT
    assert len(billets[BOARD]) == 1


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


# --- несколько щитов (Р9) ---------------------------------------------------


def test_two_panels_run(two_panels: Program) -> None:
    """Доска собирается из деталей двух разных щитов."""
    board = two_panels.apply()
    assert board.width_mm == pytest.approx(6 * CELL_MM)
    assert len(two_panels.run().billets) == 3


def test_two_panels_alternate_composition(two_panels: Program) -> None:
    """Ряды из щита B несут вишню, которой в щите A нет вовсе."""
    board = two_panels.apply()
    species = {board.species_at(column * CELL_MM + 20.0, 20.0) for column in range(6)}
    assert "cherry" in species


def test_second_glue_allowed() -> None:
    """Ограничение «один щит на программу» снято — ради этого сделан Р9."""
    prog = program(
        SIMPLE_GLUE,
        Glue("B", (Strip(MAPLE, 40.0),), 200.0, 40.0),
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        Crosscut("B", 40.0),
        StandOnEnd("B"),
        Assemble(
            "C",
            (PieceRef("A", 0), PieceRef("B", 0)),
            (False, False),
            (0.0, 0.0),
        ),
    )
    assert prog.errors == []


def test_duplicate_billet_name_rejected() -> None:
    """Переопределение имени затёрло бы щит, из которого ещё берут детали."""
    prog = program(SIMPLE_GLUE, Glue("A", (Strip(MAPLE, 40.0),), 200.0, 40.0))
    assert "заготовка A уже заведена" in errors_of(prog)


def test_unknown_billet_rejected() -> None:
    """Ссылка на незаведённую заготовку — ошибка с именем."""
    prog = program(SIMPLE_GLUE, Crosscut("Z", 40.0))
    assert "заготовка Z ещё не заведена" in errors_of(prog)


def test_assemble_from_unknown_billet_rejected() -> None:
    """Деталь нельзя взять из щита, которого нет."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        Assemble("C", (PieceRef("Z", 0),), (False,), (0.0,)),
    )
    assert "заготовка Z ещё не заведена" in errors_of(prog)


def test_piece_index_on_uncut_billet_rejected() -> None:
    """У неразрезанного щита есть только деталь 0."""
    prog = program(
        SIMPLE_GLUE,
        Glue("B", (Strip(MAPLE, 40.0),), 200.0, 40.0),
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        Assemble("C", (PieceRef("A", 0), PieceRef("B", 3)), (False,) * 2, (0.0,) * 2),
    )
    assert "только деталь 0" in errors_of(prog)


def test_missing_piece_reported_at_run() -> None:
    """Номер детали за пределами пачки объясняет, сколько их на самом деле."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        Assemble("B", (PieceRef("A", 99),), (False,), (0.0,)),
    )
    with pytest.raises(ProgramError, match="всего 15"):
        prog.apply()


def test_mixing_stood_and_flat_rejected() -> None:
    """Деталь с торца и деталь с пласти в одном щите — разное третье измерение."""
    prog = program(
        SIMPLE_GLUE,
        Glue("B", (Strip(MAPLE, 40.0),), 200.0, 40.0),
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        Crosscut("B", 40.0),
        Assemble("C", (PieceRef("A", 0), PieceRef("B", 0)), (False,) * 2, (0.0,) * 2),
    )
    assert "и с торца, и с пласти" in errors_of(prog)


def test_stand_on_end_is_per_billet() -> None:
    """Каждый щит ставится на торец сам — «один раз на программу» снято."""
    prog = program(
        SIMPLE_GLUE,
        Glue("B", (Strip(MAPLE, 40.0),), 200.0, 40.0),
        Crosscut("A", 40.0),
        Crosscut("B", 40.0),
        StandOnEnd("A"),
        StandOnEnd("B"),
        Assemble(
            "C",
            (PieceRef("A", 0), PieceRef("B", 0)),
            (False, False),
            (0.0, 0.0),
        ),
    )
    assert prog.errors == []


def test_stand_on_end_survives_interleaving() -> None:
    """Проверка «сразу после торцовки» ведётся по заготовке, а не по списку."""
    prog = program(
        SIMPLE_GLUE,
        Glue("B", (Strip(MAPLE, 40.0),), 200.0, 40.0),
        Crosscut("A", 40.0),
        Crosscut("B", 40.0),
        StandOnEnd("B"),
        StandOnEnd("A"),
        Assemble(
            "C",
            (PieceRef("A", 0), PieceRef("B", 0)),
            (False, False),
            (0.0, 0.0),
        ),
    )
    assert prog.errors == []


# --- валидатор последовательности -------------------------------------------


def test_empty_program_is_invalid() -> None:
    """Пустая программа — не доска."""
    assert "программа пуста" in errors_of(program())


def test_program_must_start_with_glue() -> None:
    """Резать нечего, пока не склеен щит."""
    prog = program(Crosscut("A", 40.0))
    assert "должна начинаться с Glue" in errors_of(prog)


def test_stand_on_end_requires_crosscut() -> None:
    """На торец ставят сразу после торцовки, иначе ячейки не занимают весь шаг."""
    prog = program(SIMPLE_GLUE, StandOnEnd("A"))
    assert "сразу после торцовки" in errors_of(prog)


def test_stand_on_end_only_once_per_billet() -> None:
    """Дважды на торец не ставят — щит уже стоит."""
    prog = program(
        SIMPLE_GLUE, Crosscut("A", 40.0), StandOnEnd("A"), StandOnEnd("A"), FULL_ASSEMBLE
    )
    assert "уже ставили на торец" in errors_of(prog)


def test_crosscut_after_stand_on_end_rejected() -> None:
    """Торцовка поверх вертикальных волокон бессмысленна."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        FULL_ASSEMBLE,
        Crosscut("B", 40.0),
        Assemble("C", (PieceRef("B", 0),), (False,), (0.0,)),
    )
    assert "волокна уже вертикальны" in errors_of(prog)


def test_angled_cut_before_stand_on_end_rejected() -> None:
    """До постановки на торец угол задаёт направление волокон, а не узор (Р10)."""
    prog = program(
        SIMPLE_GLUE,
        Cut("A", 45.0, 40.0),
        Assemble("B", (PieceRef("A", 0),), (False,), (0.0,)),
    )
    assert "только после StandOnEnd" in errors_of(prog)


def test_cut_needs_single_panel() -> None:
    """Резать можно щит, а не россыпь полос."""
    prog = program(
        SIMPLE_GLUE,
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        Cut("A", 45.0, 40.0),
        Assemble("B", (PieceRef("A", 0),), (False,), (0.0,)),
    )
    assert "уже разрезана" in errors_of(prog)


def test_program_must_end_assembled() -> None:
    """Программа заканчивается щитом, а не кучей полос на верстаке."""
    prog = program(SIMPLE_GLUE, Crosscut("A", 40.0), StandOnEnd("A"))
    assert "осталась россыпью деталей" in errors_of(prog)


def test_missing_stand_on_end_warns() -> None:
    """Без StandOnEnd программа исполнима, но это не торцевая доска."""
    prog = program(SIMPLE_GLUE, Crosscut("A", 40.0), FULL_ASSEMBLE)
    assert prog.errors == []
    warnings = [issue.message for issue in prog.validate() if issue.level == "warning"]
    assert any("не торцевая доска" in message for message in warnings)


def test_invalid_program_refuses_to_run() -> None:
    """Неисполнимая программа падает с разбором, а не с невнятной геометрией."""
    with pytest.raises(ProgramError, match="начинаться с Glue"):
        program(Crosscut("A", 40.0)).apply()


def test_issue_mentions_operation_number() -> None:
    """Ошибка указывает на конкретную операцию, чтобы её было где искать."""
    prog = program(SIMPLE_GLUE, StandOnEnd("A"))
    assert str(prog.errors[0]).startswith("операция 2:")


def test_crop_trims_to_size(checkerboard: Program) -> None:
    """Обрезка доводит рваный от сдвигов край до прямоугольника.

    До обрезки щит длиннее полосы ровно на сдвиг: полоса несёт все ячейки
    исходного щита, а нечётные полосы съезжают на ячейку вниз.
    """
    glue = checkerboard.operations[0]
    max_offset = max(checkerboard.operations[3].offsets_mm)

    without_crop = Program(operations=checkerboard.operations[:-1])
    assert without_crop.apply().length_mm == pytest.approx(glue.width_mm + max_offset)
    assert checkerboard.apply().length_mm == pytest.approx(ROW_COUNT * CELL_MM)


def test_crop_of_stack_rejected() -> None:
    """Обрезать россыпь деталей нельзя — обрезают собранный щит."""
    prog = program(SIMPLE_GLUE, Crosscut("A", 40.0), Crop("A", left=5.0))
    assert "только собранный щит" in errors_of(prog)
