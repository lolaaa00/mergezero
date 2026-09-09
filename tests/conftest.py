"""Shared direct-mode test configuration for MergeZero."""
import pytest


@pytest.fixture(autouse=True)
def _reset_contract_registry():
    yield
    try:
        import genlayer.gl.genvm_contracts as contracts
    except ImportError:
        return
    contracts.__known_contract__ = None
