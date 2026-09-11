"""Tests for the connection lifecycle of LD2410Client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from custom_components.smart_ld2410.algo.types import Frame
from custom_components.smart_ld2410.ble import client as client_module
from custom_components.smart_ld2410.ble import protocol
from custom_components.smart_ld2410.ble.client import LD2410Client


def _ack_bytes(command_word: int, status: int = 0) -> bytes:
    """Build the ACK frame the device would answer a command word with."""
    body = (command_word | 0x0100).to_bytes(2, "little") + status.to_bytes(
        2, "little"
    )
    return (
        protocol.CMD_HEADER
        + len(body).to_bytes(2, "little")
        + body
        + protocol.CMD_FOOTER
    )


class FakeBleakClient:
    """Minimal stand-in for BleakClientWithServiceCache."""

    def __init__(
        self,
        disconnected_callback: Callable[[FakeBleakClient], None],
        *,
        ack: bool,
        command_statuses: dict[int, int] | None = None,
    ) -> None:
        """Create a connected fake; ``ack`` decides if commands get answered.

        ``command_statuses`` maps a command word to the ACK status it should
        be answered with (default 0/success for anything not listed).
        """
        self.is_connected = True
        self.disconnect_calls = 0
        self.ack = ack
        self.owner: LD2410Client | None = None
        self._disconnected_callback = disconnected_callback
        self._command_statuses = command_statuses or {}
        self.written_words: list[int] = []

    async def start_notify(self, _uuid: str, _handler: object) -> None:
        """Accept the notification subscription."""

    async def write_gatt_char(
        self, _uuid: str, data: bytes, response: bool = False
    ) -> None:
        """Answer the written command with a success ACK, if acking."""
        word = int.from_bytes(data[6:8], "little")
        self.written_words.append(word)
        if not self.ack or self.owner is None:
            return
        status = self._command_statuses.get(word, 0)
        asyncio.get_running_loop().call_soon(
            self.owner._on_notify,  # noqa: SLF001
            None,
            bytearray(_ack_bytes(word, status)),
        )

    async def disconnect(self) -> None:
        """Disconnect and fire the callback, exactly as bleak does."""
        self.disconnect_calls += 1
        self.is_connected = False
        self._disconnected_callback(self)


def _reconnect_loop_tasks() -> list[asyncio.Task[None]]:
    """Every live LD2410Client._reconnect_loop task on this loop."""
    return [
        task
        for task in asyncio.all_tasks()
        if getattr(task.get_coro(), "__qualname__", "").endswith(
            "LD2410Client._reconnect_loop"
        )
    ]


@pytest.fixture
def fast_client_timings() -> object:
    """Shrink the command timeout and backoff so tests stay sub-second."""
    with (
        patch.object(client_module, "_COMMAND_TIMEOUT_S", 0.01),
        patch.object(client_module, "_RECONNECT_INITIAL_DELAY_S", 0.01),
        patch.object(client_module, "_RECONNECT_MAX_DELAY_S", 0.01),
    ):
        yield


def _make_client(
    availability: list[bool], frames: list[Frame]
) -> LD2410Client:
    return LD2410Client(
        BLEDevice("AA:BB:CC:DD:EE:FF", "PRP1-RD_6615", details=None),
        frames.append,
        availability.append,
    )


async def test_failed_init_does_not_leak_a_second_reconnect_loop(
    fast_client_timings: object,
) -> None:
    """The deliberate disconnect after a failed init must not spawn a rival loop."""
    availability: list[bool] = []
    frames: list[Frame] = []
    client = _make_client(availability, frames)
    fakes: list[FakeBleakClient] = []

    async def _fake_establish(_cls: object, *args: object, **kwargs: object):
        fake = FakeBleakClient(args[2], ack=False)  # type: ignore[arg-type]
        fake.owner = client
        fakes.append(fake)
        return fake

    with patch.object(client_module, "establish_connection", _fake_establish):
        await client.start()
        # Let several init attempts fail in a row.
        while len(fakes) < 3:
            await asyncio.sleep(0.01)
        assert len(_reconnect_loop_tasks()) == 1
        assert all(fake.disconnect_calls == 1 for fake in fakes[:-1])

        await client.stop()
        assert _reconnect_loop_tasks() == []

        attempts_at_stop = len(fakes)
        await asyncio.sleep(0.05)
        assert len(fakes) == attempts_at_stop  # no loop still running


async def test_initial_connect_failure_retries_until_it_succeeds(
    fast_client_timings: object,
) -> None:
    """A device out of range at start() keeps retrying instead of giving up."""
    availability: list[bool] = []
    frames: list[Frame] = []
    client = _make_client(availability, frames)
    attempts = 0
    fakes: list[FakeBleakClient] = []

    async def _fake_establish(_cls: object, *args: object, **kwargs: object):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise BleakError("device not found")
        fake = FakeBleakClient(args[2], ack=True)  # type: ignore[arg-type]
        fake.owner = client
        fakes.append(fake)
        return fake

    with patch.object(client_module, "establish_connection", _fake_establish):
        await client.start()
        assert availability == []  # setup does not block on the connection

        for _ in range(200):
            if availability:
                break
            await asyncio.sleep(0.01)

        assert availability == [True]
        assert attempts == 3

        await client.stop()

    assert _reconnect_loop_tasks() == []
    assert fakes[0].disconnect_calls == 1


async def test_wrong_password_ack_status_raises_authentication_error(
    fast_client_timings: object,
) -> None:
    """A non-zero ACK status on the password command aborts init as an auth failure."""
    availability: list[bool] = []
    frames: list[Frame] = []
    client = _make_client(availability, frames)
    fakes: list[FakeBleakClient] = []

    async def _fake_establish(_cls: object, *args: object, **kwargs: object):
        fake = FakeBleakClient(
            args[2],  # type: ignore[arg-type]
            ack=True,
            command_statuses={protocol.CMD_BLUETOOTH_PASSWORD: 1},
        )
        fake.owner = client
        fakes.append(fake)
        return fake

    with patch.object(client_module, "establish_connection", _fake_establish):
        await client.start()
        while len(fakes) < 2:
            await asyncio.sleep(0.01)
        assert availability == []  # never became available
        assert all(fake.disconnect_calls == 1 for fake in fakes[:-1])

        await client.stop()
        assert _reconnect_loop_tasks() == []


async def test_ble_device_lookup_is_used_for_reconnect(
    fast_client_timings: object,
) -> None:
    """The lookup callable is consulted before each attempt and its result used."""
    availability: list[bool] = []
    frames: list[Frame] = []
    stored_device = BLEDevice("AA:BB:CC:DD:EE:FF", "PRP1-RD_6615", details=None)
    fresh_device = BLEDevice(
        "AA:BB:CC:DD:EE:FF", "PRP1-RD_6615", details={"source": "esphome-proxy"}
    )
    lookup_calls = 0

    def _lookup() -> BLEDevice | None:
        nonlocal lookup_calls
        lookup_calls += 1
        return fresh_device

    client = LD2410Client(
        stored_device,
        frames.append,
        availability.append,
        ble_device_lookup=_lookup,
    )
    fakes: list[FakeBleakClient] = []
    seen_devices: list[BLEDevice] = []

    async def _fake_establish(_cls: object, device: object, *args: object, **kwargs: object):
        seen_devices.append(device)  # type: ignore[arg-type]
        fake = FakeBleakClient(args[1], ack=True)  # type: ignore[arg-type]
        fake.owner = client
        fakes.append(fake)
        return fake

    with patch.object(client_module, "establish_connection", _fake_establish):
        await client.start()
        for _ in range(200):
            if availability:
                break
            await asyncio.sleep(0.01)
        assert availability == [True]

        await client.stop()

    assert lookup_calls >= 1
    assert seen_devices[0] is fresh_device


async def test_unexpected_disconnect_reconnects_once(
    fast_client_timings: object,
) -> None:
    """A real disconnect starts exactly one reconnect loop."""
    availability: list[bool] = []
    frames: list[Frame] = []
    client = _make_client(availability, frames)
    fakes: list[FakeBleakClient] = []

    async def _fake_establish(_cls: object, *args: object, **kwargs: object):
        fake = FakeBleakClient(args[2], ack=True)  # type: ignore[arg-type]
        fake.owner = client
        fakes.append(fake)
        return fake

    with patch.object(client_module, "establish_connection", _fake_establish):
        await client.start()
        for _ in range(200):
            if availability:
                break
            await asyncio.sleep(0.01)
        assert availability == [True]

        # Simulate the peripheral dropping the link.
        fakes[0].is_connected = False
        client._on_disconnected(fakes[0])  # noqa: SLF001
        assert availability == [True, False]
        assert len(_reconnect_loop_tasks()) == 1

        for _ in range(200):
            if len(availability) > 2:
                break
            await asyncio.sleep(0.01)
        assert availability == [True, False, True]
        assert len(fakes) == 2

        await client.stop()

    assert _reconnect_loop_tasks() == []
