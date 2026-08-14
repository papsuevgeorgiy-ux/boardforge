"""Цвет породы в перцептивных координатах.

Два потребителя, и оба меряют не «похожесть чисел», а различимость глазом.
Кубы держатся на разной светлоте трёх пород: если тона близки, объём
не читается, сколько ни строй геометрию. Импорт изображения подбирает
ближайшую породу к пикселю — и в sRGB ближайшая по числам оказывается
не ближайшей на вид.

Отсюда CIELAB: в нём расстояние примерно пропорционально воспринимаемой
разнице. Формула D65, наблюдатель 2°, как для экрана.

Только чтение цвета: рисование, палитры и текстура живут в `render/`,
ядро про них ничего не знает.
"""

import math
from dataclasses import dataclass

# Матрица sRGB → XYZ (D65) и белая точка того же осветителя.
_TO_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
_WHITE = (0.95047, 1.00000, 1.08883)

_DELTA = 6.0 / 29.0


def _linear(channel: float) -> float:
    """Снять гамму sRGB: числа в файле — не количество света."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def srgb_to_linear(channel: float) -> float:
    """Канал sRGB 0–1 в линейный свет.

    Нужна усреднению: среднее двух пикселей считается по количеству света,
    а не по числам в файле. Усреднить в sRGB — получить тон темнее обоих.
    """
    return _linear(channel)


def _pivot(ratio: float) -> float:
    if ratio > _DELTA**3:
        return ratio ** (1.0 / 3.0)
    return ratio / (3 * _DELTA**2) + 4.0 / 29.0


@dataclass(frozen=True, slots=True)
class Lab:
    """Цвет в CIELAB: светлота 0–100 и две оси цветности."""

    lightness: float
    a: float
    b: float

    def distance(self, other: "Lab") -> float:
        """ΔE76 — евклидово расстояние в Lab.

        Не CIEDE2000: та поправляет неравномерность на насыщенных синих
        и мелких различиях, а здесь сравниваются древесные тона, лежащие
        узкой полосой в жёлто-красной части. Разница формул на них меньше,
        чем разброс между двумя досками одной породы.
        """
        return math.dist(
            (self.lightness, self.a, self.b), (other.lightness, other.a, other.b)
        )


def parse_hex(color: str) -> tuple[float, float, float]:
    """`#rrggbb` → три канала 0–1."""
    value = color.strip()
    if not value.startswith("#") or len(value) != 7:
        raise ValueError(f"цвет должен быть в формате #rrggbb, получен {color!r}")
    try:
        return tuple(int(value[index : index + 2], 16) / 255.0 for index in (1, 3, 5))  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"цвет {color!r} не разбирается как #rrggbb") from exc


def rgb_to_lab(red: float, green: float, blue: float) -> Lab:
    """Канал 0–1 в sRGB → CIELAB."""
    linear = (_linear(red), _linear(green), _linear(blue))
    xyz = tuple(sum(row[i] * linear[i] for i in range(3)) for row in _TO_XYZ)
    fx, fy, fz = (_pivot(xyz[i] / _WHITE[i]) for i in range(3))
    return Lab(116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def hex_to_lab(color: str) -> Lab:
    """`#rrggbb` → CIELAB."""
    return rgb_to_lab(*parse_hex(color))


def lightness_spread(colors: list[str]) -> float:
    """Наименьшая разница светлоты между парами — узкое место набора.

    Именно минимум, а не размах: объём в кубах теряется на той паре граней,
    которая слилась, даже если третья далеко.
    """
    if len(colors) < 2:
        raise ValueError("разброс светлоты считается минимум по двум цветам")
    values = sorted(hex_to_lab(color).lightness for color in colors)
    return min(after - before for before, after in zip(values, values[1:], strict=False))


def nearest(color: Lab, palette: dict[str, Lab]) -> tuple[str, float]:
    """Ближайший по ΔE ключ палитры и само расстояние.

    При равенстве расстояний берётся первый по имени: подбор обязан быть
    воспроизводимым, а порядок словаря приходит из файла справочника.
    """
    if not palette:
        raise ValueError("палитра пуста: не из чего выбирать")
    return min(
        ((key, color.distance(value)) for key, value in sorted(palette.items())),
        key=lambda item: (item[1], item[0]),
    )


__all__ = [
    "Lab",
    "srgb_to_linear",
    "hex_to_lab",
    "lightness_spread",
    "nearest",
    "parse_hex",
    "rgb_to_lab",
]
