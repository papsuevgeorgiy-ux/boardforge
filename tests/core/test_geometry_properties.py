"""Свойства резов при произвольных углах и шагах.

Страховка перед Днём 3, где появятся ёлочка, шеврон и кубы: резать начнут под
углами, которые в примерах не встречались. Проверяем не конкретные числа,
а сохранение материала — дерево не берётся из ниоткуда и не пропадает.
"""

from collections import defaultdict

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from shapely.affinity import rotate
from shapely.geometry import box

from boardforge.core.geometry import assemble, crop, glue, slice_part
from boardforge.core.ops import Strip
from boardforge.core.piece import Part

SPECIES = ("maple_hard", "walnut_black", "cherry", "oak")

TOLERANCE = {"rel": 1e-6}

panels = st.builds(
    glue,
    strips=st.lists(
        st.builds(
            Strip,
            species=st.sampled_from(SPECIES),
            width_mm=st.floats(10.0, 100.0),
        ),
        min_size=1,
        max_size=5,
    ).map(tuple),
    length_mm=st.floats(50.0, 600.0),
    thickness_mm=st.floats(10.0, 60.0),
)

angles = st.floats(1.0, 179.0)
steps = st.floats(20.0, 200.0)

PROPERTY_SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


def _areas_by_species(parts: list[Part]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for part in parts:
        for piece in part.pieces:
            totals[piece.species] += piece.area_mm2
    return dict(totals)


def _tail_areas(part: Part, angle_deg: float, remainder_mm: float) -> dict[str, float]:
    """Площади по породам в куске, который короче шага и уходит в отход."""
    totals: dict[str, float] = defaultdict(float)
    if remainder_mm <= 0:
        return dict(totals)

    turned = [
        (rotate(piece.polygon, -angle_deg, origin=(0, 0)), piece.species)
        for piece in part.pieces
    ]
    bounds = [polygon.bounds for polygon, _ in turned]
    xmax = max(b[2] for b in bounds)
    ymin = min(b[1] for b in bounds)
    ymax = max(b[3] for b in bounds)

    tail = box(xmax - remainder_mm, ymin - 1.0, xmax + 1.0, ymax + 1.0)
    for polygon, species in turned:
        totals[species] += polygon.intersection(tail).area
    return dict(totals)


@given(part=panels, angle=angles, step=steps)
@PROPERTY_SETTINGS
def test_cut_conserves_area(part: Part, angle: float, step: float) -> None:
    """Сумма площадей деталей плюс отход равна площади входа."""
    try:
        parts, remainder = slice_part(part, angle, step)
    except ValueError:
        assume(False)

    kept = sum(item.area_mm2 for item in parts)
    tail = sum(_tail_areas(part, angle, remainder).values())
    assert kept + tail == pytest.approx(part.area_mm2, **TOLERANCE)


@given(part=panels, angle=angles, step=steps)
@PROPERTY_SETTINGS
def test_cut_conserves_each_species(part: Part, angle: float, step: float) -> None:
    """Порода не подменяется: сохраняется площадь каждой по отдельности."""
    try:
        parts, remainder = slice_part(part, angle, step)
    except ValueError:
        assume(False)

    kept = _areas_by_species(parts)
    tail = _tail_areas(part, angle, remainder)
    expected = _areas_by_species([part])

    assert set(kept) <= set(expected)
    for species, total in expected.items():
        got = kept.get(species, 0.0) + tail.get(species, 0.0)
        assert got == pytest.approx(total, **TOLERANCE)


@given(part=panels, angle=angles, step=steps)
@PROPERTY_SETTINGS
def test_cut_remainder_is_shorter_than_step(
    part: Part, angle: float, step: float
) -> None:
    """Остаток по определению короче шага — иначе из него вышла бы ещё деталь."""
    try:
        _, remainder = slice_part(part, angle, step)
    except ValueError:
        assume(False)

    assert 0.0 <= remainder < step


@given(part=panels, angle=angles, step=steps)
@PROPERTY_SETTINGS
def test_cut_pieces_fit_the_step(part: Part, angle: float, step: float) -> None:
    """Ни одна деталь не шире шага реза."""
    try:
        parts, _ = slice_part(part, angle, step)
    except ValueError:
        assume(False)

    for item in parts:
        assert item.width_mm <= step * (1 + 1e-9)


@given(part=panels, angle=angles, step=steps)
@PROPERTY_SETTINGS
def test_assemble_conserves_area(part: Part, angle: float, step: float) -> None:
    """Склейка ничего не теряет: площадь щита — сумма площадей деталей."""
    try:
        parts, _ = slice_part(part, angle, step)
    except ValueError:
        assume(False)

    count = len(parts)
    board = assemble(parts, (False,) * count, (0.0,) * count)
    assert board.area_mm2 == pytest.approx(
        sum(item.area_mm2 for item in parts), **TOLERANCE
    )


@given(part=panels, angle=angles, step=steps, share=st.floats(0.0, 0.4))
@PROPERTY_SETTINGS
def test_crop_never_grows_the_board(
    part: Part, angle: float, step: float, share: float
) -> None:
    """Обрезка только убавляет: щит после неё не может стать больше."""
    try:
        parts, _ = slice_part(part, angle, step)
    except ValueError:
        assume(False)

    count = len(parts)
    board = assemble(parts, (False,) * count, (0.0,) * count)
    margin = board.length_mm * share / 2
    cropped = crop(board, left=0.0, right=0.0, top=margin, bottom=margin)
    assert cropped.area_mm2 <= board.area_mm2 * (1 + 1e-9)
