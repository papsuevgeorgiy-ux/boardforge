"""Справочник пород."""

import pytest

from boardforge.core.species import Species, load_species


@pytest.fixture(scope="module")
def catalogue() -> dict[str, Species]:
    return load_species()


def test_catalogue_loads(catalogue: dict[str, Species]) -> None:
    """В справочнике все двенадцать пород из доменной модели."""
    assert len(catalogue) == 12
    assert catalogue["maple_hard"].name == "Клён сахарный"
    assert catalogue["maple_hard"].density_kg_m3 == pytest.approx(705)


def test_open_pores_flagged(catalogue: dict[str, Species]) -> None:
    """Дуб и ясень помечены крупными порами — их не советуют для торца."""
    assert catalogue["oak"].open_pores
    assert catalogue["ash"].open_pores
    assert not catalogue["maple_hard"].open_pores


def test_allergens_flagged(catalogue: dict[str, Species]) -> None:
    """Венге и амарант помечены, но не запрещены."""
    assert catalogue["wenge"].allergen
    assert catalogue["purpleheart"].allergen


def test_fading_flagged(catalogue: dict[str, Species]) -> None:
    """Породы с нестойким цветом отмечены отдельно."""
    assert {key for key, item in catalogue.items() if item.fades} == {
        "cherry",
        "padauk",
        "purpleheart",
    }


def test_colors_are_srgb(catalogue: dict[str, Species]) -> None:
    """Цвет годится для SVG без дополнительной обработки."""
    for item in catalogue.values():
        assert len(item.color) == 7 and item.color.startswith("#")


def test_shrinkage_present(catalogue: dict[str, Species]) -> None:
    """Обе усушки заполнены — на них держится предупреждение о короблении."""
    for item in catalogue.values():
        assert item.shrinkage_tangential > 0
        assert item.shrinkage_radial > 0


def test_bad_density_rejected() -> None:
    """Порода без плотности не пройдёт: на ней считается вес доски."""
    with pytest.raises(ValueError, match="плотность"):
        Species("x", "Тест", 0.0, 8.0, 4.0, "#ffffff")


def test_bad_color_rejected() -> None:
    """Цвет не в формате #rrggbb отклоняется на загрузке, а не в рендере."""
    with pytest.raises(ValueError, match="цвет"):
        Species("x", "Тест", 700.0, 8.0, 4.0, "красный")


def test_custom_catalogue(tmp_path) -> None:
    """Справочник можно подменить своим файлом."""
    path = tmp_path / "my.yaml"
    path.write_text(
        "birch:\n"
        "  name: Берёза\n"
        "  density: 640\n"
        "  shrinkage: {tangential: 9.0, radial: 5.3}\n"
        '  color: "#e0d2b4"\n',
        encoding="utf-8",
    )
    loaded = load_species(path)
    assert loaded["birch"].name == "Берёза"


def test_missing_field_reports_species(tmp_path) -> None:
    """Ошибка в справочнике называет породу, а не только поле."""
    path = tmp_path / "broken.yaml"
    path.write_text("birch:\n  name: Берёза\n", encoding="utf-8")
    with pytest.raises(ValueError, match="birch"):
        load_species(path)
