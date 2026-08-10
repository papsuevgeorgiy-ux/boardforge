"""Операции DSL: проверка аргументов и сериализация."""

import pytest

from boardforge.core.ops import (
    Assemble,
    Crop,
    Crosscut,
    Cut,
    Glue,
    StandOnEnd,
    Strip,
    op_from_dict,
    op_to_dict,
)


def test_glue_width_is_sum_of_strips() -> None:
    """Ширина щита выводится из реек, а не задаётся отдельно."""
    glue = Glue((Strip("oak", 40.0), Strip("ash", 25.0)), 600.0, 30.0)
    assert glue.width_mm == pytest.approx(65.0)


def test_empty_panel_rejected() -> None:
    """Щит без реек не бывает."""
    with pytest.raises(ValueError, match="пустым"):
        Glue((), 600.0, 30.0)


@pytest.mark.parametrize("length", [0.0, -1.0])
def test_nonpositive_length_rejected(length: float) -> None:
    """Нулевая и отрицательная длина щита отсекаются на конструкторе."""
    with pytest.raises(ValueError, match="длина щита"):
        Glue((Strip("oak", 40.0),), length, 30.0)


def test_strip_without_species_rejected() -> None:
    """Рейка без породы не пройдёт: по ней считается цвет и вес."""
    with pytest.raises(ValueError, match="порода"):
        Strip("", 40.0)


def test_crosscut_is_ninety_degrees() -> None:
    """Торцовка — частный случай реза, угол не настраивается."""
    assert Crosscut(40.0).angle_deg == 90.0


@pytest.mark.parametrize("angle", [0.0, 180.0, 200.0, -45.0])
def test_bad_cut_angle_rejected(angle: float) -> None:
    """Вырожденный угол реза не даёт полос."""
    with pytest.raises(ValueError, match="угол реза"):
        Cut(angle, 40.0)


def test_assemble_rejects_repeated_part() -> None:
    """Одну полосу нельзя вклеить в щит дважды."""
    with pytest.raises(ValueError, match="дважды"):
        Assemble(order=(0, 1, 1), reversed=(False,) * 3, offsets_mm=(0.0,) * 3)


def test_assemble_rejects_length_mismatch() -> None:
    """Флаги и сдвиги обязаны совпадать по длине с порядком деталей."""
    with pytest.raises(ValueError, match="offsets_mm"):
        Assemble(order=(0, 1), reversed=(False, False), offsets_mm=(0.0,))


def test_assemble_accepts_optional_flips() -> None:
    """Переворот на другую сторону — необязательная четвёртая степень свободы."""
    op = Assemble(order=(0, 1), reversed=(False, True), offsets_mm=(0.0, 20.0))
    assert op.flipped is None


def test_negative_crop_rejected() -> None:
    """Обрезка «в минус» — это уже не обрезка."""
    with pytest.raises(ValueError, match="обрезка"):
        Crop(left=-5.0)


@pytest.mark.parametrize(
    "op",
    [
        Glue((Strip("oak", 40.0), Strip("ash", 25.0)), 600.0, 30.0),
        Crosscut(40.0),
        StandOnEnd(),
        Cut(45.0, 30.0),
        Assemble(order=(1, 0), reversed=(False, True), offsets_mm=(0.0, 20.0)),
        Assemble(order=(0,), reversed=(False,), offsets_mm=(0.0,), flipped=(True,)),
        Crop(left=5.0, right=5.0, top=1.0, bottom=2.0),
    ],
)
def test_operation_roundtrip(op) -> None:
    """Операция переживает путь в словарь и обратно без потерь."""
    assert op_from_dict(op_to_dict(op)) == op


def test_unknown_operation_rejected() -> None:
    """Чужой JSON не подсовывает нам несуществующую операцию."""
    with pytest.raises(ValueError, match="неизвестная операция"):
        op_from_dict({"op": "Sand", "grit": 120})
