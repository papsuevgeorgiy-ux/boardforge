"""Пошаговая инструкция: шаги выводятся из программы, а не пишутся рядом с ней.

Главное требование дня: инструкция не имеет права быть отдельным описанием
доски. Если её можно рассогласовать с программой — значит, она уже не про эту
доску. Поэтому здесь проверяется не «текст красивый», а совпадения: число шагов
с числом операций, числа в шагах — с исполнением, слова — со словами редактора.
"""

import re

import pytest

from boardforge.core.library import build
from boardforge.core.program import Program
from boardforge.core.species import load_species
from boardforge.core.units import INCHES, MILLIMETRES
from boardforge.io.steps import instructions, outcome
from tests.helpers import build_checkerboard

TEMPLATES = ("checkerboard", "chevron", "cubes")


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


@pytest.fixture(scope="module")
def checkerboard() -> Program:
    return build_checkerboard()


@pytest.fixture(scope="module")
def steps(checkerboard, catalogue):
    return instructions(checkerboard, catalogue)


def test_a_step_for_every_operation(checkerboard, steps) -> None:
    """Шагов ровно столько же, сколько операций, и они пронумерованы подряд.

    Не формальность: лишний шаг означал бы, что инструкция что-то придумала
    от себя, а пропущенный — что столяр не узнает про одну из операций.
    """
    assert len(steps) == len(checkerboard.operations)
    assert [step.number for step in steps] == list(range(1, len(steps) + 1))


def test_every_step_carries_its_own_drawing(steps) -> None:
    """У каждого шага свой чертёж — вставляемый в HTML, без заголовка XML."""
    for step in steps:
        assert step.drawing.startswith("<svg")
        assert "<?xml" not in step.drawing
        assert f"Шаг {step.number}" in step.drawing


def test_drawings_differ_from_step_to_step(steps) -> None:
    """Картинки не дублируются: верстак после каждой операции выглядит иначе."""
    assert len({step.drawing for step in steps}) == len(steps)


def test_outcome_counts_the_parts_the_cut_really_gives(checkerboard, catalogue) -> None:
    """«Получится N деталей» берётся из исполнения, а не из деления длины на шаг.

    Число полос из щита операция не знает: остаток от торцовки в неё не входит,
    и посчитанное «на бумаге» разошлось бы с тем, что выйдет на станке.
    """
    counts = {cut.op_index: cut.count for cut in checkerboard.run().cuts}
    assert counts, "в шахматке есть хотя бы один рез"
    for index, count in counts.items():
        text = instructions(checkerboard, catalogue)[index].outcome
        assert f"{count} деталей" in text


def test_uneven_parts_are_named_uneven(catalogue) -> None:
    """После углового реза полосы разной длины, и инструкция это говорит.

    Обратное было бы враньём в самом дорогом месте: на угловом узоре крайние
    полосы уходят в отход, и «16 одинаковых деталей» отправило бы столяра
    искать несуществующую ошибку сборки.
    """
    chevron = build("chevron").program
    texts = [step.outcome for step in instructions(chevron, catalogue)]
    assert any("разного размера" in text for text in texts)


def test_steps_speak_the_same_words_as_the_editor(checkerboard, catalogue) -> None:
    """Панель операций в браузере и инструкция в распечатке — одни слова.

    Ради этого `describe` и переехала в `io/steps.py`: две копии текста
    разъезжаются молча, и заметно это станет на распечатанном листе.
    """
    from boardforge.web.presenters import operation_views

    views = operation_views(checkerboard, catalogue, MILLIMETRES)
    steps = instructions(checkerboard, catalogue, MILLIMETRES)
    assert [(v.kind, v.title, v.detail) for v in views] == [
        (s.kind, s.title, s.detail) for s in steps
    ]


def test_units_reach_the_steps(checkerboard, catalogue) -> None:
    """Единицы — способ смотреть (Р19), и инструкция их слушает."""
    inches = instructions(checkerboard, catalogue, INCHES)
    assert not any("мм" in step.outcome for step in inches)
    assert any("мм" in step.outcome for step in instructions(checkerboard, catalogue))


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_produces_an_instruction(template, catalogue) -> None:
    """Инструкция строится для всех узоров, включая двухщитовые кубы.

    У кубов операций восемнадцать и две линии заготовок; порядок шагов обязан
    идти по программе, а не по щитам — иначе столяр склеит B прежде, чем
    разрежет A.
    """
    program = build(template).program
    steps = instructions(program, catalogue)
    assert len(steps) == len(program.operations)
    assert all(step.detail for step in steps)


def test_outcome_of_a_glued_panel_is_a_single_billet(checkerboard) -> None:
    """После склейки на верстаке один щит, а не пачка — так и написано."""
    frame = checkerboard.trace()[0]
    text = outcome(frame, MILLIMETRES)
    assert "деталей" not in text
    assert re.search(r"\d", text), "размер щита должен быть назван числом"
