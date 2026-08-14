"""Чтение растра без сторонних библиотек.

Картинки для тестов собираются здесь же, байт за байтом: файл-фикстура
проверял бы заодно и git, и кодировку, а нам нужен только разбор.
"""

import struct
import zlib
from pathlib import Path

import pytest

from boardforge.io.images import UnsupportedImage, decode_png, decode_ppm, read_image


def _png(rows: list[list[tuple[int, int, int]]], colour: int = 2) -> bytes:
    """Собрать простейший PNG: 8 бит, без чересстрочности, фильтр 0."""
    height, width = len(rows), len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for pixel in row:
            raw += bytes(pixel if colour == 2 else (*pixel, 255))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


PIXELS = [
    [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
    [(10, 20, 30), (40, 50, 60), (70, 80, 90)],
]


def test_png_round_trip() -> None:
    assert decode_png(_png(PIXELS)) == PIXELS


def test_png_with_alpha_drops_the_alpha() -> None:
    assert decode_png(_png(PIXELS, colour=6)) == PIXELS


def test_png_filters_are_all_understood() -> None:
    """Каждый из пяти фильтров строки обязан читаться одинаково.

    Кодировщики выбирают фильтр построчно и по своему усмотрению, так что
    непонятый фильтр — это не редкий случай, а обычная картинка из редактора.
    """
    width, height = 6, 5
    rows = [
        [
            (column * 40 % 256, row * 50 % 256, (row + column) * 30 % 256)
            for column in range(width)
        ]
        for row in range(height)
    ]

    raw = bytearray()
    previous = [0] * (width * 3)
    for index, row in enumerate(rows):
        method = index % 5
        line = [channel for pixel in row for channel in pixel]
        raw.append(method)
        encoded = []
        for position, value in enumerate(line):
            left = line[position - 3] if position >= 3 else 0
            up = previous[position]
            corner = previous[position - 3] if position >= 3 else 0
            if method == 0:
                encoded.append(value)
            elif method == 1:
                encoded.append((value - left) & 0xFF)
            elif method == 2:
                encoded.append((value - up) & 0xFF)
            elif method == 3:
                encoded.append((value - (left + up) // 2) & 0xFF)
            else:
                estimate = left + up - corner
                distances = (
                    abs(estimate - left),
                    abs(estimate - up),
                    abs(estimate - corner),
                )
                if distances[0] <= distances[1] and distances[0] <= distances[2]:
                    predictor = left
                elif distances[1] <= distances[2]:
                    predictor = up
                else:
                    predictor = corner
                encoded.append((value - predictor) & 0xFF)
        raw += bytes(encoded)
        previous = line

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )
    assert decode_png(data) == rows


def test_sixteen_bit_png_is_refused_in_words() -> None:
    header = struct.pack(">IIBBBBB", 1, 1, 16, 2, 0, 0, 0)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b"")
    with pytest.raises(UnsupportedImage, match="8"):
        decode_png(data)


def test_binary_ppm_round_trip() -> None:
    body = b"".join(bytes(pixel) for row in PIXELS for pixel in row)
    assert decode_ppm(b"P6\n3 2\n255\n" + body) == PIXELS


def test_text_ppm_round_trip() -> None:
    numbers = " ".join(
        str(channel) for row in PIXELS for pixel in row for channel in pixel
    )
    assert decode_ppm(b"P3\n3 2\n255\n" + numbers.encode()) == PIXELS


def test_ppm_comments_are_skipped() -> None:
    body = b"".join(bytes(pixel) for row in PIXELS for pixel in row)
    assert decode_ppm(b"P6\n# from GIMP\n3 2\n255\n" + body) == PIXELS


def test_read_image_picks_the_parser_by_content(tmp_path: Path) -> None:
    """Расширение врёт чаще, чем подпись файла."""
    path = tmp_path / "board.ppm"
    path.write_bytes(_png(PIXELS))
    assert read_image(path) == PIXELS


def test_unknown_format_says_what_to_do(tmp_path: Path) -> None:
    path = tmp_path / "board.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    with pytest.raises(UnsupportedImage, match="Пересохрани"):
        read_image(path)


def test_truncated_ppm_is_reported() -> None:
    with pytest.raises(ValueError, match="обрывается"):
        decode_ppm(b"P6\n3 2\n255\n\x00\x01")
