"""Вывод переживает консоль с легаси-кодировкой.

Почему здесь настоящий процесс, а не `capsys`: перехват идёт в UTF-8, и этому
классу дефектов он слеп целиком. Обе команды ниже проходили тесты зелёными,
падая при этом в Git Bash — `--help` голым трейсбеком, `workshop` кодом 1
после успешно сделанной работы. Смотреть надо на настоящий поток.

Кодировку в пробе задаём через `PYTHONIOENCODING`: она делает с потоком ровно
то, что делает локаль на русской Windows, но не зависит от того, на какой
машине идёт прогон.
"""

import os
import subprocess
import sys

import pytest

# То, во что упирается человек: Git Bash на русской Windows даёт cp1251,
# cmd.exe — cp866. Ни в одной из них нет ни стрелки, ни рубля.
LEGACY_ENCODINGS = ["cp1251", "cp866"]

_ENTRY = "from boardforge.cli import main; raise SystemExit(main())"


def _run(argv: list[str], encoding: str) -> subprocess.CompletedProcess[bytes]:
    """Запустить команду настоящим процессом с настоящим пайпом."""
    env = os.environ | {"PYTHONIOENCODING": encoding}
    return subprocess.run(
        [sys.executable, "-c", _ENTRY, *argv],
        capture_output=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_help_survives_a_legacy_console(encoding: str) -> None:
    """`--help` печатает argparse — до всякого `try`, и стрелка его роняла."""
    done = _run(["--help"], encoding)

    assert done.returncode == 0, done.stderr.decode(encoding, "replace")
    assert b"Traceback" not in done.stderr
    assert "→" in done.stdout.decode("utf-8")


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_workshop_summary_survives_a_legacy_console(encoding, tmp_path) -> None:
    """Сводка `workshop` несёт `×`, `дм³` и `₽` — и раньше на них падала.

    Код возврата здесь важнее текста: команда доделывала работу до конца
    и всё равно возвращала 1, потому что `UnicodeEncodeError` наследует
    `ValueError` и попадал в ветку доменных отказов.
    """
    done = _run(
        ["workshop", "--template", "checkerboard", "-o", str(tmp_path / "shop")],
        encoding,
    )

    assert done.returncode == 0, done.stderr.decode(encoding, "replace")
    summary = done.stdout.decode("utf-8")
    for mark in ("×", "дм³", "₽"):
        assert mark in summary
    assert (tmp_path / "shop" / "workshop.html").exists()


def test_a_console_that_takes_our_alphabet_is_left_alone() -> None:
    """UTF-8-поток не трогаем: принудительный перевод дал бы мозаику там,
    где всё работало. Настоящая консоль Windows — как раз такой поток."""
    from boardforge.cli import _use_unicode_output

    class Stream:
        encoding = "utf-8"

        def __init__(self) -> None:
            self.reconfigured = False

        def reconfigure(self, **kwargs: object) -> None:
            self.reconfigured = True

    stream = Stream()
    _use_unicode_output(stream)
    assert not stream.reconfigured


@pytest.mark.parametrize("encoding", LEGACY_ENCODINGS)
def test_a_legacy_stream_is_switched_to_utf8(encoding: str) -> None:
    """А поток, который наш алфавит не берёт, — переводим."""
    from boardforge.cli import _use_unicode_output

    class Stream:
        def __init__(self) -> None:
            self.encoding = encoding
            self.kwargs: dict[str, object] = {}

        def reconfigure(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    stream = Stream()
    _use_unicode_output(stream)
    assert stream.kwargs == {"encoding": "utf-8", "errors": "replace"}
