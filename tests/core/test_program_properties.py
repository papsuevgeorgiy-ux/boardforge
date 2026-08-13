"""Свойства программы целиком: угловые резы, несколько щитов, третья склейка.

Главная страховка Дня 3. Резы под углом дают клинья, обрезки и полигоны,
которых в примерах не было; проверяем не конкретные числа, а то, что дерево
не берётся из ниоткуда и не исчезает между операциями.

Отдельно от `test_geometry_properties.py`: там свойства одного реза, здесь —
свойства цепочки, где участвуют и `StandOnEnd`, и склейка деталей из разных
заготовок. Каждое ожидание считается из параметров операций, а не повторяет
вычисление из `geometry` — иначе тест подтверждал бы сам себя.
"""

from collections import defaultdict

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from boardforge.core.ops import (
    Assemble,
    Crosscut,
    Cut,
    Glue,
    Operation,
    PieceRef,
    StandOnEnd,
    Strip,
)
from boardforge.core.piece import Part
from boardforge.core.program import Execution, Program

SPECIES = ("maple_hard", "walnut_black", "cherry", "oak")
NAMES = ("A", "B", "C")

TOLERANCE = {"rel": 1e-6}

PROPERTY_SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@st.composite
def angled_programs(draw: st.DrawFn) -> Program:
    """Программа «несколько щитов → склейка → угловой рез».

    Кончается россыпью полос: финальную склейку дописывает `_finished`, потому
    что разным тестам нужны разные наборы полос.

    Шаг торцовки общий на все щиты: после `StandOnEnd` он становится высотой
    доски, а детали разной высоты в один щит не клеятся. Толщина у каждого щита
    своя — в плане это ширина столбца, и разнобой здесь как раз интересен.
    """
    crosscut_step = draw(st.floats(20.0, 50.0))
    operations: list[Operation] = []
    slats: list[PieceRef] = []

    for name in NAMES[: draw(st.integers(1, 3))]:
        strips = tuple(
            draw(
                st.lists(
                    st.builds(
                        Strip,
                        species=st.sampled_from(SPECIES),
                        width_mm=st.floats(15.0, 50.0),
                    ),
                    min_size=1,
                    max_size=3,
                )
            )
        )
        count = draw(st.integers(2, 4))
        tail = draw(st.floats(0.0, 0.9)) * crosscut_step
        operations += [
            Glue(
                id=name,
                strips=strips,
                length_mm=crosscut_step * count + tail,
                thickness_mm=draw(st.floats(15.0, 40.0)),
            ),
            Crosscut(source=name, step_mm=crosscut_step),
            StandOnEnd(source=name),
        ]
        slats += [PieceRef(name, index) for index in range(count)]

    operations.append(
        Assemble(
            id="P",
            pieces=tuple(slats),
            reversed=tuple(draw(st.booleans()) for _ in slats),
            offsets_mm=tuple(draw(st.floats(-30.0, 30.0)) for _ in slats),
        )
    )
    operations.append(
        Cut(
            source="P",
            angle_deg=draw(st.floats(5.0, 175.0)),
            step_mm=draw(st.floats(15.0, 60.0)),
        )
    )
    return Program(operations=tuple(operations))


def _finished(program: Program, count: int = 1) -> Program:
    """Дописать финальную склейку: программа обязана кончаться собранным щитом."""
    picks = tuple(PieceRef("P", index) for index in range(count))
    return Program(
        operations=(
            *program.operations,
            Assemble(
                id="BOARD",
                pieces=picks,
                reversed=(False,) * count,
                offsets_mm=(0.0,) * count,
            ),
        )
    )


def _without_cut(program: Program) -> Program:
    """Та же программа, оборванная перед угловым резом: щит `P` целый."""
    return Program(operations=program.operations[:-1])


def _run(program: Program) -> Execution | None:
    """Исполнить; None, если шаг реза не влез в щит — такой пример не про нас."""
    assert not program.errors, [str(issue) for issue in program.errors]
    try:
        return program.run()
    except ValueError:
        return None


def _areas_by_species(parts: tuple[Part, ...]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for part in parts:
        for piece in part.pieces:
            totals[piece.species] += piece.area_mm2
    return dict(totals)


@given(program=angled_programs())
@PROPERTY_SETTINGS
def test_angled_cut_conserves_area(program: Program) -> None:
    """Сумма площадей полос плюс отход равна площади щита — при любом угле и шаге.

    Площадь щита берётся исполнением той же программы, оборванной перед резом,
    а не пересчётом внутренностей реза.
    """
    before = _run(_without_cut(program))
    after = _run(_finished(program))
    assume(after is not None)
    assert before is not None and after is not None

    cut = after.cuts[-1]
    strips = sum(part.area_mm2 for part in after.billets["P"])

    assert cut.waste_mm2 >= -1e-9
    assert strips + cut.waste_mm2 == pytest.approx(before.board.area_mm2, **TOLERANCE)


@given(program=angled_programs())
@PROPERTY_SETTINGS
def test_angled_cut_conserves_each_species(program: Program) -> None:
    """Порода не подменяется резом: новых не появляется, старых не прибавляется."""
    before = _run(_without_cut(program))
    after = _run(_finished(program))
    assume(after is not None)
    assert before is not None and after is not None

    was = _areas_by_species((before.board,))
    kept = _areas_by_species(after.billets["P"])

    assert set(kept) <= set(was)
    for species, total in kept.items():
        assert total <= was[species] * (1 + 1e-9)

    lost = sum(was.get(species, 0.0) - kept.get(species, 0.0) for species in was)
    assert lost == pytest.approx(after.cuts[-1].waste_mm2, abs=1e-6)


@given(program=angled_programs())
@PROPERTY_SETTINGS
def test_stand_on_end_scales_area_by_the_known_factor(program: Program) -> None:
    """Постановка на торец — масштаб `толщина / шаг` по X.

    Множитель известен из геометрии операции, а не подсмотрен в коде: полоса
    шириной в шаг торцовки становится шириной в толщину щита.
    """
    execution = _run(_finished(program))
    assume(execution is not None)
    assert execution is not None

    glues = {op.id: op for op in program.operations if isinstance(op, Glue)}
    steps = {
        op.source: op.step_mm for op in program.operations if isinstance(op, Crosscut)
    }

    for name, glue in glues.items():
        slats = execution.billets[name]
        expected = len(slats) * glue.thickness_mm * glue.width_mm
        assert sum(part.area_mm2 for part in slats) == pytest.approx(
            expected, **TOLERANCE
        )
        for part in slats:
            assert part.thickness_mm == pytest.approx(steps[name])


@given(program=angled_programs(), take=st.integers(1, 6))
@PROPERTY_SETTINGS
def test_assemble_is_exactly_the_sum_of_its_pieces(program: Program, take: int) -> None:
    """Склейка ничего не теряет и не создаёт: площадь щита — сумма деталей."""
    probe = _run(_finished(program))
    assume(probe is not None)
    assert probe is not None

    count = min(take, len(probe.billets["P"]))
    execution = _run(_finished(program, count))
    assume(execution is not None)
    assert execution is not None

    chosen = probe.billets["P"][:count]
    assert execution.board.area_mm2 == pytest.approx(
        sum(part.area_mm2 for part in chosen), **TOLERANCE
    )


@given(program=angled_programs())
@PROPERTY_SETTINGS
def test_every_strip_fits_the_cut_step(program: Program) -> None:
    """Ни одна полоса не шире шага реза — иначе рез прошёл не там, где заявлено."""
    execution = _run(_finished(program))
    assume(execution is not None)
    assert execution is not None

    step = execution.cuts[-1].step_mm
    for part in execution.billets["P"]:
        assert part.width_mm <= step * (1 + 1e-9)
