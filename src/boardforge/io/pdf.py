"""Принтер: та же страница распечатки, только в PDF.

Отдельным модулем, а не строчкой в `report.py`, ради одного: **импорт
`weasyprint` живёт внутри функции**. Колесо WeasyPrint не тянет нативные
Pango и GLib, и на машине без системного GTK его импорт падает `OSError`
ещё до первой строчки кода. Стой он наверху модуля — вместе с PDF ложился бы
весь `boardforge`, включая `serve` и `swatches`, которым принтер не нужен
вовсе. Поэтому здесь нет ни одного импорта WeasyPrint на уровне модуля,
и `io/report.py` про него тоже не знает.

Вторая причина — сообщение. Столяру, у которого не поставлен GTK, трейсбек
про `libgobject-2.0-0` не говорит ничего; ему нужна команда установки.
"""

from pathlib import Path

INSTALL_HINT = (
    "PDF не собран: нет системного GTK-рантайма (Pango и GLib), без него "
    "WeasyPrint не запускается — колесо тянет только Python-часть.\n"
    "Windows: поставьте MSYS2 с https://www.msys2.org и выполните\n"
    "    pacman -S mingw-w64-x86_64-pango\n"
    "Если библиотеки не находятся, укажите каталог явно:\n"
    r'    $env:WEASYPRINT_DLL_DIRECTORIES = "C:\msys64\mingw64\bin"'
    "\n"
    "Всё остальное — превью, чертёж и распечатка в HTML — работает и без PDF."
)


class PrinterError(OSError):
    """Печать не состоялась.

    Наследник `OSError`, а не `RuntimeError`: это и есть ошибка окружения —
    в системе нет библиотеки. Заодно её ловит общий обработчик `cli.main`
    и превращает в строку «boardforge: …» с кодом 1, а не в трейсбек.
    """


def printer_available() -> bool:
    """Можно ли сейчас печатать. Нужна тестам и интерфейсу, чтобы не гадать."""
    try:
        _html_class()
    except PrinterError:
        return False
    return True


def _html_class():
    """Класс `weasyprint.HTML` — или человеческая фраза вместо трейсбека."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as error:
        raise PrinterError(INSTALL_HINT) from error
    return HTML


def render_pdf(html: str, base_url: Path | None = None) -> bytes:
    """Страница распечатки в PDF, байтами.

    `base_url` нужен не картинкам — их на странице нет, вектор встроен, —
    а самому WeasyPrint: без него относительные ссылки он ищет от текущего
    каталога процесса, и результат зависел бы от того, откуда запустили.
    """
    html_class = _html_class()
    document = html_class(string=html, base_url=str(base_url or Path.cwd()))
    return document.write_pdf()


def write_pdf(html: str, target: Path) -> Path:
    """Положить PDF рядом со страницей, из которой он собран."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render_pdf(html, target.parent))
    return target


__all__ = ["INSTALL_HINT", "PrinterError", "printer_available", "render_pdf", "write_pdf"]
