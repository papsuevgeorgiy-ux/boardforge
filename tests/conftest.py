"""Общие фикстуры."""

import pytest

from boardforge.core.program import Program
from tests.helpers import build_checkerboard, build_two_panels


@pytest.fixture
def checkerboard() -> Program:
    """Эталонная шахматка 15×3 ячейки из одного щита."""
    return build_checkerboard()


@pytest.fixture
def two_panels() -> Program:
    """Доска, где ряды приходят из двух разных щитов."""
    return build_two_panels()
