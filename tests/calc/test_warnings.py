"""Предупреждения о породах и калибровка порога по короблению.

Главный тест здесь — не «предупреждение появляется», а тот, что держит порог
осмысленным с обеих сторон: ниже — оно срабатывает почти везде и его перестают
читать, выше — молчит и там, где надо было сказать.
"""

import pytest

from boardforge.calc.warnings import (
    MAX_SHRINKAGE_GAP,
    WoodLimits,
    shrinkage_issues,
    species_issues,
)
from boardforge.core.library import LIBRARY, build
from boardforge.core.species import load_species


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


def _worst_gap(program, catalogue) -> float:
    """Наибольшая разница усушки среди соседей по щиту."""
    from boardforge.core.ops import Glue

    worst = 0.0
    for op in program.operations:
        if not isinstance(op, Glue):
            continue
        species = [strip.species for strip in op.strips]
        for first, second in zip(species, species[1:], strict=False):
            if first in catalogue and second in catalogue:
                worst = max(
                    worst,
                    abs(
                        catalogue[first].shrinkage_tangential
                        - catalogue[second].shrinkage_tangential
                    ),
                )
    return worst


def test_maple_and_walnut_never_complain(catalogue) -> None:
    """Клён с орехом — якорь порога, и ругаться на них нельзя.

    На этой паре стоит половина торцевых досок, разница усушки у неё 2.1.
    Предупреждение, которое срабатывает здесь, обесценивает себя целиком,
    поэтому порог обязан лежать выше — это и проверяется, а не то, что 3 > 2.1.
    """
    gap = abs(
        catalogue["maple_hard"].shrinkage_tangential
        - catalogue["walnut_black"].shrinkage_tangential
    )
    assert gap < MAX_SHRINKAGE_GAP
    program = build("checkerboard", species=("maple_hard", "walnut_black")).program
    assert not shrinkage_issues(program, catalogue)


def test_threshold_fires_on_a_minority_of_the_library(catalogue) -> None:
    """Порог срабатывает на меньшинстве узоров библиотеки.

    Верхняя граница — чтобы предупреждение не стало фоном, нижняя — чтобы оно
    вообще звучало. Числа замерены на дне 5: при пороге 3.0 срабатывает 3 узора
    из 14, при 2.0 — одиннадцать, при 3.5 — один.
    """
    noisy = [name for name in LIBRARY if shrinkage_issues(build(name).program, catalogue)]
    assert 1 <= len(noisy) <= len(LIBRARY) // 3, f"срабатывает на {sorted(noisy)}"


def test_lower_threshold_would_flood_the_list(catalogue) -> None:
    """Порог 2.0 залил бы список: так проверяется, что 3.0 выбран, а не угадан."""
    flooded = sum(
        1
        for name in LIBRARY
        if shrinkage_issues(build(name).program, catalogue, WoodLimits(2.0))
    )
    assert flooded > len(LIBRARY) * 0.7


def test_cherry_and_hornbeam_do_complain(catalogue) -> None:
    """Вишня с грабом — разница 4.4, и об этом надо сказать."""
    program = build("checkerboard", species=("cherry", "hornbeam")).program
    issues = shrinkage_issues(program, catalogue)
    assert len(issues) == 1
    assert "Вишня" in issues[0].message
    assert "Граб" in issues[0].message
    assert issues[0].level == "warning"


def test_warning_points_at_the_glue_up(catalogue) -> None:
    """Замечание привязано к операции склейки — там и правят состав щита."""
    program = build("checkerboard", species=("cherry", "hornbeam")).program
    issue = shrinkage_issues(program, catalogue)[0]
    assert issue.index is not None
    assert type(program.operations[issue.index]).__name__ == "Glue"


def test_each_pair_is_named_once(catalogue) -> None:
    """Пара повторяется в щите десяток раз, а замечание про неё одно."""
    program = build("stripes", species=("cherry", "hornbeam", "padauk")).program
    issues = shrinkage_issues(program, catalogue)
    messages = [issue.message for issue in issues]
    assert len(messages) == len(set(messages))


def test_same_species_side_by_side_is_silent(catalogue) -> None:
    """Порода сама с собой усыхает одинаково — жаловаться не на что."""
    program = build("stripes", species=("oak", "oak")).program
    assert not shrinkage_issues(program, catalogue)


def test_open_pores_are_reported(catalogue) -> None:
    """Дуб и ясень — крупные поры, для разделочной поверхности не годятся."""
    program = build("checkerboard", species=("oak", "maple_hard")).program
    issues = species_issues(program, catalogue)
    assert any("поры" in issue.message for issue in issues)


def test_allergens_are_reported(catalogue) -> None:
    """Венге и амарант — пыль раздражает; предупреждение про цех, а не про доску."""
    program = build("checkerboard", species=("wenge", "maple_hard")).program
    issues = species_issues(program, catalogue)
    assert any("респиратор" in issue.message for issue in issues)


def test_fading_species_are_reported(catalogue) -> None:
    """Падук буреет, и покупателю об этом стоит знать заранее."""
    program = build("checkerboard", species=("padauk", "maple_hard")).program
    issues = species_issues(program, catalogue)
    assert any("цвет со временем" in issue.message for issue in issues)


def test_one_issue_per_property_not_per_species(catalogue) -> None:
    """Три аллергена дают одно замечание, а не три.

    Список замечаний читают, пока он короткий. Три строки об одном и том же —
    самый быстрый способ добиться, чтобы его перестали читать.
    """
    program = build("stripes", species=("wenge", "purpleheart", "maple_hard")).program
    issues = species_issues(program, catalogue)
    assert sum(1 for issue in issues if "респиратор" in issue.message) == 1


def test_plain_maple_board_says_nothing(catalogue) -> None:
    """Доска из клёна с орехом не вызывает ни одного замечания о породах."""
    program = build("checkerboard", species=("maple_hard", "walnut_black")).program
    assert not species_issues(program, catalogue)


def test_species_issues_include_shrinkage(catalogue) -> None:
    """Общий список содержит и разницу усушки — отдельно её звать не надо."""
    program = build("checkerboard", species=("cherry", "hornbeam")).program
    assert len(species_issues(program, catalogue)) >= len(
        shrinkage_issues(program, catalogue)
    )


def test_threshold_must_be_positive() -> None:
    """Нулевой порог сделал бы предупреждением любую пару разных пород."""
    with pytest.raises(ValueError, match="порог"):
        WoodLimits(0.0)


def test_unknown_species_does_not_crash(catalogue) -> None:
    """Порода вне справочника молчит, а не роняет расчёт.

    Справочник подменяем: чужой файл может знать не все породы программы,
    и предупреждения — не то место, где об этом надо падать.
    """
    program = build("checkerboard", species=("cherry", "hornbeam")).program
    assert shrinkage_issues(program, {"cherry": catalogue["cherry"]}) == []
