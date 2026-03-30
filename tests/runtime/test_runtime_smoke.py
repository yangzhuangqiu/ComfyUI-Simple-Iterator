import os

import pytest


pytestmark = pytest.mark.runtime


def test_runtime_env_ready_for_optional_tests():
    if os.getenv("RUN_RUNTIME_TESTS") != "1":
        pytest.skip("Set RUN_RUNTIME_TESTS=1 to execute runtime-layer tests.")
    pytest.importorskip("torch")
    assert True
