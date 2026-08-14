"""Картинка → доска: квантование в CIELAB и подгон под ограничение рядов.

Два шага, и второй важнее первого.

**Квантование.** Картинка усредняется в сетку ячеек, каждая ячейка переводится
в CIELAB и заменяется ближайшей по ΔE доступной породой. Именно в Lab, а не
в sRGB: там ближайшая по числам сплошь и рядом не ближайшая на вид, и светлый
дуб уезжает в вишню.

**Подгон под ограничение рядов.** Наивный результат квантования — свободная
карта пород, и сделать её нельзя. Столбец доски — это один срез склеенного
щита, поэтому **все ячейки столбца обязаны быть набором реек одного щита**.
Столбцов пятнадцать, а щитов столяр клеит два-три. Значит столбцы надо
разложить по немногим щитам, а щиты подобрать так, чтобы картинка пострадала
меньше всего. Это кластеризация, и она здесь настоящая, а не «взяли первые
попавшиеся».

Решение честно сообщает **точность** — долю ячеек, совпавших с желаемым.
Обещать «портрет из дерева» инструмент не должен: из трёх пород и двух щитов
выходит силуэт, а не фотография.

Только ортогональные узоры (`decisions.md`): угловые резы сюда не заходят.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from ..io.images import Pixels
from .color import Lab, hex_to_lab, rgb_to_lab, srgb_to_linear
from .library import assemble_columns
from .program import Program
from .species import Species

REFINE_PASSES = 4
"""Сколько раз уточнять состав щитов после раскладки столбцов.

Больше четырёх не меняет ничего: разбиение перестаёт двигаться уже
на втором-третьем проходе, а считается каждый проход по всем ячейкам."""


@dataclass(frozen=True, slots=True)
class Mosaic:
    """Что вышло из картинки: программа, щиты и честная точность."""

    program: Program
    billets: tuple[tuple[str, ...], ...]
    """Набор реек каждого щита снизу вверх.

    Щитов может выйти меньше, чем заказано: если картинке хватает одного,
    второй такой же клеить незачем. Это не недоработка солвера, а экономия —
    лишний щит стоит склейки, строгания и обрезки.
    """
    columns: tuple[int, ...]
    """Из какого щита взят каждый столбец доски, слева направо."""
    target: tuple[tuple[str, ...], ...]
    """Чего хотела картинка до подгона: породы по столбцам."""
    fidelity: float
    """Доля ячеек, где вышло то, что хотелось. Единица недостижима почти всегда."""

    @property
    def result(self) -> tuple[tuple[str, ...], ...]:
        """Что получилось: породы по столбцам после подгона."""
        return tuple(self.billets[index] for index in self.columns)


def downsample(pixels: Pixels, columns: int, rows: int) -> list[list[Lab]]:
    """Усреднить растр в сетку `columns × rows` и перевести в CIELAB.

    Усреднение идёт в линейном свете, а не в sRGB: среднее двух чисел из файла
    даёт тон темнее обоих, и вся картинка уезжает в грязь.

    Строки разворачиваются: у растра первая строка сверху, а рейки в щите
    считаются снизу вверх.
    """
    if columns < 1 or rows < 1:
        raise ValueError("сетка должна быть хотя бы 1 × 1")
    if not pixels or not pixels[0]:
        raise ValueError("картинка пуста")

    height, width = len(pixels), len(pixels[0])
    if any(len(row) != width for row in pixels):
        raise ValueError("строки растра разной длины")

    grid: list[list[Lab]] = []
    for column in range(columns):
        left = width * column // columns
        right = max(left + 1, width * (column + 1) // columns)
        cells: list[Lab] = []
        for row in range(rows):
            # Снизу вверх: нулевая рейка щита — нижняя ячейка доски.
            flipped = rows - 1 - row
            top = height * flipped // rows
            bottom = max(top + 1, height * (flipped + 1) // rows)
            totals = [0.0, 0.0, 0.0]
            count = 0
            for y in range(top, bottom):
                for x in range(left, right):
                    pixel = pixels[y][x]
                    for channel in range(3):
                        totals[channel] += srgb_to_linear(pixel[channel] / 255.0)
                    count += 1
            cells.append(_lab_from_linear([value / count for value in totals]))
        grid.append(cells)
    return grid


def _lab_from_linear(linear: Sequence[float]) -> Lab:
    """Линейный RGB → Lab, минуя обратную гамму."""

    # `rgb_to_lab` ждёт sRGB, поэтому гамму возвращаем и тут же снимаем внутри.
    # Дешевле, чем дублировать матрицу XYZ ради одного вызова.
    def encode(value: float) -> float:
        value = max(0.0, min(1.0, value))
        if value <= 0.0031308:
            return value * 12.92
        return 1.055 * value ** (1 / 2.4) - 0.055

    return rgb_to_lab(*(encode(channel) for channel in linear))


def _palette(
    catalogue: dict[str, Species], allowed: Sequence[str] | None
) -> dict[str, Lab]:
    keys = sorted(allowed) if allowed is not None else sorted(catalogue)
    missing = [key for key in keys if key not in catalogue]
    if missing:
        raise ValueError(f"породы нет в справочнике: {', '.join(missing)}")
    if not keys:
        raise ValueError("не задано ни одной доступной породы")
    return {key: hex_to_lab(catalogue[key].color) for key in keys}


def _best_species(cell: Lab, palette: dict[str, Lab]) -> str:
    return min(sorted(palette), key=lambda key: (cell.distance(palette[key]), key))


def _cost(column: Sequence[Lab], strips: Sequence[str], palette: dict[str, Lab]) -> float:
    return sum(
        cell.distance(palette[species])
        for cell, species in zip(column, strips, strict=True)
    )


def _fit_billets(
    grid: list[list[Lab]], palette: dict[str, Lab], count: int
) -> tuple[list[tuple[str, ...]], list[int]]:
    """Разложить столбцы по `count` щитам и подобрать состав каждого.

    Обычный обмен: приписали столбцы к ближайшему щиту, пересобрали щиты под
    приписанные столбцы, повторили. Начальные щиты — самые частые «идеальные»
    столбцы: так стартовое разбиение уже осмысленно, и проходов нужно немного.
    """
    ideal = [tuple(_best_species(cell, palette) for cell in column) for column in grid]

    order: list[tuple[str, ...]] = []
    for candidate in ideal:
        if candidate not in order:
            order.append(candidate)
    order.sort(key=lambda strips: (-ideal.count(strips), strips))
    billets = order[:count]

    assignment = [0] * len(grid)
    for _ in range(REFINE_PASSES):
        assignment = [
            min(
                range(len(billets)),
                key=lambda index: (_cost(grid[column], billets[index], palette), index),
            )
            for column in range(len(grid))
        ]
        rebuilt: list[tuple[str, ...]] = []
        for index, strips in enumerate(billets):
            members = [
                grid[column] for column, owner in enumerate(assignment) if owner == index
            ]
            if not members:
                # Щит, которым никто не пользуется, оставляем как был: выкинуть
                # его значило бы молча уменьшить заказанное число щитов.
                rebuilt.append(strips)
                continue
            rebuilt.append(
                tuple(
                    min(
                        sorted(palette),
                        key=lambda key, row=row: (  # type: ignore[misc]
                            sum(member[row].distance(palette[key]) for member in members),
                            key,
                        ),
                    )
                    for row in range(len(strips))
                )
            )
        if rebuilt == billets:
            break
        billets = rebuilt

    return billets, assignment


def quantise(
    pixels: Pixels,
    catalogue: dict[str, Species],
    columns: int = 14,
    rows: int = 12,
    billets: int = 2,
    cell_mm: float = 34.0,
    allowed: Sequence[str] | None = None,
) -> Mosaic:
    """Картинка → изготовимая доска.

    `billets` — сколько разных щитов согласен склеить столяр. Один даёт
    вертикальные полосы (все столбцы одинаковы), два-три уже узнаваемый силуэт,
    больше десяти — уже не столярка, а мозаика по одной ячейке.
    """
    if billets < 1:
        raise ValueError("щит нужен хотя бы один")
    if billets > columns:
        raise ValueError(
            f"щитов заказано больше ({billets}), чем столбцов в доске ({columns}): "
            f"часть щитов склеить и не из чего"
        )

    table = _palette(catalogue, allowed)
    grid = downsample(pixels, columns, rows)
    strips, assignment = _fit_billets(grid, table, billets)

    target = tuple(
        tuple(_best_species(cell, table) for cell in column) for column in grid
    )
    matched = sum(
        1
        for column, owner in enumerate(assignment)
        for row in range(rows)
        if strips[owner][row] == target[column][row]
    )

    program = assemble_columns(
        strips,
        cell_mm,
        [(owner, 0.0) for owner in assignment],
    )
    return Mosaic(
        program=program,
        billets=tuple(strips),
        columns=tuple(assignment),
        target=target,
        fidelity=matched / (columns * rows),
    )


__all__ = ["Mosaic", "downsample", "quantise"]
