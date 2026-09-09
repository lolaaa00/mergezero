"""Integration-test infrastructure.

The hosted Studio intermittently returns infrastructure errors (database
connection-pool exhaustion, gateway timeouts) that are unrelated to contract
execution. ``genlayer_py``'s provider raises on the first one, which can abort a
lifecycle mid-run even though the chain state is fine.

This wraps the provider transport with a bounded retry for those specific
transient errors only. Contract-level errors (``UserError``, consensus results,
anything the contract itself produced) are never retried and propagate as-is.
"""

import time

import pytest
from genlayer_py.exceptions import GenLayerError
from genlayer_py.provider.provider import GenLayerProvider

TRANSIENT_MARKERS = (
    "queuepool limit",
    "connection timed out",
    "connection reset",
    "timeout",
    "temporarily unavailable",
    "bad gateway",
    "service unavailable",
    "gateway time-out",
    "502",
    "503",
    "504",
)

MAX_ATTEMPTS = 6
BASE_DELAY_SECONDS = 3


def _is_transient(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in TRANSIENT_MARKERS)


@pytest.fixture(autouse=True, scope="session")
def retry_transient_studio_errors():
    original = GenLayerProvider.make_request

    def make_request(self, method, params):
        last = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                return original(self, method, params)
            except GenLayerError as err:
                if not _is_transient(err):
                    raise
                last = err
                delay = BASE_DELAY_SECONDS * (2**attempt)
                print(f"[transient studio error on {method}, retry {attempt + 1}/{MAX_ATTEMPTS} in {delay}s] {err}")
                time.sleep(delay)
        raise last

    GenLayerProvider.make_request = make_request
    try:
        yield
    finally:
        GenLayerProvider.make_request = original
