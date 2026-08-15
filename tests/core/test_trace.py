"""`Program.trace()` — состояние верстака после каждой операции.

Инструкция не может рисовать шаги «примерно»: если кадр разойдётся с тем, что
считает `run()`, столяр увидит одну доску, а смета посчитает другую. Поэтому
главный тест здесь — не «кадров столько же, сколько операций», а совпадение
последнего кадра с результатом обычного исполнения.
"""

import pytest

from boardforge.core.library import build
from boardforge.core.ops import Assemble, Crop, Glue, target_of
from boardforge.core.program import Program, ProgramError
from tests.helpers import build_checkerboard

TEMPLATES = ("checkerboard", "chevron", "herringbone", "cubes")


@pytest.fixture(scope="module")
def checkerboard() -> Program:
    return build_checkerboard()


def test_one_frame_per_operation(checkerboard: Program) -> None:
    """Кадр на операцию, в том же порядке — по ним и нумеруются шаги."""
    frames = checkerboard.trace()
    assert len(frames) == len(checkerboard.operations)
    for index, frame in enumerate(frames):
        assert frame.index == index
        assert frame.operation is checkerboard.operations[index]


@pytest.mark.parametrize("template", TEMPLATES)
def test_last_frame_is_the_board(template: str) -> None:
    """Последний кадр — ровно та доска, которую отдаёт `run()`.

    Это и есть контракт между инструкцией и всем остальным: чертёж шага и
    чертёж готовой доски обязаны быть про одно и то же изделие.
    """
    program = build(template).program
    assert program.trace()[-1].parts[0] == program.run().board


@pytest.mark.parametrize("template", TEMPLATES)
def test_frames_follow_the_targets(template: str) -> None:
    """Каждый кадр показывает ту заготовку, которой коснулась операция."""
    program = build(template).program
    for frame in program.trace():
        assert frame.target == target_of(frame.operation)
        assert frame.parts, "заготовка после операции не может быть пустой"


def test_cutting_leaves_a_stack_and_gluing_a_single_panel(checkerboard: Program) -> None:
    """Рез переводит заготовку в пачку, склейка сводит обратно в одну деталь.

    Различие видно только по кадрам: в готовой доске от него не остаётся следа,
    а инструкции надо сказать «получится 9 полос», и число берётся отсюда.
    """
    frames = checkerboard.trace()
    for frame in frames:
        if isinstance(frame.operation, Glue | Assemble | Crop):
            assert len(frame.parts) == 1
        else:
            assert len(frame.parts) > 1


def test_frames_do_not_share_state(checkerboard: Program) -> None:
    """Кадр — снимок, а не окно в изменяющийся словарь.

    Ловушка настоящая: словарь заготовок один на весь прогон, и кадр,
    сохранивший ссылку на него, показал бы конечное состояние на каждом шаге.
    """
    frames = checkerboard.trace()
    names = [sorted(frame.billets) for frame in frames]
    assert names[0] != names[-1], "состав заготовок обязан меняться по ходу программы"


def test_trace_refuses_a_broken_program(checkerboard: Program) -> None:
    """Неисполнимая программа не даёт кадров — и говорит почему.

    Взят настоящий обрубок: программа, оборванная сразу после торцовки. Именно
    поэтому шаги и берутся кадрами, а не исполнением префиксов `operations[:k]`
    — большинство префиксов валидатор не пропускает, и правильно делает.
    """
    broken = Program(
        operations=checkerboard.operations[:2],
        schema_version=checkerboard.schema_version,
    )
    with pytest.raises(ProgramError, match="россыпью"):
        broken.trace()
