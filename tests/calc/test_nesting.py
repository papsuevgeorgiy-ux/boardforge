"""Одномерный раскрой: рейки из мерных досок.

Проверяется не близость к оптимуму — её здесь и не обещают, — а три вещи:
план физически осуществим, он никогда не хуже жадного, и он воспроизводим.
"""

import pytest

from boardforge.calc.cutlist import cut_list
from boardforge.calc.nesting import (
    STANDARD_LENGTHS_MM,
    Demand,
    demands_of,
    nest,
    nest_stock,
)
from boardforge.core.library import build
from tests.helpers import build_checkerboard

KERF = 3.2


def _rails(*lengths: float) -> tuple[Demand, ...]:
    return tuple(
        Demand(f"X{index + 1}", "maple_hard", 40.0, length)
        for index, length in enumerate(lengths)
    )


@pytest.fixture(scope="module")
def plan():
    return nest_stock(cut_list(build_checkerboard()))


def test_every_rail_is_cut_exactly_once(plan) -> None:
    """Каждая рейка попадает ровно в одну доску: ни потерянных, ни задвоенных."""
    ordered = demands_of(cut_list(build_checkerboard()))
    planned = [part.number for board in plan.boards for part in board.parts]
    assert sorted(planned) == sorted(item.number for item in ordered)


def test_nothing_hangs_over_the_end(plan) -> None:
    """Из доски нельзя выпилить больше, чем в ней есть, — с учётом пропилов."""
    for board in plan.boards:
        assert board.used_mm <= board.length_mm + 1e-9
        assert board.offcut_mm >= -1e-9


def test_kerf_eats_length_between_cuts() -> None:
    """Пропил между рейками входит в длину: две по метру в двухметровую не лезут."""
    tight = nest(_rails(1000.0, 1000.0), lengths=(2000.0,), kerf_mm=KERF, tries=1)
    assert len(tight.boards) == 2

    loose = nest(_rails(1000.0, 1000.0), lengths=(2000.0,), kerf_mm=0.0, tries=1)
    assert len(loose.boards) == 1


def test_one_board_type_per_species_and_thickness() -> None:
    """Породы и толщины не смешиваются: это разный товар, а не разный кусок."""
    items = (
        Demand("A1", "maple_hard", 40.0, 500.0),
        Demand("A2", "walnut_black", 40.0, 500.0),
        Demand("A3", "maple_hard", 20.0, 500.0),
    )
    plan = nest(items, lengths=(2000.0,), kerf_mm=KERF, tries=1)
    assert len(plan.boards) == 3
    for board in plan.boards:
        kinds = {(part.species, part.thickness_mm) for part in board.parts}
        assert len(kinds) == 1


def test_shopping_list_counts_boards(plan) -> None:
    """Список в магазин перечисляет товар и штуки, а не отдельные доски."""
    total = sum(count for *_, count in plan.shopping_list)
    assert total == len(plan.boards)


def test_search_is_never_worse_than_plain_ffd() -> None:
    """Локальный поиск не имеет права ухудшить жадный план.

    Это и есть его контракт: FFD — нижняя планка, поиск только подчищает.
    Гарантия важнее выигрыша — план, который иногда хуже очевидного, доверия
    не заслуживает, каким бы хорошим он ни был в среднем.
    """
    listing = cut_list(build("chevron").program)
    greedy = nest_stock(listing, tries=1)
    searched = nest_stock(listing, tries=200)
    assert searched.total_length_mm <= greedy.total_length_mm


def test_search_actually_wins_somewhere() -> None:
    """Случай, на котором поиск обыгрывает FFD, — иначе он был бы украшением.

    Набор найден перебором случайных задач: на таких длинах жадность
    расходует пять досок, а перестановка укладывается в четыре. Первая
    редакция поиска этот случай не брала: она перемешивала рейки, но тут же
    пересортировывала их по убыванию, и переставлялись только равные по длине,
    то есть взаимозаменяемые. Тест держит именно это — что соседство ломает
    сам порядок убывания.
    """
    items = _rails(1000, 760, 750, 720, 710, 690, 630, 610, 570, 530, 340, 300)
    greedy = nest(items, lengths=(2000.0,), kerf_mm=KERF, tries=1, seed=1)
    searched = nest(items, lengths=(2000.0,), kerf_mm=KERF, tries=300, seed=1)

    assert len(greedy.boards) == 5
    assert len(searched.boards) == 4
    assert searched.improvements >= 1


def test_the_same_seed_gives_the_same_plan() -> None:
    """План воспроизводим: тот же сид — тот же раскрой."""
    items = _rails(1000, 760, 750, 720, 710, 690, 630, 610, 570, 530, 340, 300)
    first = nest(items, lengths=(2000.0,), kerf_mm=KERF, tries=120, seed=5)
    second = nest(items, lengths=(2000.0,), kerf_mm=KERF, tries=120, seed=5)
    assert first.boards == second.boards


def test_measured_lengths_are_chosen_not_assumed() -> None:
    """Мерная длина выбирается по расходу, а не берётся первая попавшаяся.

    Рейка 1.9 м: из двухметровой доски выходит одна с обрезком 100 мм,
    из четырёхметровой — тоже одна, но обрезок 2.1 м. Выбор очевиден,
    и он должен быть сделан.
    """
    plan = nest(_rails(1900.0), lengths=STANDARD_LENGTHS_MM, kerf_mm=KERF, tries=1)
    assert plan.boards[0].length_mm == 2000.0


def test_rail_longer_than_any_board_is_reported() -> None:
    """Рейка длиннее любой мерной доски — разговор, а не молчаливый провал."""
    with pytest.raises(ValueError, match="не выходит ни из одной мерной доски"):
        nest(_rails(5000.0), lengths=(2000.0, 3000.0), kerf_mm=KERF, tries=1)


def test_empty_order_is_reported() -> None:
    """Пустой заказ — ошибка вызова, а не план из нуля досок."""
    with pytest.raises(ValueError, match="нечего кроить"):
        nest((), tries=1)


def test_budget_stops_the_search_and_says_so() -> None:
    """Кончился бюджет — план всё равно годен, и об этом сказано прямо."""
    items = _rails(*[float(700 + index * 7) for index in range(40)])
    plan = nest(items, lengths=(2000.0,), kerf_mm=KERF, tries=10_000, budget_s=0.05)
    assert plan.stopped_early
    assert plan.tries < 10_000
    assert sum(len(board.parts) for board in plan.boards) == len(items)


def test_offcut_share_is_reported(plan) -> None:
    """Доля обрезков считается от метража закупки и лежит в разумных пределах."""
    assert 0.0 <= plan.offcut_share < 1.0
    assert plan.offcut_mm == pytest.approx(
        plan.total_length_mm - sum(board.used_mm for board in plan.boards)
    )
