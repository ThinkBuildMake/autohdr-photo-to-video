import pytest

from tests.support.fixtures import client  # noqa: F401
from tests.support.jobs_rows import planning_idle, scripted_planner  # noqa: F401
from tests.support.library_rows import stub_presets  # noqa: F401


@pytest.fixture(autouse=True)
def _every_test_waits_for_planning(planning_idle):  # noqa: F811
    """Planning threads finish before the test's database goes away."""
