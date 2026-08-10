"""Общие фикстуры."""

import pytest

from boardforge.core.program import Program
from tests.helpers import build_checkerboard


@pytest.fixture
def checkerboard() -> Program:
    """Эталонная шахматка 15×3 ячейки."""
    return build_checkerboard()
