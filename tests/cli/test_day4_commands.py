"""Команды Дня 4: генератор и импорт картинки доходят до файла на диске."""

import struct
import zlib
from pathlib import Path

import pytest

from boardforge.cli import main


def _png(rows) -> bytes:
    height, width = len(rows), len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for pixel in row:
            raw += bytes(pixel)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


def test_generate_writes_a_board_and_prints_the_scores(tmp_path: Path, capsys) -> None:
    target = tmp_path / "generated.svg"
    assert main(["generate", "--seed", "5", "-o", str(target)]) == 0

    assert target.read_text(encoding="utf-8").startswith("<?xml")
    out = capsys.readouterr().out
    assert "сид 5" in out
    for name in ("контраст", "ритм", "симметрия", "экономичность", "реализуемость"):
        assert name in out


def test_generate_is_reproducible_on_disk(tmp_path: Path) -> None:
    """Один сид — один файл, байт в байт. Это и есть обещание про сид."""
    first, second = tmp_path / "a.svg", tmp_path / "b.svg"
    assert main(["generate", "--seed", "77", "-o", str(first)]) == 0
    assert main(["generate", "--seed", "77", "-o", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_generate_can_be_told_which_template(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "generate",
                "--seed",
                "3",
                "--template",
                "basket",
                "-o",
                str(tmp_path / "b.svg"),
            ]
        )
        == 0
    )
    assert "basket" in capsys.readouterr().out


def test_evolve_runs_and_reports(tmp_path: Path, capsys) -> None:
    target = tmp_path / "evolved.svg"
    assert (
        main(
            [
                "generate",
                "--seed",
                "8",
                "--evolve",
                "--generations",
                "2",
                "--population",
                "4",
                "-o",
                str(target),
            ]
        )
        == 0
    )
    assert target.read_text(encoding="utf-8").startswith("<?xml")
    assert "итого" in capsys.readouterr().out


def test_image_command_writes_a_board(tmp_path: Path, capsys) -> None:
    picture = tmp_path / "logo.png"
    picture.write_bytes(
        _png(
            [
                [(250, 245, 235) if column < 8 else (30, 24, 20) for column in range(16)]
                for _ in range(16)
            ]
        )
    )
    target = tmp_path / "board.svg"
    assert (
        main(["image", str(picture), "--columns", "8", "--rows", "6", "-o", str(target)])
        == 0
    )

    assert target.read_text(encoding="utf-8").startswith("<?xml")
    out = capsys.readouterr().out
    assert "точность" in out
    assert "щит A" in out


def test_image_command_reports_a_bad_file(tmp_path: Path, capsys) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"definitely not an image")
    assert main(["image", str(broken)]) == 1
    assert "не распознан" in capsys.readouterr().err


def test_contact_sheet_covers_the_whole_library(tmp_path: Path, capsys) -> None:
    """Контактный лист — это вся библиотека, а не выборка из неё."""
    from boardforge.core.library import LIBRARY

    target = tmp_path / "sheet.svg"
    assert main(["contact-sheet", "-o", str(target), "--scale", "1"]) == 0

    sheet = target.read_text(encoding="utf-8")
    for template in LIBRARY.values():
        assert template.title.lower() in sheet.lower(), template.key
    assert f"досок на листе: {len(LIBRARY)}" in capsys.readouterr().out


@pytest.mark.parametrize("seed", (2, 19))
def test_generated_boards_are_never_broken(seed: int, tmp_path: Path) -> None:
    """Команда не имеет права выдать то, на что ругается валидатор."""
    from boardforge.core.generate import generate

    _, program = generate(seed)
    assert not program.errors
    assert main(["generate", "--seed", str(seed), "-o", str(tmp_path / "x.svg")]) == 0
