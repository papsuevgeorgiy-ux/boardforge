# -*- mode: python ; coding: utf-8 -*-
"""Сборка BoardForge в обычную программу для Windows.

    uv add --dev pyinstaller
    uv run pyinstaller packaging/boardforge.spec --noconfirm

Результат — каталог `dist/BoardForge/` с `BoardForge.exe` внутри. Каталог, а не
один файл: стартует заметно быстрее и реже ловит ложное срабатывание антивируса,
который не любит самораспаковывающиеся сборки.

WeasyPrint исключён намеренно. Он тянет системный GTK, которого на чужой машине
нет и который в установщик по-человечески не упаковать. Страница цеха и без него
печатается из браузера по Ctrl+P — она для этого и написана. Ленивый импорт из
`io/pdf.py` при этом сработает штатно и выдаст свой отказ вместо падения; текст
отказа для сборки стоит перечитать, он написан для разработчика.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller считает относительные пути в спеке от каталога спеки, а не от
# корня проекта. Поэтому всё абсолютное: SPECPATH подставляет сам PyInstaller.
ROOT = Path(SPECPATH).parent          # noqa: F821 — SPECPATH объявляет PyInstaller
SRC = ROOT / "src" / "boardforge"

# Пути внутри сборки повторяют пути в исходниках: модули ищут соседние файлы
# через Path(__file__).parent, и эта раскладка обязана совпадать.
datas = [
    (str(SRC / "core" / "species.yaml"), "boardforge/core"),
    (str(SRC / "web" / "static"), "boardforge/web/static"),
    (str(SRC / "web" / "templates"), "boardforge/web/templates"),
    (str(SRC / "io" / "templates"), "boardforge/io/templates"),
]
datas += collect_data_files("trimesh")

hiddenimports = [
    # uvicorn грузит эти модули по строке имени, статический анализ их не видит
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]
hiddenimports += collect_submodules("boardforge")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "weasyprint",  # см. шапку файла
        "tkinter",
        "matplotlib",
        "pytest",
        "hypothesis",
        "IPython",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="BoardForge",
    console=True,  # окно нужно: это единственный способ остановить программу
    disable_windowed_traceback=False,
    # icon=str(ROOT / "packaging" / "boardforge.ico"),  # появится иконка — раскомментировать
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,  # UPX ускоряет антивирусные ложные срабатывания, не стоит того
    name="BoardForge",
)
