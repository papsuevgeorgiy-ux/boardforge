"""Принтер: PDF из той же страницы и внятный отказ, когда печатать нечем.

Два требования равнозначны. Первое очевидно — PDF должен получаться. Второе
важнее для Дня 7: на машине без системного GTK импорт `weasyprint` падает
`OSError` ещё до первой строчки кода, и если этот импорт стоит наверху модуля,
вместе с ним ложится весь `boardforge` — включая `serve` и `swatches`, которым
принтер не нужен. Поэтому здесь есть тест, который запускает **отдельный
процесс** и смотрит, не затянулся ли `weasyprint` в память сам собой.
"""

import subprocess
import sys
import types

import pytest

from boardforge.io.pdf import PrinterError, printer_available, render_pdf, write_pdf

PAGE = (
    "<!DOCTYPE html><html><head><title>t</title></head><body><p>Доска</p></body></html>"
)

needs_printer = pytest.mark.skipif(
    not printer_available(),
    reason="нет системного GTK: WeasyPrint не запускается, PDF проверить нечем",
)


@pytest.fixture
def without_gtk(monkeypatch):
    """Машина, где колесо WeasyPrint стоит, а нативных библиотек нет.

    Заглушка воспроизводит настоящий отказ буквально: не `ImportError`
    отсутствующего пакета, а `OSError` от `ctypes`, который и получает
    пользователь без GTK.
    """
    stub = types.ModuleType("weasyprint")

    def missing(name: str):
        raise OSError("cannot load library 'libgobject-2.0-0'")

    stub.__getattr__ = missing  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "weasyprint", stub)
    return stub


def test_missing_runtime_is_explained_not_traced(without_gtk) -> None:
    """Без GTK пользователь получает команду установки, а не трейсбек."""
    with pytest.raises(PrinterError) as failure:
        render_pdf(PAGE)
    message = str(failure.value)
    assert "pacman -S mingw-w64-x86_64-pango" in message
    assert "libgobject" not in message, "имя библиотеки столяру ничего не говорит"
    assert "WEASYPRINT_DLL_DIRECTORIES" in message


def test_missing_runtime_is_reported_before_printing(without_gtk) -> None:
    """`printer_available` отвечает про окружение, а не про удачу прошлого раза."""
    assert printer_available() is False


def test_import_of_boardforge_does_not_pull_weasyprint() -> None:
    """Ни одна оболочка не тянет принтер за собой.

    Отдельным процессом: в этом прогоне `weasyprint` уже мог быть импортирован
    другим тестом, и проверка `sys.modules` внутри процесса ничего не значила бы.
    """
    code = (
        "import sys;"
        "import boardforge.cli, boardforge.web, boardforge.io.report, boardforge.io.pdf;"
        "print('weasyprint' in sys.modules)"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "False", (
        "weasyprint импортируется при загрузке пакета — на машине без GTK "
        "ляжет весь boardforge, а не только PDF"
    )


@needs_printer
def test_pdf_is_produced_from_the_page() -> None:
    """Печать даёт настоящий PDF, а не пустой файл."""
    printed = render_pdf(PAGE)
    assert printed.startswith(b"%PDF-")
    assert len(printed) > 1000


@needs_printer
def test_pdf_lands_next_to_the_page(tmp_path) -> None:
    """`write_pdf` создаёт каталог и кладёт файл туда, куда просили."""
    target = write_pdf(PAGE, tmp_path / "deep" / "workshop.pdf")
    assert target.read_bytes().startswith(b"%PDF-")


@needs_printer
def test_workshop_printout_survives_the_printer(tmp_path) -> None:
    """Настоящая распечатка со встроенным чертежом проходит через WeasyPrint.

    Проверяется не «файл появился», а что документ многостраничный: чертёж,
    закупка и карта раскроя на одну страницу не помещаются, и схлопывание
    в один лист означало бы, что вёрстка до принтера не доехала.

    Число страниц приходится спрашивать у самого WeasyPrint: готовый файл
    пакует объекты PDF в сжатые потоки, и по его байтам страницы не сосчитать.
    """
    from weasyprint import HTML

    from boardforge.io.report import collect, render_workshop, write_workshop
    from tests.helpers import build_checkerboard

    shop = collect(build_checkerboard())
    write_workshop(shop, tmp_path, pdf=True)
    assert (tmp_path / "workshop.pdf").read_bytes().startswith(b"%PDF-")
    assert len(HTML(string=render_workshop(shop)).render().pages) > 1
