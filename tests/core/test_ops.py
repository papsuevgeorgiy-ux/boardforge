"""Операции DSL: проверка аргументов и сериализация."""

import pytest

from boardforge.core.ops import (
    Assemble,
    Crop,
    Crosscut,
    Cut,
    Glue,
    PieceRef,
    StandOnEnd,
    Strip,
    op_from_dict,
    op_to_dict,
    target_of,
)


def test_glue_width_is_sum_of_strips() -> None:
    """Ширина щита выводится из реек, а не задаётся отдельно."""
    glue = Glue("A", (Strip("oak", 40.0), Strip("ash", 25.0)), 600.0, 30.0)
    assert glue.width_mm == pytest.approx(65.0)


def test_empty_panel_rejected() -> None:
    """Щит без реек не бывает."""
    with pytest.raises(ValueError, match="пустым"):
        Glue("A", (), 600.0, 30.0)


@pytest.mark.parametrize("length", [0.0, -1.0])
def test_nonpositive_length_rejected(length: float) -> None:
    """Нулевая и отрицательная длина щита отсекаются на конструкторе."""
    with pytest.raises(ValueError, match="длина щита"):
        Glue("A", (Strip("oak", 40.0),), length, 30.0)


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_billet_name_rejected(name: str) -> None:
    """Безымянная заготовка неадресуема — её нельзя ни разрезать, ни склеить."""
    with pytest.raises(ValueError, match="имя щита"):
        Glue(name, (Strip("oak", 40.0),), 600.0, 30.0)


def test_strip_without_species_rejected() -> None:
    """Рейка без породы не пройдёт: по ней считается цвет и вес."""
    with pytest.raises(ValueError, match="порода"):
        Strip("", 40.0)


def test_crosscut_is_ninety_degrees() -> None:
    """Торцовка — частный случай реза, угол не настраивается."""
    assert Crosscut("A", 40.0).angle_deg == 90.0


@pytest.mark.parametrize("angle", [0.0, 180.0, 200.0, -45.0])
def test_bad_cut_angle_rejected(angle: float) -> None:
    """Вырожденный угол реза не даёт полос."""
    with pytest.raises(ValueError, match="угол реза"):
        Cut("A", angle, 40.0)


def test_negative_piece_index_rejected() -> None:
    """Отрицательного номера детали не бывает."""
    with pytest.raises(ValueError, match="номер детали"):
        PieceRef("A", -1)


def test_assemble_rejects_repeated_piece() -> None:
    """Одну деталь нельзя вклеить в щит дважды."""
    pieces = (PieceRef("A", 0), PieceRef("A", 1), PieceRef("A", 1))
    with pytest.raises(ValueError, match="дважды"):
        Assemble("B", pieces, (False,) * 3, (0.0,) * 3)


def test_assemble_allows_same_index_from_other_billet() -> None:
    """Деталь №0 щита A и деталь №0 щита B — разные куски дерева."""
    pieces = (PieceRef("A", 0), PieceRef("B", 0))
    op = Assemble("C", pieces, (False, False), (0.0, 0.0))
    assert op.sources == ("A", "B")


def test_assemble_rejects_length_mismatch() -> None:
    """Флаги и сдвиги обязаны совпадать по длине с числом деталей."""
    pieces = (PieceRef("A", 0), PieceRef("A", 1))
    with pytest.raises(ValueError, match="offsets_mm"):
        Assemble("B", pieces, (False, False), (0.0,))


def test_assemble_accepts_optional_flips() -> None:
    """Переворот на другую сторону — необязательная четвёртая степень свободы."""
    op = Assemble("B", (PieceRef("A", 0),), (False,), (0.0,))
    assert op.flipped is None


def test_negative_crop_rejected() -> None:
    """Обрезка «в минус» — это уже не обрезка."""
    with pytest.raises(ValueError, match="обрезка"):
        Crop("A", left=-5.0)


@pytest.mark.parametrize(
    ("op", "expected"),
    [
        (Glue("A", (Strip("oak", 40.0),), 600.0, 30.0), "A"),
        (Crosscut("A", 40.0), "A"),
        (StandOnEnd("A"), "A"),
        (Cut("A", 45.0, 30.0), "A"),
        (Assemble("B", (PieceRef("A", 0),), (False,), (0.0,)), "B"),
        (Crop("B", left=5.0), "B"),
    ],
)
def test_target_of(op, expected: str) -> None:
    """Каждая операция знает, какой заготовки она касается."""
    assert target_of(op) == expected


@pytest.mark.parametrize(
    "op",
    [
        Glue("A", (Strip("oak", 40.0), Strip("ash", 25.0)), 600.0, 30.0),
        Crosscut("A", 40.0),
        StandOnEnd("A"),
        Cut("A", 45.0, 30.0),
        Assemble(
            "B",
            (PieceRef("A", 1), PieceRef("A", 0)),
            (False, True),
            (0.0, 20.0),
        ),
        Assemble("B", (PieceRef("A", 0),), (False,), (0.0,), flipped=(True,)),
        Crop("B", left=5.0, right=5.0, top=1.0, bottom=2.0),
    ],
)
def test_operation_roundtrip(op) -> None:
    """Операция переживает путь в словарь и обратно без потерь."""
    assert op_from_dict(op_to_dict(op)) == op


def test_unknown_operation_rejected() -> None:
    """Чужой JSON не подсовывает нам несуществующую операцию."""
    with pytest.raises(ValueError, match="неизвестная операция"):
        op_from_dict({"op": "Sand", "grit": 120})
