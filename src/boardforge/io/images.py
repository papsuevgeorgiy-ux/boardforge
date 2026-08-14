"""Чтение растра без сторонних библиотек.

PNG и PPM разбираются здесь руками на `zlib` и `struct` из стандартной
библиотеки. Причина не в аскетизме: картинка нужна ровно один раз, чтобы
её усреднить в сетку ячеек, — а Pillow тянет за собой бинарные колёса,
которые придётся ставить на машине в мастерской.

Поддержано то, что реально приходит из редактора: PNG 8 бит на канал,
без чересстрочности, цветной с альфой и без; PPM P6 и P3. Всё остальное
отвергается словами, а не молча искажается.
"""

import struct
import zlib
from pathlib import Path

type Pixels = list[list[tuple[int, int, int]]]
"""Растр строками сверху вниз, каналы 0–255."""

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class UnsupportedImage(ValueError):
    """Формат распознан, но такой его разновидности мы не умеем."""


def _paeth(left: int, up: int, corner: int) -> int:
    estimate = left + up - corner
    distances = (abs(estimate - left), abs(estimate - up), abs(estimate - corner))
    if distances[0] <= distances[1] and distances[0] <= distances[2]:
        return left
    return up if distances[1] <= distances[2] else corner


def _unfilter(raw: bytes, width: int, height: int, channels: int) -> bytearray:
    """Снять построчные фильтры PNG. Данные приходят уже распакованными."""
    stride = width * channels
    out = bytearray(stride * height)
    position = 0
    for row in range(height):
        method = raw[position]
        position += 1
        line = raw[position : position + stride]
        position += stride
        start = row * stride
        previous = start - stride
        for index in range(stride):
            value = line[index]
            left = out[start + index - channels] if index >= channels else 0
            up = out[previous + index] if row else 0
            corner = out[previous + index - channels] if row and index >= channels else 0
            if method == 1:
                value += left
            elif method == 2:
                value += up
            elif method == 3:
                value += (left + up) // 2
            elif method == 4:
                value += _paeth(left, up, corner)
            elif method != 0:
                raise UnsupportedImage(f"неизвестный фильтр строки PNG: {method}")
            out[start + index] = value & 0xFF
    return out


def decode_png(data: bytes) -> Pixels:
    """PNG 8 бит на канал, без чересстрочности, RGB или RGBA."""
    if not data.startswith(_PNG_MAGIC):
        raise ValueError("это не PNG: нет подписи файла")

    position = len(_PNG_MAGIC)
    header: tuple[int, ...] | None = None
    payload = bytearray()
    palette = b""

    while position + 8 <= len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        chunk = data[position + 8 : position + 8 + length]
        position += 12 + length

        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"PLTE":
            palette = chunk
        elif kind == b"IDAT":
            payload += chunk
        elif kind == b"IEND":
            break

    if header is None:
        raise ValueError("в PNG нет заголовка IHDR")
    width, height, depth, colour, compression, filtering, interlace = header

    if depth != 8:
        raise UnsupportedImage(f"PNG глубиной {depth} бит: умеем только 8")
    if interlace:
        raise UnsupportedImage("чересстрочный PNG: пересохрани без Interlace")
    if compression or filtering:
        raise UnsupportedImage("нестандартное сжатие или фильтрация PNG")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if channels is None:
        raise UnsupportedImage(f"неизвестный тип цвета PNG: {colour}")

    flat = _unfilter(zlib.decompress(bytes(payload)), width, height, channels)
    stride = width * channels

    rows: Pixels = []
    for row in range(height):
        line: list[tuple[int, int, int]] = []
        base = row * stride
        for column in range(width):
            start = base + column * channels
            if colour in (2, 6):
                line.append((flat[start], flat[start + 1], flat[start + 2]))
            elif colour in (0, 4):
                grey = flat[start]
                line.append((grey, grey, grey))
            else:
                index = flat[start] * 3
                if index + 2 >= len(palette):
                    raise ValueError("палитра PNG короче, чем ссылки на неё")
                line.append((palette[index], palette[index + 1], palette[index + 2]))
        rows.append(line)
    return rows


def decode_ppm(data: bytes) -> Pixels:
    """PPM: двоичный P6 и текстовый P3, 8 бит на канал."""
    fields: list[bytes] = []
    position = 0
    while len(fields) < 4 and position < len(data):
        while position < len(data) and data[position : position + 1].isspace():
            position += 1
        if data[position : position + 1] == b"#":
            while position < len(data) and data[position] != 0x0A:
                position += 1
            continue
        start = position
        while position < len(data) and not data[position : position + 1].isspace():
            position += 1
        fields.append(data[start:position])

    if len(fields) < 4 or fields[0] not in (b"P6", b"P3"):
        raise ValueError("это не PPM: ожидались P6 или P3 и три числа заголовка")
    width, height, maximum = (int(value) for value in fields[1:4])
    if maximum != 255:
        raise UnsupportedImage(f"PPM с максимумом {maximum}: умеем только 255")

    if fields[0] == b"P6":
        body = data[position + 1 :]
        need = width * height * 3
        if len(body) < need:
            raise ValueError("PPM обрывается раньше, чем кончается растр")
        return [
            [
                tuple(body[(row * width + column) * 3 :][:3])  # type: ignore[misc]
                for column in range(width)
            ]
            for row in range(height)
        ]

    numbers = [int(value) for value in data[position:].split()]
    if len(numbers) < width * height * 3:
        raise ValueError("PPM обрывается раньше, чем кончается растр")
    return [
        [
            (
                numbers[(row * width + column) * 3],
                numbers[(row * width + column) * 3 + 1],
                numbers[(row * width + column) * 3 + 2],
            )
            for column in range(width)
        ]
        for row in range(height)
    ]


def read_image(path: Path) -> Pixels:
    """Прочитать картинку с диска, выбрав разбор по её содержимому.

    По содержимому, а не по расширению: `.png`, сохранённый как JPEG, —
    обычное дело, и ошибка про подпись файла понятнее, чем про zlib.
    """
    data = Path(path).read_bytes()
    if data.startswith(_PNG_MAGIC):
        return decode_png(data)
    if data[:2] in (b"P6", b"P3"):
        return decode_ppm(data)
    raise UnsupportedImage(
        f"{path}: формат не распознан. Умеем PNG (8 бит, без чересстрочности) "
        f"и PPM. Пересохрани картинку в PNG"
    )


__all__ = ["Pixels", "UnsupportedImage", "decode_png", "decode_ppm", "read_image"]
