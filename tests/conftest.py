"""Fixtures for the Smart LD2410 integration tests."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def mock_adapter_history() -> object:
    """Empty the BlueZ advertisement history.

    Reading it goes through dbus_fast's unpack_variants, whose C extension
    isn't available on macOS, so local test runs crash without this.
    """
    with patch(
        "bluetooth_adapters.systems.linux.LinuxAdapters.history",
        PropertyMock(return_value={}),
    ):
        yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture(autouse=True)
def auto_enable_bluetooth(enable_bluetooth: None) -> None:
    """Mock the bluetooth stack so the manifest dependency can set up."""


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Allow the mocked scanner's device-expiry timer to outlive the test."""
    return True
