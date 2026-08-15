"""Общие фикстуры и разметка дорогих тестов.

Полный прогон идёт больше двадцати минут, и это не «подождать», а причина
не гонять тесты вовсе. Поэтому дорогие помечаются `slow`, и в разработке
набор гоняется как `-m "not slow"`. Перед коммитом (`/check`) и на закрытии
дня прогон остаётся **полным**: быстрый набор — рабочий инструмент, а не
новое определение зелёного.

Разметка не расставлена руками по файлам, а выведена из замера
(`pytest --durations`) в одном месте — иначе она разъедется с правдой в первый
же день. Правил три:

1. **Параметр `cubes`.** Кубы дороги по построению: два щита-близнеца и два
   угловых реза (Р23), у заготовок по 300–400 ячеек. В таблице замера они
   занимают почти каждую строку, а параметризация по шаблонам гоняет их
   в десятке файлов. Прочие шаблоны в быстром наборе остаются.
2. **Модуль целиком** — если в нём дороги все тесты, а не отдельные.
3. **Поимённый список** с замеренными секундами.
"""

import pytest

from boardforge.core.program import Program
from tests.helpers import build_checkerboard, build_two_panels

SLOW_PARAMS = frozenset({"cubes"})

SLOW_MODULES = frozenset(
    {
        # Весь модуль про кубы: 32 с + 30 с + 10 с + …
        "tests/core/test_cubes.py",
    }
)

SLOW_TESTS: dict[str, dict[str, int]] = {
    # Путь → имя теста → замеренные секунды полного прогона.
    "tests/cli/test_day4_commands.py": {
        "test_contact_sheet_covers_the_whole_library": 33,
    },
    "tests/cli/test_cli.py": {
        "test_diagnostics_are_off_by_default": 31,
        "test_examples_write_every_board": 18,
        "test_examples_are_manufacturable": 11,
    },
    "tests/core/test_fitness.py": {
        "test_repeated_complaints_count_once": 27,
        "test_every_library_pattern_gets_a_finite_score": 22,
    },
    "tests/core/test_generate.py": {
        "test_weights_steer_the_search": 21,
        "test_one_seed_gives_one_pattern": 14,
        "test_evolution_is_reproducible": 14,
        "test_evolution_beats_the_random_start": 25,
        "test_evolution_result_is_makeable": 11,
        "test_different_seeds_give_different_patterns": 11,
    },
    "tests/calc/test_cutlist.py": {
        "test_cubes_leave_a_kit_for_a_second_board": 22,
        "test_kept_leftovers_are_no_worse_than_what_went_in": 10,
        "test_used_parts_are_never_counted_as_leftovers": 10,
    },
    "tests/calc/test_warnings.py": {
        "test_lower_threshold_would_flood_the_list": 11,
        "test_threshold_fires_on_a_minority_of_the_library": 10,
    },
    "tests/calc/test_material.py": {
        "test_twin_panels_get_the_same_allowances": 10,
    },
    "tests/calc/test_estimate.py": {
        "test_cubes_cost_is_split_between_two_boards": 4,
    },
    "tests/io/test_report.py": {
        "test_cubes_report_the_second_board": 17,
    },
    "tests/render/test_blueprint.py": {
        "test_no_letter_lands_on_a_seam": 11,
        "test_blueprint_draws_the_rounded_edge": 10,
        "test_board_edge_is_one_contour_on_cubes": 10,
    },
}


def _is_slow(item: pytest.Item) -> bool:
    path = item.location[0].replace("\\", "/")
    if path in SLOW_MODULES:
        return True
    if (item.originalname or item.name) in SLOW_TESTS.get(path, ()):
        return True
    callspec = getattr(item, "callspec", None)
    return callspec is not None and any(
        value in SLOW_PARAMS
        for value in callspec.params.values()
        if isinstance(value, str)
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Пометить дорогие тесты `slow` по замеру, а не по ощущению."""
    for item in items:
        if _is_slow(item):
            item.add_marker(pytest.mark.slow)


@pytest.fixture
def checkerboard() -> Program:
    """Эталонная шахматка 15×3 ячейки из одного щита."""
    return build_checkerboard()


@pytest.fixture
def two_panels() -> Program:
    """Доска, где ряды приходят из двух разных щитов."""
    return build_two_panels()
