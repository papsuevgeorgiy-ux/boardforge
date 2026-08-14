"""Командная строка на `argparse` (Р17).

Typer не добавляем: две подкоманды не окупают зависимости. К вопросу
возвращаемся на Дне 7, когда появится интерактивный режим.
"""

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

from ..core.species import DEFAULT_SPECIES_PATH, load_species
from ..render.style import RenderOptions, style_by_name
from ..render.svg import render_board
from ..render.swatches import render_swatches
from .examples import DIAGNOSTICS, EXAMPLES

OUT_DIR = Path("out")
DEFAULT_SWATCHES_PATH = OUT_DIR / "swatches.svg"


def _swatches(args: argparse.Namespace) -> int:
    catalogue = load_species(args.species)
    sheet = render_swatches(
        catalogue, RenderOptions(scale=args.scale), columns=args.columns
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(sheet, encoding="utf-8")

    unverified = [item.key for item in catalogue.values() if not item.palette.verified]
    print(f"пород на листе: {len(catalogue)}; сохранено: {args.output}")
    if unverified:
        print(f"не сверено: {', '.join(unverified)}")
        print(f"правьте палитры в {args.species} и ставьте verified: true")
    return 0


def _examples(args: argparse.Namespace) -> int:
    catalogue = load_species(args.species)
    options = RenderOptions(scale=args.scale, style=style_by_name(args.style))
    args.output.mkdir(parents=True, exist_ok=True)

    boards = dict(EXAMPLES)
    if args.diagnostics:
        boards |= DIAGNOSTICS

    for name, (title, build) in boards.items():
        board = build().apply()
        path = args.output / f"{name}.svg"
        path.write_text(render_board(board, catalogue, options), encoding="utf-8")
        print(f"{path}: {title}, ячеек {len(board.pieces)}")
    return 0


def _contact_sheet(args: argparse.Namespace) -> int:
    from ..render.contact import render_contact_sheet

    catalogue = load_species(args.species)
    options = RenderOptions(scale=args.scale)
    boards = {
        title: render_board(build().apply(), catalogue, options)
        for title, build in EXAMPLES.values()
    }
    sheet = render_contact_sheet(boards, catalogue, options)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(sheet, encoding="utf-8")
    print(f"досок на листе: {len(boards)}; сохранено: {args.output}")
    return 0


def _generate(args: argparse.Namespace) -> int:
    from ..core.fitness import score
    from ..core.generate import evolve, generate

    catalogue = load_species(args.species)
    if args.evolve:
        best = evolve(
            args.seed,
            generations=args.generations,
            population=args.population,
            catalogue=catalogue,
        )
        genome, program, scores = best.genome, best.program, best.scores
    else:
        genome, program = generate(args.seed, catalogue, template=args.template)
        scores = score(program, catalogue)

    board = program.apply()
    options = RenderOptions(scale=args.scale)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_board(board, catalogue, options), encoding="utf-8")

    print(f"сид {args.seed}: узор «{genome.template}», ячеек {len(board.pieces)}")
    print(f"размер {board.width_mm:.0f} x {board.length_mm:.0f} мм")
    for name, value in scores.as_dict().items():
        print(f"  {name:<14} {value:.2f}")
    print(f"  {'итого':<14} {scores.total():.2f}")
    print(f"сохранено: {args.output}")
    return 0


def _image(args: argparse.Namespace) -> int:
    from ..core.imaging import quantise
    from ..io.images import read_image

    catalogue = load_species(args.species)
    pixels = read_image(args.image)
    mosaic = quantise(
        pixels,
        catalogue,
        columns=args.columns,
        rows=args.rows,
        billets=args.billets,
        cell_mm=args.cell,
        allowed=tuple(args.only) if args.only else None,
    )

    board = mosaic.program.apply()
    options = RenderOptions(scale=args.scale)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_board(board, catalogue, options), encoding="utf-8")

    print(
        f"{args.image}: {args.columns} x {args.rows} ячеек, щитов {len(mosaic.billets)}"
    )
    print(f"точность: {mosaic.fidelity:.0%} ячеек совпали с картинкой")
    for index, strips in enumerate(mosaic.billets):
        used = ", ".join(sorted({catalogue[key].name for key in strips}))
        print(f"  щит {chr(ord('A') + index)}: {used}")
    print(f"сохранено: {args.output}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from ..web import create_app

    program = None
    if args.project is not None:
        editor_program = Path(args.project)
        from ..core.program import Program

        program = Program.from_dict(
            json.loads(editor_program.read_text(encoding="utf-8"))
        )

    url = f"http://{args.host}:{args.port}/"
    print(f"BoardForge: {url}")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(create_app(program), host=args.host, port=args.port, log_level="warning")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Разбор аргументов."""
    parser = argparse.ArgumentParser(
        prog="boardforge",
        description="Генератор узоров для торцевых разделочных досок",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    swatches = commands.add_parser(
        "swatches",
        help="лист образцов пород в SVG — сверить цвета глазами",
        description=(
            "Рисует все породы справочника торцевыми квадратами с подписями. "
            "Породы с несверенной палитрой помечены на листе."
        ),
    )
    swatches.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_SWATCHES_PATH,
        help=f"куда сохранить лист (по умолчанию {DEFAULT_SWATCHES_PATH})",
    )
    swatches.add_argument(
        "--species",
        type=Path,
        default=DEFAULT_SPECIES_PATH,
        help="свой справочник пород вместо встроенного",
    )
    swatches.add_argument(
        "--scale", type=float, default=3.0, help="пикселей на миллиметр"
    )
    swatches.add_argument(
        "--columns", type=int, default=4, help="сколько образцов в ряду"
    )
    swatches.set_defaults(handler=_swatches)

    examples = commands.add_parser(
        "examples",
        help="демо-доски в SVG — посмотреть, что делает рендер",
        description="Рисует набор досок: шахматку, сильные кольца, тропические.",
    )
    examples.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUT_DIR,
        help=f"каталог для файлов (по умолчанию {OUT_DIR})",
    )
    examples.add_argument(
        "--species",
        type=Path,
        default=DEFAULT_SPECIES_PATH,
        help="свой справочник пород вместо встроенного",
    )
    examples.add_argument(
        "--scale", type=float, default=2.0, help="пикселей на миллиметр"
    )
    examples.add_argument(
        "--style", default="preview", help="режим рендера: preview или flat"
    )
    examples.add_argument(
        "--diagnostics",
        action="store_true",
        help="добавить стенды: доски, собранные под проверку рендера глазом",
    )
    examples.set_defaults(handler=_examples)

    contact = commands.add_parser(
        "contact-sheet",
        help="одна страница со всеми досками и породами",
        description=(
            "Собирает демо-доски и лист пород в один документ. Нужен для быстрой "
            "проверки после правок, для README и для показа проекта."
        ),
    )
    contact.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUT_DIR / "contact-sheet.svg",
        help="куда сохранить лист",
    )
    contact.add_argument(
        "--species",
        type=Path,
        default=DEFAULT_SPECIES_PATH,
        help="свой справочник пород вместо встроенного",
    )
    contact.add_argument("--scale", type=float, default=2.0, help="пикселей на миллиметр")
    contact.set_defaults(handler=_contact_sheet)

    generated = commands.add_parser(
        "generate",
        help="случайный узор по сиду, с оценками",
        description=(
            "Собирает изготовимый узор из библиотеки со случайными параметрами. "
            "Один сид даёт один и тот же узор. С --evolve вместо одной попытки "
            "идёт отбор по фитнес-функции."
        ),
    )
    generated.add_argument("--seed", type=int, default=1, help="сид генератора")
    generated.add_argument(
        "--template", default=None, help="назначить шаблон вместо случайного"
    )
    generated.add_argument(
        "--evolve", action="store_true", help="эволюционный режим вместо одной попытки"
    )
    generated.add_argument("--generations", type=int, default=6, help="сколько поколений")
    generated.add_argument("--population", type=int, default=8, help="размер популяции")
    generated.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUT_DIR / "generated.svg",
        help="куда сохранить",
    )
    generated.add_argument(
        "--species", type=Path, default=DEFAULT_SPECIES_PATH, help="свой справочник пород"
    )
    generated.add_argument(
        "--scale", type=float, default=2.0, help="пикселей на миллиметр"
    )
    generated.set_defaults(handler=_generate)

    image = commands.add_parser(
        "image",
        help="картинка → доска через квантование в CIELAB",
        description=(
            "Усредняет картинку в сетку ячеек, подбирает ближайшие породы "
            "в CIELAB и раскладывает столбцы по немногим щитам — иначе доску "
            "не склеить. Честно печатает, какая доля ячеек совпала."
        ),
    )
    image.add_argument("image", type=Path, help="PNG или PPM")
    image.add_argument("--columns", type=int, default=14, help="ячеек по ширине")
    image.add_argument("--rows", type=int, default=12, help="ячеек по высоте")
    image.add_argument(
        "--billets", type=int, default=2, help="сколько разных щитов готов склеить"
    )
    image.add_argument("--cell", type=float, default=34.0, help="сторона ячейки, мм")
    image.add_argument(
        "--only", nargs="*", default=None, help="ограничить набор пород их ключами"
    )
    image.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUT_DIR / "image-board.svg",
        help="куда сохранить",
    )
    image.add_argument(
        "--species", type=Path, default=DEFAULT_SPECIES_PATH, help="свой справочник пород"
    )
    image.add_argument("--scale", type=float, default=2.0, help="пикселей на миллиметр")
    image.set_defaults(handler=_image)

    serve = commands.add_parser(
        "serve",
        help="веб-интерфейс на localhost",
        description=(
            "Поднимает редактор и открывает браузер. Инструмент локальный: "
            "проект живёт в памяти процесса, сохраняется кнопкой в файл."
        ),
    )
    serve.add_argument("--host", default="127.0.0.1", help="адрес прослушивания")
    serve.add_argument("--port", type=int, default=8000, help="порт")
    serve.add_argument(
        "--project", type=Path, default=None, help="открыть проект из JSON при старте"
    )
    serve.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    serve.set_defaults(handler=_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Точка входа консольной команды."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ValueError) as error:
        print(f"boardforge: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
