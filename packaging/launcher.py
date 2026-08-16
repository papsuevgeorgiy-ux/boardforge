"""Запуск BoardForge как обычной программы: двойной клик — открывается браузер.

Точка входа для сборки PyInstaller. От `boardforge serve` отличается двумя
вещами, и обе — про человека без консоли:

* порт подбирается свободный. 8000 занимают десятки чужих программ, а объяснить
  мастеру, что такое «порт занят», нечем;
* окно не исчезает при ошибке. Если программа падает, она обязана оставить на
  экране текст, а не мигнуть и пропасть.

Лежит вне `src/boardforge`, потому что это способ запуска, а не часть ядра.
"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser

BANNER = """
  BoardForge — генератор узоров для торцевых разделочных досок

  Программа работает, пока открыто это окно.
  Интерфейс: {url}

  Если браузер не открылся сам — скопируйте адрес выше в адресную строку.
  Чтобы завершить работу, закройте это окно.
"""


def free_port(preferred: int = 8000) -> int:
    """Первый свободный порт начиная с 8000, иначе любой, выданный системой."""
    for port in range(preferred, preferred + 50):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def main() -> int:
    try:
        import uvicorn

        from boardforge.web import create_app

        port = free_port()
        url = f"http://127.0.0.1:{port}"
        print(BANNER.format(url=url))

        threading.Timer(1.5, webbrowser.open, [url]).start()
        uvicorn.run(
            create_app(),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            loop="asyncio",  # без uvloop и httptools: в сборке они лишние
            http="h11",
        )
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001 — здесь ловим всё намеренно
        import traceback

        print("\n  BoardForge не смог запуститься.")
        print("  Покажите текст ниже разработчику — он объясняет причину.\n")
        traceback.print_exc()
        input("\n  Нажмите Enter, чтобы закрыть окно. ")
        return 1


if __name__ == "__main__":
    sys.exit(main())
