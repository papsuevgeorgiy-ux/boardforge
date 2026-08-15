"""Командная строка: команды доходят до файлов на диске."""

import math

import pytest

from boardforge.cli import main
from boardforge.cli.examples import DIAGNOSTICS, EXAMPLES
from boardforge.core.species import load_species


def test_swatches_writes_a_sheet(tmp_path, capsys) -> None:
    """`swatches` создаёт лист и докладывает, что сверять больше нечего."""
    target = tmp_path / "deep" / "swatches.svg"
    assert main(["swatches", "-o", str(target)]) == 0

    sheet = target.read_text(encoding="utf-8")
    assert sheet.startswith("<?xml")
    for species in load_species().values():
        assert species.name in sheet
    assert "сверены все" in capsys.readouterr().out


def test_swatches_names_the_unverified(tmp_path, capsys) -> None:
    """Несверенную породу команда называет по ключу, а не молчит.

    Штатный справочник сверен целиком, поэтому эту ветку показывает только
    чужой каталог — иначе она осталась бы без теста ровно с того дня, как
    пропала последняя галочка.
    """
    catalogue = tmp_path / "my.yaml"
    catalogue.write_text(
        "birch:\n"
        "  name: Берёза\n"
        "  density: 640\n"
        "  shrinkage: {tangential: 9.0, radial: 5.3}\n"
        '  color: "#e0d2b4"\n',
        encoding="utf-8",
    )
    assert (
        main(["swatches", "--species", str(catalogue), "-o", str(tmp_path / "b.svg")])
        == 0
    )
    assert "не сверено: birch" in capsys.readouterr().out


def test_swatches_takes_a_custom_catalogue(tmp_path) -> None:
    """Свой справочник — свой лист: сверять можно и чужие цвета."""
    catalogue = tmp_path / "my.yaml"
    catalogue.write_text(
        "birch:\n"
        "  name: Берёза\n"
        "  density: 640\n"
        "  shrinkage: {tangential: 9.0, radial: 5.3}\n"
        '  color: "#e0d2b4"\n',
        encoding="utf-8",
    )
    target = tmp_path / "birch.svg"
    assert main(["swatches", "--species", str(catalogue), "-o", str(target)]) == 0
    assert "Берёза" in target.read_text(encoding="utf-8")


def test_examples_write_every_board(tmp_path) -> None:
    """`examples` кладёт все демо-доски в указанный каталог."""
    assert main(["examples", "-o", str(tmp_path)]) == 0
    for name in EXAMPLES:
        assert (tmp_path / f"{name}.svg").read_text(encoding="utf-8").startswith("<?xml")


def test_diagnostics_are_off_by_default(tmp_path) -> None:
    """Стенд не узор: в наборе шаблонов ему не место, пока его не попросят."""
    assert main(["examples", "-o", str(tmp_path)]) == 0
    for name in DIAGNOSTICS:
        assert not (tmp_path / f"{name}.svg").exists()

    assert main(["examples", "-o", str(tmp_path), "--diagnostics"]) == 0
    for name in DIAGNOSTICS:
        assert (tmp_path / f"{name}.svg").read_text(encoding="utf-8").startswith("<?xml")


def test_examples_are_manufacturable() -> None:
    """Демо-доски — программы, а не картинки: валидатор пропускает каждую.

    Порог на число ячеек держит планку для библиотеки узоров Дня 4: узор из
    десятка ячеек — не узор. На стенды он не распространяется, у них другая
    работа.
    """
    for name, (_, build) in EXAMPLES.items():
        program = build()
        assert program.errors == [], name
        assert len(program.apply().pieces) > 20, name


def test_diagnostics_are_manufacturable() -> None:
    """Стенды тоже настоящие программы — иначе они ничего не доказывают."""
    for name, (_, build) in DIAGNOSTICS.items():
        program = build()
        assert program.errors == [], name
        assert program.apply().pieces


def test_reversed_check_shows_both_orientations() -> None:
    """Стенд разворота обязан содержать и прямые ячейки, и развёрнутые.

    Иначе он молча выродится в обычную доску и перестанет что-либо проверять.
    """
    from boardforge.cli.examples import reversed_check

    board = reversed_check().apply()
    turns = {piece.orientation.turn_deg for piece in board.pieces}
    assert turns == {0.0, 180.0}
    assert len({piece.origin.strip for piece in board.pieces}) == 1


def _stand_cells(program) -> list:
    """Ячейки стенда слева направо — туда же растёт смещение по длине рейки."""
    return sorted(program.apply().pieces, key=lambda piece: piece.polygon.bounds[0])


def test_column_check_is_one_rail_in_order() -> None:
    """Стенд перетекания: одна рейка, подряд идущие срезы, ни одного разворота.

    Развернись здесь хоть одна ячейка — стенд стал бы проверять разворот,
    а не перетекание, и обе проверки перестали бы что-либо значить.
    """
    from boardforge.cli.examples import STAND_CELL_MM, STAND_CELLS, column_check

    cells = _stand_cells(column_check())
    assert len(cells) == STAND_CELLS
    assert {piece.origin.strip for piece in cells} == {0}
    assert {piece.orientation.turn_deg for piece in cells} == {0.0}
    assert not any(piece.orientation.mirrored for piece in cells)

    offsets = [piece.origin.offset_mm for piece in cells]
    assert offsets == pytest.approx(
        [index * STAND_CELL_MM for index in range(STAND_CELLS)]
    )


def test_column_check_actually_shows_the_drift() -> None:
    """На стенде дрейф обязан быть виден и при этом остаться дрейфом.

    Нулевой сдвиг сердцевины — и смотреть не на что; сдвиг размером с ячейку —
    и это уже не перетекание, а разрыв.
    """
    from boardforge.cli.examples import STAND_CELL_MM, STAND_SPECIES, column_check
    from boardforge.render.texture import ring_field

    ring = load_species()[STAND_SPECIES].palette.ring_width_mm
    fields = [
        ring_field(piece.origin, ring, STAND_CELL_MM, piece.orientation)
        for piece in _stand_cells(column_check())
    ]
    steps = [
        math.hypot(second.pith_x - first.pith_x, second.pith_y - first.pith_y)
        for first, second in zip(fields, fields[1:], strict=False)
    ]
    assert max(steps) < 0.1 * STAND_CELL_MM
    assert sum(steps) > ring


def test_unknown_style_is_reported(tmp_path, capsys) -> None:
    """Опечатка в режиме — понятная ошибка и ненулевой код возврата."""
    assert main(["examples", "-o", str(tmp_path), "--style", "сепия"]) == 1
    assert "неизвестный режим" in capsys.readouterr().err


def test_missing_command_is_rejected() -> None:
    """Без подкоманды argparse ругается сам."""
    with pytest.raises(SystemExit):
        main([])


def test_missing_file_is_named_not_errno(tmp_path, capsys) -> None:
    """Ненайденный файл называется путём, а не `[Errno 2]` по-английски.

    Ветка одна на все подкоманды, поэтому и проверяется на той, что подешевле.
    """
    assert main(["swatches", "--species", str(tmp_path / "нет.yaml")]) == 1

    complaint = capsys.readouterr().err
    assert "файл не найден" in complaint
    assert "нет.yaml" in complaint
    assert "Errno" not in complaint


def test_unknown_units_are_refused_not_silently_ignored(tmp_path) -> None:
    """Неизвестные единицы — отказ, а не молчаливые миллиметры.

    `units_by_key` на неизвестный ключ отвечает миллиметрами, и для веба это
    верно: в выпадающем списке junk не наберёшь. Здесь ключ набирают руками,
    и выдать не те единицы молча — хуже, чем отказать.
    """
    with pytest.raises(SystemExit):
        main(["workshop", "-o", str(tmp_path), "--units", "дюймы"])


def test_unknown_generate_template_is_refused(tmp_path) -> None:
    """Опечатка в имени шаблона — отказ argparse, а не голый `KeyError`.

    До этого опечатка доходила до `LIBRARY[template]`, и `KeyError` выходил
    наружу трейсбеком: он не наследует ни `OSError`, ни `ValueError`, поэтому
    его не ловила ни одна ветка `main()`.
    """
    with pytest.raises(SystemExit):
        main(["generate", "--template", "чебурашка", "-o", str(tmp_path / "b.svg")])
