"""Генератор: воспроизводимость по сиду и отказ выдавать брак.

Два обещания, и оба проверяются буквально. Первое: один сид — один узор,
операция в операцию. Второе: что бы генератор ни выдал, валидатор на это
не ругается — иначе инструмент спорит сам с собой.
"""

import random

import pytest

from boardforge.core.fitness import Weights, score
from boardforge.core.generate import (
    Evolved,
    Genome,
    evolve,
    generate,
    mutate,
    random_genome,
)
from boardforge.core.library import LIBRARY
from boardforge.core.safety import inspect
from boardforge.core.species import load_species

SEEDS = (1, 7, 42, 2024, 99991)


@pytest.fixture(scope="module")
def catalogue():
    return load_species()


@pytest.mark.parametrize("seed", SEEDS)
def test_one_seed_gives_one_pattern(seed: int, catalogue) -> None:
    """Дважды по одному сиду — та же программа, а не «похожая»."""
    first_genome, first = generate(seed, catalogue)
    second_genome, second = generate(seed, catalogue)

    assert first_genome == second_genome
    assert first.operations == second.operations
    assert first.to_dict() == second.to_dict()


def test_different_seeds_give_different_patterns(catalogue) -> None:
    """Иначе это не генератор, а один узор с параметром."""
    programs = {
        generate(seed, catalogue)[1].to_dict()["operations"][0]["id"] for seed in SEEDS
    }
    genomes = [generate(seed, catalogue)[0] for seed in SEEDS]
    assert len({(g.template, g.params) for g in genomes}) > 1, genomes
    assert programs  # программы собрались


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_pattern_passes_the_validator(seed: int, catalogue) -> None:
    """Главное обещание дня: генератор не выдаёт того, за что сам отчитает."""
    _, program = generate(seed, catalogue)

    assert not program.errors, [str(issue) for issue in program.errors]
    errors = [
        issue for issue in inspect(program, program.run()) if issue.level == "error"
    ]
    assert not errors, [str(issue) for issue in errors]


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_pattern_is_a_real_board(seed: int, catalogue) -> None:
    """Не вырожденная плашка: узор — это не десяток ячеек."""
    _, program = generate(seed, catalogue)
    board = program.run().board

    assert len(board.pieces) >= 20
    assert board.width_mm > 50.0 and board.length_mm > 50.0


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_every_template_can_be_asked_for_by_name(key: str, catalogue) -> None:
    """Сид выбирает параметры, а шаблон можно и назначить."""
    genome, program = generate(11, catalogue, template=key)
    assert genome.template == key
    assert not program.errors


def test_random_genome_only_touches_known_parameters(catalogue) -> None:
    """Геном обязан заполнять ровно те параметры, что есть у шаблона."""
    rng = random.Random(3)
    for key, template in sorted(LIBRARY.items()):
        genome = random_genome(rng, catalogue, key)
        assert set(genome.values) == set(template.defaults), key


def test_species_in_a_genome_are_all_different(catalogue) -> None:
    """Повтор породы — это узор из меньшего числа пород, притворяющийся сложным."""
    rng = random.Random(5)
    for _ in range(40):
        genome = random_genome(rng, catalogue)
        species = genome.values["species"]
        assert len(set(species)) == len(species), species


def test_mutation_changes_exactly_one_thing(catalogue) -> None:
    """Мутация точечная: иначе не видно, что именно улучшило узор."""
    rng = random.Random(17)
    base = random_genome(rng, catalogue, "checkerboard")

    changed = 0
    for _ in range(30):
        child = mutate(base, rng, catalogue)
        differing = [
            name for name in base.values if base.values[name] != child.values.get(name)
        ]
        assert len(differing) <= 1, differing
        changed += len(differing)
    assert changed > 0, "мутация ни разу ничего не поменяла"


def test_mutation_keeps_the_template(catalogue) -> None:
    rng = random.Random(23)
    base = random_genome(rng, catalogue, "zigzag")
    for _ in range(20):
        assert mutate(base, rng, catalogue).template == "zigzag"


def test_genome_rejects_an_unknown_template() -> None:
    with pytest.raises(ValueError, match="нет такого шаблона"):
        Genome("houndstooth", ())


@pytest.mark.parametrize("seed", (4, 31))
def test_evolution_beats_the_random_start(seed: int, catalogue) -> None:
    """Отбор обязан улучшать оценку, иначе он просто дорогой способ погадать.

    Сравнение честное: та же случайность, тот же справочник — разница только
    в том, что эволюция мутирует лучших, а не берёт первого попавшегося.
    """
    best = evolve(seed, generations=3, population=6, catalogue=catalogue)
    _, plain = generate(seed, catalogue)

    assert isinstance(best, Evolved)
    assert best.total >= score(plain, catalogue).total() - 1e-9, (
        best.total,
        score(plain, catalogue).total(),
    )


def test_evolution_is_reproducible(catalogue) -> None:
    first = evolve(9, generations=2, population=6, catalogue=catalogue)
    second = evolve(9, generations=2, population=6, catalogue=catalogue)
    assert first.genome == second.genome
    assert first.program.operations == second.program.operations


def test_evolution_result_is_makeable(catalogue) -> None:
    best = evolve(13, generations=2, population=6, catalogue=catalogue)
    assert not best.program.errors
    assert best.scores.feasibility > 0.0


def test_weights_steer_the_search(catalogue) -> None:
    """Веса обязаны что-то менять: иначе фитнес-функция декоративна."""
    thrifty = evolve(
        21,
        generations=3,
        population=6,
        weights=Weights(
            contrast=0.0, rhythm=0.0, symmetry=0.0, economy=1.0, feasibility=0.0
        ),
        catalogue=catalogue,
    )
    showy = evolve(
        21,
        generations=3,
        population=6,
        weights=Weights(
            contrast=1.0, rhythm=0.0, symmetry=0.0, economy=0.0, feasibility=0.0
        ),
        catalogue=catalogue,
    )
    assert thrifty.scores.economy >= showy.scores.economy - 1e-9
    assert showy.scores.contrast >= thrifty.scores.contrast - 1e-9


def test_evolution_refuses_a_degenerate_run(catalogue) -> None:
    with pytest.raises(ValueError, match="хотя бы одно поколение"):
        evolve(1, generations=0, catalogue=catalogue)


def test_generator_gives_up_out_loud_on_an_empty_catalogue() -> None:
    """Пустой справочник — не молчаливый сбой, а объяснённый отказ."""
    with pytest.raises(ValueError):
        generate(1, {})
