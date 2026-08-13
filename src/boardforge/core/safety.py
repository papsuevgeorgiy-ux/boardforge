"""Изготовимость: то, что видно только по числам, а не по последовательности.

`Program.validate()` читает операции и молчит про геометрию — законная
программа может дать деталь, которую опасно вести по станку. Здесь проверки,
для которых программу надо сначала исполнить.

Три вопроса, и все три про цех, а не про красоту:

- **Клин на кромке.** При угловом резе крайние полосы щита вырождаются
  в клинья, и остриё затягивает под диск при торцовке. Мерить его шириной
  бесполезно: у прямоугольного треугольника с катетами по 40 мм минимальный
  прямоугольник вовсе не узкий. Опасен **нос**, и его угол равен
  `min(θ, 90° − θ)` — то есть тем острее, чем ближе рез к продольному.
- **Тонкая деталь.** Отдельно от клина: длинная узкая полоса тонка по всей
  длине, и её меряют шириной.
- **Опрокидывание.** После `StandOnEnd` рез в плане даёт брусок сечением
  «шаг реза × высота доски». Высокий и узкий брусок валится на столе.

Пороги — параметры, а не числа в коде: у ленточной пилы и у форматника
разные привычки, и спорить с настройкой мастерской инструмент не должен.
"""

from dataclasses import dataclass

from .ops import Cut, target_of
from .program import Execution, Issue, Program


@dataclass(frozen=True, slots=True)
class Limits:
    """Пороги цеха. Значения стартовые, спорить с мастерской не наше дело.

    `min_part_width_mm` и `min_angle_deg` — про **деталь**, ту, что берут в руки
    и ведут по станку. Это безопасность.

    `min_cell_width_mm` — про ячейку внутри детали. Ячейку никто не берёт в руки:
    её склеили несколько операций назад, и она едет по станку вместе со всей
    полосой. Поэтому здесь вопрос не безопасности, а вида: волосок чужой породы
    в поле читается как царапина. Порог соответственно мельче, уровень ниже.
    """

    min_part_width_mm: float = 10.0
    min_cell_width_mm: float = 1.5
    min_angle_deg: float = 15.0
    max_tipping_ratio: float = 3.0

    def __post_init__(self) -> None:
        for name in (
            "min_part_width_mm",
            "min_cell_width_mm",
            "min_angle_deg",
            "max_tipping_ratio",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"порог {name} должен быть положительным")


def _used_parts(program: Program) -> dict[str, set[int]]:
    """Какие детали каждой заготовки реально идут в склейку.

    Клин, который остался в отходе, руками не ведут — жаловаться на него значит
    приучать пользователя пролистывать замечания.
    """
    used: dict[str, set[int]] = {}
    for op in program.operations:
        if hasattr(op, "pieces"):
            for ref in op.pieces:
                used.setdefault(ref.billet, set()).add(ref.index)
    return used


def inspect(
    program: Program, execution: Execution, limits: Limits | None = None
) -> list[Issue]:
    """Замечания об изготовимости, с привязкой к номеру операции."""
    limits = limits or Limits()
    issues: list[Issue] = []
    used = _used_parts(program)

    for cut in execution.cuts:
        parts = execution.billets.get(cut.billet, ())
        indices = sorted(used.get(cut.billet, set()))

        for index in indices:
            if index >= len(parts):
                continue
            part = parts[index]

            width = part.outline_min_width_mm
            if width < limits.min_part_width_mm:
                issues.append(
                    Issue(
                        "error",
                        f"деталь {cut.billet}#{index} вышла клином шириной "
                        f"{width:.1f} мм при пороге {limits.min_part_width_mm:.0f}. "
                        f"Такую полосу при торцовке затягивает под диск — "
                        f"не ставь её в щит, а рез начни отступив от кромки",
                        cut.op_index,
                    )
                )

            angle = part.outline_min_angle_deg
            if angle < limits.min_angle_deg:
                issues.append(
                    Issue(
                        "error",
                        f"деталь {cut.billet}#{index} выходит клином с носом "
                        f"{angle:.0f}° при пороге {limits.min_angle_deg:.0f}°. "
                        f"Остриё затягивает под диск при торцовке, а под "
                        f"струбциной оно скалывается — не бери эту полосу в щит",
                        cut.op_index,
                    )
                )

            cell = part.min_width_mm
            if cell < limits.min_cell_width_mm:
                issues.append(
                    Issue(
                        "warning",
                        f"в детали {cut.billet}#{index} ячейка шириной {cell:.1f} мм — "
                        f"это волосок чужой породы у самой кромки. Не опасно, "
                        f"но в готовой доске читается как царапина",
                        cut.op_index,
                    )
                )

    issues.extend(_tipping_issues(program, execution, limits))
    return issues


def _tipping_issues(
    program: Program, execution: Execution, limits: Limits
) -> list[Issue]:
    """Резы, после которых на столе оказывается высокий и узкий брусок."""
    issues: list[Issue] = []
    heights = {
        name: parts[0].thickness_mm for name, parts in execution.billets.items() if parts
    }

    for index, op in enumerate(program.operations):
        if not isinstance(op, Cut):
            continue
        height = heights.get(target_of(op))
        if height is None:
            continue
        ratio = height / op.step_mm
        if ratio > limits.max_tipping_ratio:
            issues.append(
                Issue(
                    "warning",
                    f"брусок после этого реза выходит {height:.0f} мм высотой "
                    f"при ширине {op.step_mm:.0f} — это {ratio:.1f} к одному. "
                    f"Такой на столе валится: веди его в салазках или прижиме, "
                    f"либо возьми шаг крупнее",
                    index,
                )
            )
    return issues


__all__ = ["Limits", "inspect"]
