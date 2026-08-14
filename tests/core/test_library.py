"""Библиотека узоров: каждый обязан быть изготовим, периодичен и не такой,
как остальные.

Главный тест здесь — не «программа собралась», а **период**. Узор объявляет
вектор, вдоль которого обязан переходить сам в себя; ошибись в сдвиге одного
столбца, и период сломается. Это тот же тест на схождение, что у шеврона,
только выраженный трансляцией, а не швом.

Второй по важности — различимость. Двенадцать вариаций шахматки — не библиотека,
и поймать это должен тест, а не жюри.
"""

import pytest

from boardforge.core.library import LIBRARY, Pattern, build
from boardforge.core.piece import Part
from boardforge.core.program import Program
from boardforge.core.safety import inspect
from boardforge.core.species import load_species

MIN_TEMPLATES = 12

ANGLED = {"chevron", "herringbone", "cubes"}
"""У этих схождение проверяется по швам своими тестами (`test_patterns.py`,
`test_cubes.py`): трансляцией их узор не описывается."""


def _probe(board: Part, steps: int = 18, margin_mm: float = 6.0):
    xmin, ymin, xmax, ymax = board.bounds
    for i in range(steps):
        for j in range(steps):
            yield (
                xmin + margin_mm + (xmax - xmin - 2 * margin_mm) * i / (steps - 1),
                ymin + margin_mm + (ymax - ymin - 2 * margin_mm) * j / (steps - 1),
            )


def _fingerprint(board: Part) -> tuple[str, ...]:
    """Отпечаток узора: породы по сетке проб, нормированные к первой."""
    seen: dict[str, str] = {}
    marks: list[str] = []
    for x, y in _probe(board, steps=24):
        species = board.species_at(x, y)
        if species is None:
            marks.append("-")
            continue
        marks.append(seen.setdefault(species, str(len(seen))))
    return tuple(marks)


@pytest.fixture(scope="module")
def patterns() -> dict[str, Pattern]:
    return {key: template() for key, template in LIBRARY.items()}


def test_library_is_big_enough() -> None:
    assert len(LIBRARY) >= MIN_TEMPLATES, sorted(LIBRARY)


def test_keys_and_titles_are_unique() -> None:
    titles = [template.title for template in LIBRARY.values()]
    assert len(set(titles)) == len(titles), titles
    for key, template in LIBRARY.items():
        assert template.key == key
        assert template.summary, key


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_every_template_validates_and_runs(key: str, patterns) -> None:
    """Ни одна ошибка валидатора: библиотека не имеет права предлагать брак."""
    program = patterns[key].program
    assert not program.errors, [str(issue) for issue in program.errors]

    board = program.run().board
    assert len(board.pieces) >= 20, f"{key}: узор — это не десяток ячеек"
    assert board.width_mm > 0 and board.length_mm > 0


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_every_template_is_safe_to_make(key: str, patterns) -> None:
    """И ни одной ошибки изготовимости: клиньев и опрокидывания быть не должно."""
    program = patterns[key].program
    execution = program.run()
    errors = [issue for issue in inspect(program, execution) if issue.level == "error"]
    assert not errors, [str(issue) for issue in errors]


@pytest.mark.parametrize("key", sorted(set(LIBRARY) - ANGLED))
def test_declared_period_holds(key: str, patterns) -> None:
    """Узор обязан переходить в себя вдоль объявленного вектора.

    Проба берётся только там, где материал есть по обоим концам вектора:
    у края доски переносить нечего, и это не расхождение узора.
    """
    pattern = patterns[key]
    assert pattern.periods_mm or pattern.half_turn, f"{key}: нечем закрыть схождение"

    board = pattern.program.run().board
    for dx, dy in pattern.periods_mm:
        checked = matched = 0
        for x, y in _probe(board):
            here = board.species_at(x, y)
            there = board.species_at(x + dx, y + dy)
            if here is None or there is None:
                continue
            checked += 1
            matched += here == there
        assert checked > 40, f"{key}: проб слишком мало ({checked}) для ({dx}, {dy})"
        assert matched == checked, (
            f"{key}: узор не переносится на ({dx:.1f}, {dy:.1f}) — "
            f"разошлось {checked - matched} проб из {checked}"
        )


@pytest.mark.parametrize(
    "key", sorted(key for key, value in LIBRARY.items() if key not in ANGLED)
)
def test_half_turn_symmetry_holds_where_declared(key: str, patterns) -> None:
    """Поворот доски на 180° — тоже схождение, просто другого рода."""
    pattern = patterns[key]
    if not pattern.half_turn:
        pytest.skip("этот узор симметрии поворота не обещает")

    board = pattern.program.run().board
    xmin, ymin, xmax, ymax = board.bounds
    checked = matched = 0
    for x, y in _probe(board):
        here = board.species_at(x, y)
        there = board.species_at(xmin + xmax - x, ymin + ymax - y)
        if here is None or there is None:
            continue
        checked += 1
        matched += here == there
    assert checked > 40
    assert matched == checked, f"{key}: разошлось {checked - matched} из {checked}"


def test_patterns_are_all_different(patterns) -> None:
    """Двенадцать вариаций шахматки — не библиотека.

    Сравниваются отпечатки, нормированные к порядку появления пород: узор,
    отличающийся только выбором дерева, — тот же узор.
    """
    prints = {
        key: _fingerprint(value.program.run().board) for key, value in patterns.items()
    }
    collisions = [
        (first, second)
        for index, first in enumerate(sorted(prints))
        for second in sorted(prints)[index + 1 :]
        if prints[first] == prints[second]
    ]
    assert not collisions, collisions


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_templates_are_parametric_not_constant(key: str) -> None:
    """Шаблон обязан отвечать на параметры, иначе это не шаблон, а картинка."""
    template = LIBRARY[key]
    size_key = "cell_mm" if "cell_mm" in template.defaults else "side_mm"
    smaller = template(**{size_key: template.defaults[size_key] * 0.75})

    board = template().program.run().board
    other = smaller.program.run().board
    assert other.width_mm != pytest.approx(board.width_mm, rel=1e-3), key


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_same_parameters_give_the_same_program(key: str) -> None:
    """Библиотека детерминирована: дважды собранный узор совпадает операция
    в операцию. Без этого ни сид генератора, ни кэш не имеют смысла."""
    assert LIBRARY[key]().program == LIBRARY[key]().program


def test_unknown_parameter_is_refused() -> None:
    with pytest.raises(ValueError, match="неизвестные параметры"):
        LIBRARY["stripes"](cellmm=40.0)


def test_unknown_template_lists_what_there_is() -> None:
    with pytest.raises(ValueError, match="нет такого узора"):
        build("houndstooth")


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_every_species_exists_in_the_catalogue(key: str) -> None:
    """Породы шаблонов — из справочника, а не выдуманные."""
    catalogue = load_species()
    program: Program = LIBRARY[key]().program
    used = {
        strip.species
        for op in program.operations
        if hasattr(op, "strips")
        for strip in op.strips
    }
    assert used <= set(catalogue), sorted(used - set(catalogue))
