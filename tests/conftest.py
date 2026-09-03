"""Fixtures for the Smart LD2410 integration tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from bleak.backends.device import BLEDevice

from custom_components.smart_ld2410.algo.types import GATE_COUNT, Frame
from custom_components.smart_ld2410.ble.protocol import DeviceParams

TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Point hass.config.config_dir at a fresh tmp dir, not the shared fixture one.

    The store lives under this dir (smart_ld2410/frames.db); without this
    override every test would share and accumulate rows in the same on-disk
    database across the whole suite.
    """
    return str(tmp_path)


class FakeLD2410Client:
    """Stand-in for LD2410Client: captures callbacks, never touches BLE."""

    def __init__(
        self,
        ble_device: BLEDevice,
        on_frame: Callable[[Frame], None],
        on_availability: Callable[[bool], None],
        password: bytes = b"HiLink",
        ble_device_lookup: Callable[[], BLEDevice | None] | None = None,
    ) -> None:
        """Capture the callbacks a test injects synthetic events through."""
        self.ble_device = ble_device
        self.on_frame = on_frame
        self.on_availability = on_availability
        self.password = password
        self.ble_device_lookup = ble_device_lookup
        self.started = False
        self.stopped = False
        self.set_ble_device_calls: list[BLEDevice] = []
        self.set_gate_sensitivity_calls: list[tuple[int, int, int]] = []
        self.read_params_result = DeviceParams(
            max_gate=GATE_COUNT - 1,
            max_move_gate=GATE_COUNT - 1,
            max_still_gate=GATE_COUNT - 1,
            move_sensitivities=(15,) * GATE_COUNT,
            still_sensitivities=(15,) * GATE_COUNT,
            absence_delay_s=5,
        )
        self.command_error: Exception | None = None

    async def start(self) -> None:
        """Pretend to connect."""
        self.started = True

    async def stop(self) -> None:
        """Pretend to disconnect."""
        self.stopped = True

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Record a fresh BLEDevice reference."""
        self.set_ble_device_calls.append(ble_device)
        self.ble_device = ble_device

    async def set_gate_sensitivity(self, gate: int, moving: int, static: int) -> None:
        """Record a sensitivity write, or raise command_error if set."""
        if self.command_error is not None:
            raise self.command_error
        self.set_gate_sensitivity_calls.append((gate, moving, static))

    async def read_params(self) -> DeviceParams:
        """Return read_params_result, or raise command_error if set."""
        if self.command_error is not None:
            raise self.command_error
        return self.read_params_result


@pytest.fixture
def ble_device() -> BLEDevice:
    """A BLEDevice for the test sensor's address."""
    return BLEDevice(TEST_ADDRESS, "PRP1-RD_6615", details=None)


@pytest.fixture
def fake_clients() -> list[FakeLD2410Client]:
    """Every FakeLD2410Client instance created during a test."""
    return []


@pytest.fixture(autouse=True)
def patch_ld2410_client(
    fake_clients: list[FakeLD2410Client],
) -> object:
    """Patch LD2410Client at the __init__.py module boundary."""

    def _factory(*args: object, **kwargs: object) -> FakeLD2410Client:
        client = FakeLD2410Client(*args, **kwargs)  # type: ignore[arg-type]
        fake_clients.append(client)
        return client

    with patch(
        "custom_components.smart_ld2410.LD2410Client", side_effect=_factory
    ):
        yield


@pytest.fixture(autouse=True)
def patch_ble_resolution(ble_device: BLEDevice) -> object:
    """Make async_ble_device_from_address resolve the test sensor's address."""
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=ble_device,
    ):
        yield


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
