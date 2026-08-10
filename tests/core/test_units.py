"""Единицы измерения и форматтеры границы."""

import pytest

from boardforge.core.units import (
    MM_PER_INCH,
    format_inches,
    format_mm,
    inches_to_mm,
    mm_to_inches,
)


def test_inch_roundtrip() -> None:
    """Перевод в дюймы и обратно не теряет размер."""
    assert inches_to_mm(mm_to_inches(123.4)) == pytest.approx(123.4)


def test_inch_constant() -> None:
    """Дюйм — ровно 25.4 мм."""
    assert inches_to_mm(1.0) == MM_PER_INCH


@pytest.mark.parametrize(
    ("mm", "expected"),
    [
        (25.4, '1"'),
        (12.7, '1/2"'),
        (19.05, '3/4"'),
        (3.175, '1/8"'),
        (38.1, '1-1/2"'),
        (0.0, '0"'),
        (-25.4, '-1"'),
    ],
)
def test_format_inches(mm: float, expected: str) -> None:
    """Дюймы показываем столярной записью с сокращением дроби."""
    assert format_inches(mm) == expected


def test_format_inches_rounds_to_denominator() -> None:
    """Некруглый размер округляется до ближайшей доли, а не отбрасывается."""
    assert format_inches(27.0) == '1-1/16"'
    assert format_inches(25.9) == '1"'


def test_format_inches_rejects_bad_denominator() -> None:
    """Нулевой знаменатель — ошибка, а не деление на ноль."""
    with pytest.raises(ValueError):
        format_inches(25.4, denominator=0)


@pytest.mark.parametrize(
    ("mm", "digits", "expected"),
    [
        (40.0, 1, "40 мм"),
        (35.75, 1, "35.8 мм"),
        (100.0, 0, "100 мм"),
        (0.0, 1, "0 мм"),
    ],
)
def test_format_mm(mm: float, digits: int, expected: str) -> None:
    """Хвостовые нули не мозолят глаза, но целые числа не калечатся."""
    assert format_mm(mm, digits) == expected
