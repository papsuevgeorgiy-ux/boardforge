"""Процедурная текстура торца.

Главное здесь одно: сид берётся из происхождения ячейки, а не из её места
в доске. Отсюда всё остальное — соседние срезы одной рейки почти совпадают,
разные рейки не совпадают, а перестановки узора рисунок дерева не трогают.
"""

import math

import pytest

from boardforge.core.piece import Orientation, Origin
from boardforge.render.texture import (
    DRIFT_NODE_MM,
    RingField,
    ray_lines,
    ring_arcs,
    ring_field,
)

MAPLE = "maple_hard"
CELL_MM = 40.0
RING_MM = 2.2
RAY_WIDTH_MM = 0.2
RADIUS_MM = CELL_MM * math.sqrt(2.0) / 2.0

STRIPS = range(24)


def field(strip: int, offset_mm: float) -> RingField:
    return ring_field(Origin("A", strip, offset_mm, MAPLE), RING_MM, CELL_MM)


def _distance(first: RingField, second: RingField) -> float:
    return math.hypot(first.pith_x - second.pith_x, first.pith_y - second.pith_y)


def test_same_origin_gives_the_same_field() -> None:
    """Рендер детерминирован: то же происхождение — то же поле колец."""
    assert field(3, 120.0) == field(3, 120.0)


def test_neighbouring_slices_almost_coincide() -> None:
    """Соседние срезы одной рейки — почти один и тот же рисунок.

    Это требование к текстуре, а не украшение: столбец доски физически собран
    из последовательных срезов одной рейки, и разъехавшийся рисунок сразу
    выдаёт, что доска нарисована, а не склеена.
    """
    for strip in STRIPS:
        near = _distance(field(strip, 200.0), field(strip, 200.0 + CELL_MM))
        assert near < 0.1 * CELL_MM


def test_drift_accumulates_along_the_strip() -> None:
    """Дрейф медленный, но не нулевой: далёкие срезы рейки уже различаются."""
    close = sum(_distance(field(s, 200.0), field(s, 240.0)) for s in STRIPS)
    far = sum(_distance(field(s, 200.0), field(s, 200.0 + DRIFT_NODE_MM)) for s in STRIPS)
    assert close < far / 3.0
    assert far > 0.0


def test_neighbouring_slices_keep_ring_radii() -> None:
    """Кольца соседних срезов ложатся друг на друга с точностью до полукольца."""
    for strip in STRIPS:
        first = ring_arcs(field(strip, 200.0), RADIUS_MM)
        second = ring_arcs(field(strip, 200.0 + CELL_MM), RADIUS_MM)
        assert abs(len(first) - len(second)) <= 2

        radii = [arc.radius_mm for arc in second]
        for arc in first[1:-1]:
            nearest = min(abs(arc.radius_mm - other) for other in radii)
            assert nearest < RING_MM / 2.0


def test_different_strips_look_different() -> None:
    """Рейки пилились из разных досок: общего рисунка у них нет."""
    across = [
        _distance(field(first, 200.0), field(second, 200.0))
        for first in STRIPS
        for second in STRIPS
        if first < second
    ]
    neighbour = [_distance(field(s, 200.0), field(s, 200.0 + CELL_MM)) for s in STRIPS]
    assert sum(neighbour) / len(neighbour) < 0.05 * sum(across) / len(across)


def test_billet_is_part_of_the_seed() -> None:
    """Одинаковый номер рейки в разных щитах — разные рейки."""
    first = ring_field(Origin("A", 1, 0.0, MAPLE), RING_MM, CELL_MM)
    second = ring_field(Origin("B", 1, 0.0, MAPLE), RING_MM, CELL_MM)
    assert first != second


def test_close_pith_curves_the_rings() -> None:
    """Близкая сердцевина — сильно изогнутые кольца, далёкая — почти прямые.

    Мерой кривизны служит радиус кольца против размера ячейки: у кольца
    радиусом в полметра дуга внутри ячейки от прямой не отличима.
    """
    close = RingField(0.0, 12.0, RING_MM, 0.0, ("A", 0))
    far = RingField(0.0, 900.0, RING_MM, 0.0, ("A", 0))

    close_arcs = ring_arcs(close, RADIUS_MM)
    far_arcs = ring_arcs(far, RADIUS_MM)

    assert min(arc.radius_mm for arc in close_arcs) < CELL_MM
    assert min(arc.radius_mm for arc in far_arcs) > 10 * CELL_MM


def test_arcs_stay_near_the_cell() -> None:
    """Кольцо целиком за пределами ячейки не рисуется: файл не резиновый."""
    for strip in STRIPS:
        current = field(strip, 0.0)
        for arc in ring_arcs(current, RADIUS_MM):
            gap = abs(arc.radius_mm - current.pith_distance_mm)
            assert gap <= RADIUS_MM + RING_MM


def test_rays_are_radial() -> None:
    """Лучи идут поперёк колец, то есть по радиусу от сердцевины."""
    current = field(5, 0.0)
    for line in ray_lines(current, RADIUS_MM, RAY_WIDTH_MM):
        first = math.atan2(line.y1 - current.pith_y, line.x1 - current.pith_x)
        second = math.atan2(line.y2 - current.pith_y, line.x2 - current.pith_x)
        assert first == pytest.approx(second, abs=1e-9)


def _ray_angles(current: RingField) -> list[float]:
    return [
        math.atan2(line.y1 - current.pith_y, line.x1 - current.pith_x)
        for line in ray_lines(current, RADIUS_MM, RAY_WIDTH_MM)
    ]


def _ray_length(line) -> float:
    return math.hypot(line.x2 - line.x1, line.y2 - line.y1)


def test_ray_spacing_is_irregular() -> None:
    """Шаг между лучами разный. Ровный шаг — это решётка, а не дерево.

    Решётку видно с двух метров: при отдалении регулярный узор не сливается
    в тон, а начинает муарить. Поэтому промежуток разыгрывается.
    """
    for strip in STRIPS:
        gaps = [
            abs(second - first)
            for first, second in zip(
                _ray_angles(field(strip, 0.0)),
                _ray_angles(field(strip, 0.0))[1:],
                strict=False,
            )
        ]
        if len(gaps) < 5:
            continue
        assert min(gaps) < 0.6 * max(gaps)


def test_ray_lengths_and_widths_vary() -> None:
    """Часть лучей обрывается на полпути, и толщина у них разная."""
    for strip in STRIPS:
        lines = ray_lines(field(strip, 0.0), RADIUS_MM, RAY_WIDTH_MM)
        if len(lines) < 5:
            continue
        lengths = [_ray_length(line) for line in lines]
        assert min(lengths) < 0.5 * max(lengths)
        assert len({round(line.width_mm, 6) for line in lines}) > 1


def test_ray_density_falls_with_radius() -> None:
    """Лучи расходятся веером, поэтому плотность падает от сердцевины к краю."""
    current = RingField(0.0, 0.0, RING_MM, 0.0, ("A", 7))
    lines = ray_lines(current, RADIUS_MM, RAY_WIDTH_MM)

    def ink_density(inner: float, outer: float) -> float:
        total = 0.0
        for line in lines:
            first = math.hypot(line.x1, line.y1)
            second = math.hypot(line.x2, line.y2)
            low, high = min(first, second), max(first, second)
            overlap = max(0.0, min(high, outer) - max(low, inner))
            total += overlap * line.width_mm
        return total / (math.pi * (outer**2 - inner**2))

    near = ink_density(0.15 * RADIUS_MM, 0.45 * RADIUS_MM)
    far = ink_density(0.55 * RADIUS_MM, 0.95 * RADIUS_MM)
    assert near > far


def test_rays_are_deterministic() -> None:
    """Разброс идёт от сида происхождения, а не от случайного генератора."""
    first = ray_lines(field(4, 80.0), RADIUS_MM, RAY_WIDTH_MM)
    second = ray_lines(field(4, 80.0), RADIUS_MM, RAY_WIDTH_MM)
    assert first == second


def test_neighbouring_slices_share_the_rays() -> None:
    """Разброс лучей — свойство рейки: у соседних срезов он тот же."""
    for strip in STRIPS:
        first = ray_lines(field(strip, 200.0), RADIUS_MM, RAY_WIDTH_MM)
        second = ray_lines(field(strip, 200.0 + CELL_MM), RADIUS_MM, RAY_WIDTH_MM)
        assert abs(len(first) - len(second)) <= 2
        assert [line.width_mm for line in first[:5]] == [
            line.width_mm for line in second[:5]
        ]


def test_orientation_turns_the_texture() -> None:
    """Развёрнутая деталь показывает развёрнутый рисунок.

    Кольца концентричны, поэтому поворот рисунка — это поворот сердцевины
    вокруг середины ячейки. Иначе `reversed` в `Assemble` не видно в превью.
    """
    origin = Origin("A", 2, 120.0, MAPLE)
    straight = ring_field(origin, RING_MM, CELL_MM)
    turned = ring_field(origin, RING_MM, CELL_MM, Orientation(180.0))

    assert turned.pith_x == pytest.approx(-straight.pith_x)
    assert turned.pith_y == pytest.approx(-straight.pith_y)
    assert turned.phase_mm == pytest.approx(straight.phase_mm)


def test_flip_mirrors_the_texture() -> None:
    """Переворот на другую сторону отражает рисунок поперёк продольной оси."""
    origin = Origin("A", 2, 120.0, MAPLE)
    straight = ring_field(origin, RING_MM, CELL_MM)
    flipped = ring_field(origin, RING_MM, CELL_MM, Orientation().flipped())

    assert flipped.pith_x == pytest.approx(-straight.pith_x)
    assert flipped.pith_y == pytest.approx(straight.pith_y)
    assert flipped.mirrored


def test_ring_width_must_be_positive() -> None:
    """Нулевая ширина кольца — ошибка справочника, а не бесконечный цикл."""
    with pytest.raises(ValueError, match="кольца"):
        ring_field(Origin("A", 0, 0.0, MAPLE), 0.0, CELL_MM)
