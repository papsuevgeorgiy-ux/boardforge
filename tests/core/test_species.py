"""Справочник пород."""

import pytest

from boardforge.core.species import Palette, Species, load_species


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
    """Все цвета палитры годятся для SVG без дополнительной обработки."""
    for item in catalogue.values():
        for color in item.palette.colors:
            assert len(color) == 7 and color.startswith("#")


def test_latewood_is_darker_than_earlywood(catalogue: dict[str, Species]) -> None:
    """Поздняя древесина плотнее и всегда темнее ранней — иначе кольцо не читается."""

    def lightness(color: str) -> int:
        return sum(int(color[i : i + 2], 16) for i in (1, 3, 5))

    for item in catalogue.values():
        palette = item.palette
        assert lightness(palette.latewood) < lightness(palette.earlywood), item.key
        assert lightness(palette.ray) > lightness(palette.latewood), item.key


def test_latewood_fraction_is_set_per_species(catalogue: dict[str, Species]) -> None:
    """Доля поздней зоны разведена по породам, а не оставлена по умолчанию.

    У венге узкая очень тёмная прослойка, у клёна широкая и почти неразличимая
    граница — одним контрастом это не выразить.
    """
    fractions = {key: item.palette.latewood_fraction for key, item in catalogue.items()}
    assert fractions["wenge"] < 0.2
    assert fractions["maple_hard"] > 0.5
    assert 0.25 < fractions["oak"] < 0.45
    assert 0.25 < fractions["ash"] < 0.45
    assert len(set(fractions.values())) > 5


def test_ray_width_is_set_per_species(catalogue: dict[str, Species]) -> None:
    """Толщина лучей разведена: у дуба широкие, у бука узкие, у клёна нитевидные."""
    widths = {key: item.palette.ray_width_mm for key, item in catalogue.items()}
    assert widths["oak"] > 3 * widths["beech"]
    assert widths["beech"] > widths["maple_hard"]
    assert catalogue["ash"].palette.ray_contrast == 0.0
    assert catalogue["maple_hard"].palette.ray_contrast < 0.2


def test_latewood_width_follows_the_fraction(catalogue: dict[str, Species]) -> None:
    """Ширина тёмной зоны — производная от периода и доли."""
    for item in catalogue.values():
        palette = item.palette
        assert palette.latewood_width_mm == pytest.approx(
            palette.ring_width_mm * palette.latewood_fraction
        )
        assert palette.latewood_width_mm < palette.ring_width_mm


def test_bad_latewood_fraction_rejected() -> None:
    """Доля вне (0, 1) — ошибка справочника: кольцо не бывает целиком поздним."""
    with pytest.raises(ValueError, match="доля поздней"):
        Palette(
            "#000000",
            "#111111",
            "#000000",
            "#222222",
            0.3,
            0.2,
            2.0,
            latewood_fraction=1.0,
        )


def test_bad_ray_width_rejected() -> None:
    """Нулевая толщина луча — ошибка справочника, а не невидимый луч."""
    with pytest.raises(ValueError, match="луча"):
        Palette(
            "#000000", "#111111", "#000000", "#222222", 0.3, 0.2, 2.0, ray_width_mm=0.0
        )


def test_palette_needs_checking(catalogue: dict[str, Species]) -> None:
    """Сверены ровно дуб и венге, у остальных цвета всё ещё подобраны на глаз.

    Раньше здесь стояло «ни одна порода не сверена» — верно на тот день, когда
    сверять ещё не начали. Теперь ожидание точное с обеих сторон: тест ловит
    и потерянную галочку, и проставленную по недосмотру.
    """
    verified = {key for key, item in catalogue.items() if item.palette.verified}
    assert verified == {"oak", "wenge"}


def test_palette_from_single_color() -> None:
    """Чужой справочник может дать один тон — остальное выводится из него."""
    palette = Palette.from_base("#808080")
    assert palette.base == "#808080"
    assert palette.colors == tuple(dict.fromkeys(palette.colors))
    assert not palette.verified


def test_bad_contrast_rejected() -> None:
    """Выраженность вне 0–1 — ошибка справочника, а не сюрприз в рендере."""
    with pytest.raises(ValueError, match="выраженность"):
        Palette("#000000", "#111111", "#000000", "#222222", 1.5, 0.2, 2.0)


def test_shrinkage_present(catalogue: dict[str, Species]) -> None:
    """Обе усушки заполнены — на них держится предупреждение о короблении."""
    for item in catalogue.values():
        assert item.shrinkage_tangential > 0
        assert item.shrinkage_radial > 0


def test_bad_density_rejected() -> None:
    """Порода без плотности не пройдёт: на ней считается вес доски."""
    with pytest.raises(ValueError, match="плотность"):
        Species("x", "Тест", 0.0, 8.0, 4.0, Palette.from_base("#ffffff"))


def test_bad_color_rejected() -> None:
    """Цвет не в формате #rrggbb отклоняется на загрузке, а не в рендере."""
    with pytest.raises(ValueError, match="цвет"):
        Palette.from_base("красный")


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
