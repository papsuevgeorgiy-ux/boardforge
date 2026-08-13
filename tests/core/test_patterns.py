"""Ёлочка и шеврон: сходимость на стыках, а не правдоподобие на превью.

Проверяем породу по обе стороны каждого шва. Совпала по всей высоте — узор
сошёлся; разошлась на полшага — это ёлочка, и она обязана расходиться именно
так, а не как попало.
"""

import math

import pytest

from boardforge.core.geometry import assemble, glue, slice_part, stand_on_end
from boardforge.core.ops import Assemble, Cut, Glue, PieceRef, Strip
from boardforge.core.patterns import StripedPanel, chevron, herringbone
from boardforge.core.piece import Part
from boardforge.core.program import Program

STEP_MM = 40.0
ANGLE_DEG = 45.0
PROBE_MM = 0.4

PANEL = StripedPanel(
    species=("maple_hard", "walnut_black", "cherry"),
    strip_width_mm=40.0,
    board_height_mm=40.0,
    column_width_mm=20.0,
    columns=14,
)


def _seam_samples(board: Part, step_mm: float) -> list[tuple[float, str, str]]:
    """Породы по обе стороны каждого шва там, где материал есть с обеих сторон."""
    xmin, ymin, xmax, ymax = board.bounds
    samples: list[tuple[float, str, str]] = []
    seam = xmin + step_mm
    while seam < xmax - 1e-9:
        y = ymin + 1.0
        while y < ymax:
            left = board.species_at(seam - PROBE_MM, y)
            right = board.species_at(seam + PROBE_MM, y)
            if left is not None and right is not None:
                samples.append((y, left, right))
            y += 2.0
        seam += step_mm
    return samples


def _first_transition(board: Part, x: float) -> tuple[float, str, str] | None:
    """Первая смена породы на вертикали: высота и какая пара пород сменилась.

    Пара нужна, чтобы на двух вертикалях мерить наклон **одной и той же**
    породной линии, а не двух разных.
    """
    _, ymin, _, ymax = board.bounds
    previous: tuple[float, str] | None = None
    y = ymin + 0.5
    while y < ymax:
        species = board.species_at(x, y)
        if species is not None:
            if previous is not None and species != previous[1]:
                low, high = previous[0], y
                while high - low > 1e-4:
                    middle = (low + high) / 2
                    if board.species_at(x, middle) == previous[1]:
                        low = middle
                    else:
                        high = middle
                return (high, previous[1], species)
            previous = (y, species)
        y += 2.0
    return None


def test_chevron_matches_species_across_every_seam() -> None:
    """Шеврон: по обе стороны каждого шва одна и та же порода."""
    board = chevron(PANEL, angle_deg=ANGLE_DEG, step_mm=STEP_MM).apply()
    samples = _seam_samples(board, STEP_MM)

    assert len(samples) > 200, f"проб слишком мало ({len(samples)}), тест ничего не ловит"
    mismatched = [(y, left, right) for y, left, right in samples if left != right]
    assert not mismatched, mismatched[:5]


def test_herringbone_breaks_the_seam_on_purpose() -> None:
    """Ёлочка: тот же шов, но породы разъехались — это её отличие от шеврона."""
    board = herringbone(PANEL, angle_deg=ANGLE_DEG, step_mm=STEP_MM).apply()
    samples = _seam_samples(board, STEP_MM)

    assert len(samples) > 200
    mismatched = [1 for _, left, right in samples if left != right]
    assert len(mismatched) > len(samples) / 5, (
        f"разошлось всего {len(mismatched)} проб из {len(samples)} — "
        "это не ёлочка, а шеврон со сбитой фазой"
    )


def test_chevron_alternates_the_slant() -> None:
    """Соседние полосы наклонены встречно — иначе это не V, а просто полосы."""
    board = chevron(PANEL, angle_deg=ANGLE_DEG, step_mm=STEP_MM).apply()
    xmin, _, xmax, _ = board.bounds

    margin = 2.0
    span = STEP_MM - 2 * margin
    expected = span * math.tan(math.radians(ANGLE_DEG))

    drifts: list[float] = []
    left_edge = xmin
    while left_edge + STEP_MM < xmax + 1e-9:
        near = _first_transition(board, left_edge + margin)
        far = _first_transition(board, left_edge + STEP_MM - margin)
        # Меряем наклон только там, где на обеих вертикалях поймана одна
        # и та же породная линия: у краёв щита полосы обрезаны клином.
        if near is not None and far is not None and near[1:] == far[1:]:
            drifts.append(far[0] - near[0])
        left_edge += STEP_MM

    assert len(drifts) >= 4, drifts
    for drift in drifts:
        # Допуск — точность бисекции в `_first_transition`, а не машинный ноль.
        assert abs(drift) == pytest.approx(expected, abs=1e-3), drifts
    for previous, current in zip(drifts, drifts[1:], strict=False):
        assert previous * current < 0, f"наклон не сменился на встречный: {drifts}"


def test_herringbone_differs_from_chevron_by_half_a_pitch() -> None:
    """Ёлочка — тот же шеврон, сдвинутый ровно на полшага породных линий."""
    common = {"angle_deg": ANGLE_DEG, "step_mm": STEP_MM}
    straight = chevron(PANEL, **common).operations[-1]
    broken = herringbone(PANEL, **common).operations[-1]

    pitch = PANEL.strip_width_mm / abs(math.cos(math.radians(ANGLE_DEG)))
    period = len(PANEL.species) * pitch
    deltas = [
        after - before
        for before, after, mirrored in zip(
            straight.offsets_mm, broken.offsets_mm, broken.flipped, strict=True
        )
        if mirrored
    ]

    assert deltas
    for delta in deltas:
        # Сдвиг определён по модулю периода узора, поэтому разницу сравниваем
        # тоже по модулю: −141.4 и +28.3 при периоде 169.7 — одна и та же точка.
        assert delta % period == pytest.approx(pitch / 2, abs=1e-6)
    assert all(
        after == before
        for before, after, mirrored in zip(
            straight.offsets_mm, broken.offsets_mm, broken.flipped, strict=True
        )
        if not mirrored
    )


def _single_cycle_panel() -> StripedPanel:
    """Тот же щит, но породный цикл в нём один — сдвигу некуда переноситься."""
    return StripedPanel(
        species=PANEL.species,
        strip_width_mm=PANEL.strip_width_mm,
        board_height_mm=PANEL.board_height_mm,
        column_width_mm=PANEL.column_width_mm,
        columns=PANEL.columns,
        repeats=1,
    )


def test_single_species_cycle_is_reported_before_anything_is_drawn() -> None:
    """Нехватку породных циклов ловит валидатор, а не глаз на превью.

    Программа при этом исполнима: она соберётся, просто с дырами на швах.
    Ровно поэтому проверка обязана быть статической — исполнение молчит.
    """
    program = chevron(_single_cycle_panel(), angle_deg=ANGLE_DEG, step_mm=STEP_MM)

    warnings = [
        issue
        for issue in program.validate()
        if issue.level == "warning" and "породным циклом" in issue.message
    ]
    assert len(warnings) == 1, [str(i) for i in program.validate()]

    complaint = warnings[0]
    assert complaint.index is not None
    assert isinstance(program.operations[complaint.index], Glue)
    assert "хотя бы дважды" in complaint.message

    assert not program.errors, "это предупреждение, а не запрет"
    assert program.apply().pieces, "программа обязана оставаться исполнимой"


def test_repeated_species_cycle_is_not_reported() -> None:
    """На здоровом щите замечание молчит — иначе оно ничего не значит."""
    program = chevron(PANEL, angle_deg=ANGLE_DEG, step_mm=STEP_MM)
    assert not [
        issue for issue in program.validate() if "породным циклом" in issue.message
    ]


def test_orthogonal_boards_are_left_alone(checkerboard: Program) -> None:
    """Шахматке цикл не нужен: там нет ни угла, ни зеркала."""
    assert not [
        issue for issue in checkerboard.validate() if "породным циклом" in issue.message
    ]


def test_mirror_leaves_a_stood_slat_alone() -> None:
    """Р21 обратно совместим: у стоящей на торце полосы отражение — тождество.

    Ровно тот объект, который `Assemble` получает в ортогональных узорах:
    ячейки идут вдоль полосы, поперёк неё — одна. Отражение поперёк такой ряд
    не трогает, как и обещал Р7.
    """
    panel = glue((Strip("maple_hard", 30.0), Strip("cherry", 50.0)), 200.0, 20.0, "A")
    slat = stand_on_end(slice_part(panel, 90.0, 40.0, along_strip=True).parts[0], 40.0)

    plain = assemble([slat], (False,), (0.0,), (False,))
    turned = assemble([slat], (False,), (0.0,), (True,))

    assert len(plain.pieces) == len(turned.pieces) == 2
    for before, after in zip(plain.pieces, turned.pieces, strict=True):
        assert before.polygon.equals(after.polygon)
        assert before.species == after.species


def test_mirror_reverses_a_glued_panel() -> None:
    """А у щита, где рейки идут поперёк, порядок реек отражение переставляет.

    Это не противоречие с Р7: тот говорил про ряд, а не про щит. Перевернуть
    лежащий плашмя щит вокруг длинной оси действительно меняет порядок реек,
    если смотреть сверху.
    """
    panel = glue((Strip("maple_hard", 30.0), Strip("cherry", 50.0)), 200.0, 20.0, "A")

    plain = assemble([panel], (False,), (0.0,), (False,))
    turned = assemble([panel], (False,), (0.0,), (True,))

    assert plain.species_at(15.0, 100.0) == "maple_hard"
    assert turned.species_at(15.0, 100.0) == "cherry"
    assert plain.area_mm2 == pytest.approx(turned.area_mm2)


def test_mirror_reverses_a_slanted_cell() -> None:
    """У наклонной ячейки отражение не тождественно — ради этого Р21 и нужен."""
    panel = glue((Strip("maple_hard", 60.0), Strip("cherry", 60.0)), 200.0, 20.0, "A")
    band = slice_part(panel, 45.0, 40.0).parts[2]

    plain = assemble([band], (False,), (0.0,), (False,))
    turned = assemble([band], (False,), (0.0,), (True,))

    assert not plain.pieces[0].polygon.equals(turned.pieces[0].polygon)
    assert plain.area_mm2 == pytest.approx(turned.area_mm2)


def _three_glue_ups() -> Program:
    """Цепочка `Cut → Assemble → Cut → Assemble`: три склейки в общем виде.

    Полосатый щит режется под углом и собирается, затем режется ещё раз
    поперёк первого реза и собирается снова. Отдельной операции для третьей
    склейки не нужно (Р2) — но проверено это не было.
    """
    panel = StripedPanel(
        species=("maple_hard", "walnut_black", "cherry"),
        columns=12,
        repeats=3,
    )
    # Без обрезки: тест про третью склейку, а не про размер щита — обрезанный
    # щит даёт меньше полос, и номера деталей поехали бы.
    first = chevron(panel, angle_deg=60.0, step_mm=45.0, square=False)
    picks = tuple(PieceRef("BOARD", index) for index in range(3))
    return Program(
        operations=(
            *first.operations,
            Cut(source="BOARD", angle_deg=110.0, step_mm=50.0),
            Assemble(
                id="THIRD",
                pieces=picks,
                reversed=(False, True, False),
                offsets_mm=(0.0, 12.0, -8.0),
            ),
        )
    )


def test_third_glue_up_passes_the_validator() -> None:
    """Третья склейка законна: отдельной операции для неё не заводится."""
    program = _three_glue_ups()
    assert not program.errors, [str(issue) for issue in program.errors]


def test_third_glue_up_runs_and_conserves_area() -> None:
    """И исполняется: площадь щита равна сумме площадей взятых деталей."""
    program = _three_glue_ups()
    execution = program.run()

    chosen = execution.billets["BOARD"][:3]
    assert execution.board.area_mm2 == pytest.approx(
        sum(part.area_mm2 for part in chosen), rel=1e-6
    )
    assert len(execution.cuts) == 3, [cut.angle_deg for cut in execution.cuts]
    assert [cut.angle_deg for cut in execution.cuts] == [90.0, 60.0, 110.0]


def test_third_glue_up_keeps_origin_through_both_cuts() -> None:
    """Происхождение переживает обе пересборки — иначе текстура рассыплется."""
    board = _three_glue_ups().apply()
    assert {piece.origin.billet for piece in board.pieces} == {"A"}
    assert len({piece.origin.strip_key for piece in board.pieces}) > 1
