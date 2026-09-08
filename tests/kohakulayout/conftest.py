"""Shared fixtures for the KohakuLayout suite: fixture paths, the null problem and the state checker."""

from pathlib import Path

import pytest

from kohakulayout.physics import get
from kohakulayout.state import StateCheck, World
from kohakulayout.templates.physics.null import problem as null_problem

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def kl_fixtures() -> Path:
    """Directory of the framework's ``.kl`` fixtures."""
    return FIXTURES


@pytest.fixture
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def null_world() -> World:
    problem = null_problem()
    return World(problem, get(problem.physics))


@pytest.fixture
def state_check(null_world: World) -> StateCheck:
    """The state checker mounted on a null world."""
    return StateCheck().mount(null_world)
