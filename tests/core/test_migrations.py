"""Миграции схемы проекта."""

import pytest

from boardforge.core.migrations import SCHEMA_VERSION, migrate
from boardforge.core.program import Program

V1_CHECKERBOARD = {
    "schema_version": 1,
    "operations": [
        {
            "op": "Glue",
            "strips": [
                {"species": "maple_hard", "width_mm": 40.0},
                {"species": "walnut_black", "width_mm": 40.0},
            ],
            "length_mm": 200.0,
            "thickness_mm": 40.0,
        },
        {"op": "Crosscut", "step_mm": 40.0},
        {"op": "StandOnEnd"},
        {
            "op": "Assemble",
            "order": [0, 1, 2, 3, 4],
            "reversed": [False] * 5,
            "offsets_mm": [0.0, 40.0, 0.0, 40.0, 0.0],
            "flipped": None,
        },
        {"op": "Crop", "left": 0.0, "right": 0.0, "top": 40.0, "bottom": 40.0},
    ],
}


def test_migration_names_the_single_billet() -> None:
    """В версии 1 заготовка была одна, поэтому имя восстанавливается однозначно."""
    upgraded = migrate(V1_CHECKERBOARD)
    assert upgraded["schema_version"] == SCHEMA_VERSION
    assert upgraded["operations"][0]["id"] == "A"
    assert upgraded["operations"][1]["source"] == "A"
    assert upgraded["operations"][2]["source"] == "A"


def test_migration_converts_order_to_piece_refs() -> None:
    """Порядок деталей превращается в ссылки на щит, из которого они вышли."""
    assemble = migrate(V1_CHECKERBOARD)["operations"][3]
    assert "order" not in assemble
    assert assemble["pieces"][0] == {"billet": "A", "index": 0}
    assert assemble["id"] == "B"


def test_migration_points_later_ops_at_the_assembled_billet() -> None:
    """После склейки следующие операции работают с её результатом, а не с щитом."""
    crop = migrate(V1_CHECKERBOARD)["operations"][4]
    assert crop["source"] == "B"


def test_migrated_project_runs() -> None:
    """Поднятый проект исполняется и даёт доску."""
    prog = Program.from_dict(V1_CHECKERBOARD)
    assert prog.schema_version == SCHEMA_VERSION
    assert prog.errors == []
    assert prog.apply().width_mm == pytest.approx(200.0)


def test_current_version_untouched() -> None:
    """Актуальную схему миграция не трогает."""
    data = {"schema_version": SCHEMA_VERSION, "operations": []}
    assert migrate(data) is data


def test_future_version_rejected() -> None:
    """Проект от более новой сборки не открываем молча."""
    with pytest.raises(ValueError, match="новее"):
        migrate({"schema_version": SCHEMA_VERSION + 1, "operations": []})
