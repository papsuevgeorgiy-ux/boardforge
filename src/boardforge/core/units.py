"""Единицы измерения. Внутри ядра — миллиметры, дюймы только на границе."""

from math import gcd

MM_PER_INCH = 25.4

EPS = 1e-6
"""Геометрический допуск в миллиметрах — заведомо ниже столярной точности."""


def inches_to_mm(inches: float) -> float:
    """Дюймы в миллиметры."""
    return inches * MM_PER_INCH


def mm_to_inches(mm: float) -> float:
    """Миллиметры в дюймы."""
    return mm / MM_PER_INCH


def format_mm(mm: float, digits: int = 1) -> str:
    """Миллиметры для показа человеку: хвостовые нули убираются."""
    text = f"{mm:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text} мм"


def format_inches(mm: float, denominator: int = 16) -> str:
    """Миллиметры в дюймы столярной записью: 1-1/2\"."""
    if denominator < 1:
        raise ValueError("знаменатель доли дюйма должен быть положительным")
    sign = "-" if mm < 0 else ""
    total = round(mm_to_inches(abs(mm)) * denominator)
    whole, numerator = divmod(total, denominator)
    if numerator == 0:
        return f'{sign}{whole}"'
    divisor = gcd(numerator, denominator)
    numerator, denominator = numerator // divisor, denominator // divisor
    if whole == 0:
        return f'{sign}{numerator}/{denominator}"'
    return f'{sign}{whole}-{numerator}/{denominator}"'
