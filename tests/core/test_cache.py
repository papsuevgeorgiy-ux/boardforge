"""Кэш по хешу префикса программы.

Обещан в `architecture.md`: правка последней операции не должна пересчитывать
всё. В редакторе правят именно последнюю — двигают ползунок сдвига, меняют угол,
— и на угловых узорах полигонов достаточно, чтобы это было заметно.

Ключ — сам префикс операций: операции заморожены, значит хешируются, и
отдельная «стабильная сериализация» не нужна. Отсюда же берётся главное
свойство: разные параметры дают разный ключ, и подсунуть чужой результат
невозможно по построению. Это тут и проверяется.
"""

import pytest

from boardforge.core import program as program_module
from boardforge.core.ops import Assemble, Crosscut, Cut, Glue, PieceRef, StandOnEnd, Strip
from boardforge.core.program import Program, cache_size, clear_cache
from tests.helpers import build_checkerboard

MAPLE, WALNUT = "maple_hard", "walnut_black"


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


def _angled(offset_mm: float, angle_deg: float = 45.0) -> Program:
    return Program(
        operations=(
            Glue("A", (Strip(MAPLE, 50.0), Strip(WALNUT, 50.0)), 400.0, 40.0),
            Crosscut("A", 40.0),
            StandOnEnd("A"),
            Assemble(
                "P",
                tuple(PieceRef("A", index) for index in range(10)),
                (False,) * 10,
                (0.0,) * 10,
            ),
            Cut("P", angle_deg, 40.0),
            Assemble(
                "BOARD",
                (PieceRef("P", 2), PieceRef("P", 3)),
                (False, False),
                (0.0, offset_mm),
            ),
        )
    )


def test_editing_the_last_operation_reuses_the_prefix() -> None:
    """Правка последней операции добавляет в кэш одну запись, а не всю программу."""
    first = _angled(0.0)
    first.run()
    after_first = cache_size()
    assert after_first == len(first.operations)

    _angled(12.0).run()
    assert cache_size() == after_first + 1, (
        "пересчитался не только последний шаг — префикс не переиспользовался"
    )


def test_editing_an_early_operation_does_not_reuse_anything() -> None:
    """Правка угла реза меняет ключ префикса, и хвост считается заново."""
    _angled(0.0, angle_deg=45.0).run()
    before = cache_size()

    _angled(0.0, angle_deg=60.0).run()
    # Совпадают первые четыре операции, дальше ключи расходятся.
    assert cache_size() == before + 2


def test_cache_never_returns_someone_elses_board() -> None:
    """Разные параметры — разная доска. Кэш не имеет права это перепутать."""
    straight = _angled(0.0).apply()
    shifted = _angled(25.0).apply()
    assert straight.length_mm != pytest.approx(shifted.length_mm)

    clear_cache()
    assert _angled(0.0).apply().length_mm == pytest.approx(straight.length_mm)
    assert _angled(25.0).apply().length_mm == pytest.approx(shifted.length_mm)


def test_cached_run_gives_the_same_geometry() -> None:
    """Второй прогон той же программы совпадает с первым ячейка в ячейку."""
    program = build_checkerboard()
    first = program.apply()
    second = program.apply()

    assert len(first.pieces) == len(second.pieces)
    for before, after in zip(first.pieces, second.pieces, strict=True):
        assert before.polygon.equals(after.polygon)
        assert before.species == after.species
        assert before.origin == after.origin


def test_cut_yields_survive_the_cache() -> None:
    """Выход деталей из резов берётся из снимка, а не теряется при попадании."""
    program = _angled(0.0)
    first = program.run()
    second = program.run()
    assert [cut.count for cut in first.cuts] == [cut.count for cut in second.cuts]
    assert [cut.op_index for cut in first.cuts] == [cut.op_index for cut in second.cuts]


def test_cache_is_bounded() -> None:
    """Кэш не растёт бесконечно: редактор гоняет сотни промежуточных состояний."""
    for step in range(program_module._CACHE_LIMIT + 20):
        _angled(float(step)).run()
    assert cache_size() <= program_module._CACHE_LIMIT
