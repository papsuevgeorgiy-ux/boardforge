"""Оформление рендера. Режим — параметр, а не ветка в коде.

Рисовальщик спрашивает у стиля цвета и толщины и нигде не сравнивает имя
режима. Ч/б цеховой чертёж Дня 5 добавляется новой записью в `STYLES`
и своей `repaint`, а не вторым проходом по всему модулю.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace

from ..core.species import Palette


@dataclass(frozen=True, slots=True)
class Stroke:
    """Линия: цвет, толщина в миллиметрах модели, непрозрачность."""

    color: str
    width_mm: float
    opacity: float = 1.0

    def __post_init__(self) -> None:
        if self.width_mm <= 0:
            raise ValueError("толщина линии должна быть положительной")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError("непрозрачность линии должна быть в 0–1")


@dataclass(frozen=True, slots=True)
class RenderStyle:
    """Как выглядит рендер: чем красим ячейки, чем обводим швы и кромку."""

    name: str
    seam: Stroke
    edge: Stroke
    texture: bool
    """Разрешена ли текстура вообще. Мелкий масштаб гасит её и при `True`."""
    background: str | None = None
    repaint: Callable[[Palette], Palette] | None = None
    """Преобразование палитры породы. `None` — брать как есть."""

    def palette(self, palette: Palette) -> Palette:
        """Палитра породы в этом стиле."""
        return palette if self.repaint is None else self.repaint(palette)


def _flatten(palette: Palette) -> Palette:
    """Погасить рисунок, оставив один тон: заливка без ранней и поздней зоны."""
    return replace(
        palette,
        earlywood=palette.base,
        latewood=palette.base,
        ray=palette.base,
        ring_contrast=0.0,
        ray_contrast=0.0,
    )


PREVIEW = RenderStyle(
    name="preview",
    seam=Stroke("#2a211a", 0.35, 0.55),
    edge=Stroke("#201913", 0.9),
    texture=True,
)
"""Цветное превью: полная палитра и процедурная текстура торца."""

FLAT = RenderStyle(
    name="flat",
    seam=Stroke("#2a211a", 0.35, 0.55),
    edge=Stroke("#201913", 0.9),
    texture=False,
    repaint=_flatten,
)
"""Плоская заливка: только основной тон и швы. Быстро и легко по весу."""

STYLES: dict[str, RenderStyle] = {style.name: style for style in (PREVIEW, FLAT)}


def style_by_name(name: str) -> RenderStyle:
    """Стиль по имени, с внятным списком в ошибке."""
    try:
        return STYLES[name]
    except KeyError:
        known = ", ".join(sorted(STYLES))
        raise ValueError(f"неизвестный режим рендера {name!r}: есть {known}") from None


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Параметры рендера. Всё, что отличает один вызов от другого."""

    scale: float = 2.0
    """Пикселей на миллиметр."""
    style: RenderStyle = PREVIEW
    margin_mm: float = 6.0
    min_texture_px: float = 16.0
    """Порог детализации: ячейка мельче этого на экране рисуется одной заливкой.

    Считается в пикселях документа, а не в миллиметрах доски, — иначе отдаление
    не убирало бы кольца. При масштабе по умолчанию порог отвечает ячейке 8 мм.
    """
    digits: int = 2

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise ValueError("масштаб должен быть положительным")
        if self.margin_mm < 0:
            raise ValueError("поле вокруг доски не может быть отрицательным")
        if self.digits < 0:
            raise ValueError("точность координат не может быть отрицательной")
